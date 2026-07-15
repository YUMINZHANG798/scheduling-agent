from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterator

import httpx

from app.core.config import get_settings
from app.data.store import SQLiteStore
from app.engine.scheduling import SchedulingGenerator


@dataclass(frozen=True)
class LlmConfig:
    enabled: bool
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float
    temperature: float
    max_tokens: int


class OpenAICompatibleClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def complete(self, messages: list[dict[str, str]]) -> str | None:
        config = self._load_config()
        if not config.enabled or not config.base_url or not config.api_key or not config.model:
            return None

        endpoint = self._chat_endpoint(config.base_url)
        payload = self._payload(config, messages, stream=False)
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        try:
            response = httpx.post(endpoint, headers=headers, json=payload, timeout=max(config.timeout_seconds, 90))
            response.raise_for_status()
            body = response.json()
            return body["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return None

    def stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        config = self._load_config()
        if not config.enabled or not config.base_url or not config.api_key or not config.model:
            raise RuntimeError("LLM_CONFIG_MISSING")

        endpoint = self._chat_endpoint(config.base_url)
        payload = self._payload(config, messages, stream=True)
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        with httpx.stream(
            "POST",
            endpoint,
            headers=headers,
            json=payload,
            timeout=max(config.timeout_seconds, 90),
        ) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines():
                line = raw_line.strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                try:
                    body = json.loads(data)
                    delta = body["choices"][0].get("delta", {}).get("content")
                except (KeyError, IndexError, TypeError, ValueError):
                    continue
                if delta:
                    yield delta

    def _payload(self, config: LlmConfig, messages: list[dict[str, str]], stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "stream": stream,
        }
        uses_completion_tokens = config.model.lower().startswith("gpt-5")
        if not uses_completion_tokens:
            payload["temperature"] = config.temperature
        token_limit_key = "max_completion_tokens" if uses_completion_tokens else "max_tokens"
        payload[token_limit_key] = config.max_tokens
        return payload

    def _load_config(self) -> LlmConfig:
        path = self.settings.llm_config_path
        if not path.exists():
            return LlmConfig(False, "", "", "", 30, 0.2, 1200)
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return LlmConfig(
            enabled=bool(data.get("enabled", True)),
            base_url=str(data.get("base_url", "")).strip(),
            api_key=str(data.get("api_key", "")).strip(),
            model=str(data.get("model", "")).strip(),
            timeout_seconds=float(data.get("timeout_seconds", 30)),
            temperature=float(data.get("temperature", 0.2)),
            max_tokens=int(data.get("max_tokens", 1200)),
        )

    def _chat_endpoint(self, base_url: str) -> str:
        clean = base_url.rstrip("/")
        if clean.endswith("/chat/completions"):
            return clean
        return f"{clean}/chat/completions"


class AgentService:
    def __init__(
        self,
        store: SQLiteStore | None = None,
        generator: SchedulingGenerator | None = None,
        llm_client: OpenAICompatibleClient | None = None,
    ) -> None:
        self.store = store or SQLiteStore()
        self.generator = generator or SchedulingGenerator()
        self.llm_client = llm_client or OpenAICompatibleClient()
        self.settings = get_settings()

    def chat(
        self,
        message: str,
        version_id: str | None = None,
        context: dict[str, Any] | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        history = history or []
        version = self.store.get_version(version_id) if version_id else None
        candidates: list[dict[str, Any]] = []

        if self._is_support_question(message):
            area_code = context.get("area_code") or self._guess_area(message)
            slot = context.get("slot", "18:00-21:00")
            date = context.get("date") or self._first_friday(version)
            candidates = (
                self.generator.recommend_support(version, date, slot, area_code, context.get("task_code"))
                if version and date
                else []
            )

        llm_answer = self.llm_client.complete(self._chat_messages(message, version, context, history, candidates))
        if llm_answer:
            return {
                "intent": "llm_schedule_chat",
                "is_fallback": False,
                "message": llm_answer,
                "candidates": candidates,
            }

        return {
            "intent": "llm_unavailable",
            "is_fallback": False,
            "message": "LLM 调用失败，请检查模型配置或稍后重试。",
            "candidates": candidates,
        }

    def stream_chat(
        self,
        message: str,
        version_id: str | None = None,
        context: dict[str, Any] | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> Iterator[str]:
        context = context or {}
        history = history or []
        version = self.store.get_version(version_id) if version_id else None
        candidates: list[dict[str, Any]] = []

        if self._is_support_question(message):
            area_code = context.get("area_code") or self._guess_area(message)
            slot = context.get("slot", "18:00-21:00")
            date = context.get("date") or self._first_friday(version)
            candidates = (
                self.generator.recommend_support(version, date, slot, area_code, context.get("task_code"))
                if version and date
                else []
            )

        yield from self.llm_client.stream(self._chat_messages(message, version, context, history, candidates))

    def schedule_explanation(self, version_id: str) -> dict[str, Any]:
        version = self.store.get_version(version_id)
        if not version:
            return {
                "intent": "schedule_explanation",
                "is_fallback": True,
                "message": "没有找到这版班表，请先生成下周排班。",
                "candidates": [],
            }
        if not version["demand_results"] or not version["schedule_items"]:
            return {
                "intent": "schedule_version_incomplete",
                "is_fallback": False,
                "message": "这版班表缺少需求或排班明细，请重新生成下周排班。",
                "candidates": [],
            }

        messages = self._schedule_explanation_messages(version)
        llm_answer = self.llm_client.complete(messages)
        return {
            "intent": "schedule_explanation",
            "is_fallback": False,
            "message": llm_answer or "LLM 调用失败，请检查模型配置或稍后重试。",
            "candidates": [],
        }

    def stream_schedule_explanation(self, version_id: str) -> Iterator[str]:
        version = self.store.get_version(version_id)
        if not version:
            raise ValueError("VERSION_NOT_FOUND")
        if not version["demand_results"] or not version["schedule_items"]:
            raise ValueError("SCHEDULE_VERSION_INCOMPLETE")
        yield from self.llm_client.stream(self._schedule_explanation_messages(version))

    def recommend_support(
        self, version_id: str, date: str, slot: str, area_code: str, task_code: str | None = None
    ) -> list[dict[str, Any]]:
        version = self.store.get_version(version_id)
        if not version:
            return []
        return self.generator.recommend_support(version, date, slot, area_code, task_code)

    def explain_demand(self, version_id: str, date: str | None, slot: str, area_code: str) -> dict[str, Any]:
        version = self.store.get_version(version_id) if version_id else None
        row = None
        if version and date:
            row = next(
                (
                    item
                    for item in version["demand_results"]
                    if item["date"] == date and item["slot"] == slot and item["area_code"] == area_code
                ),
                None,
            )
        if not row:
            return {
                "intent": "explain_demand",
                "is_fallback": True,
                "message": "暂未找到这个时段的需求记录。请先生成班表，或指定日期、时段和区域。",
                "candidates": [],
            }
        factors = "、".join(row["demand_factors"])
        return {
            "intent": "explain_demand",
            "is_fallback": True,
            "message": f"{row['date']} {row['slot']} {row['area_name']}需要{row['required_count']}人，需求分{row['demand_score']}。主要依据是{factors}；系统因此把该时段标记为{row['priority']}优先级，并用于后续正式工保底和临时工补位。",
            "candidates": [],
        }

    def _chat_messages(
        self,
        message: str,
        version: dict[str, Any] | None,
        context: dict[str, Any],
        history: list[dict[str, str]],
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        schedule_context = self._schedule_context(version) if version else {"status": "no_schedule"}
        safe_history = [
            {"role": row["role"], "content": row["content"]}
            for row in history[-8:]
            if row.get("role") in {"user", "assistant"} and row.get("content")
        ]
        messages = [
            {
                "role": "system",
                "content": (
                    "你是生鲜商超智慧排班 Agent，负责回答排班负责人关于班表、需求预测、人员约束、请假审批、"
                    "专业师傅保护、临时工补位的问题。回答必须基于给定上下文；如果信息不足，说明需要哪个日期、区域或时段。"
                    "不要承诺已经修改班表，除非上下文明确说明。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "当前班表上下文：\n"
                    f"{json.dumps(schedule_context, ensure_ascii=False)}\n"
                    "当前页面上下文：\n"
                    f"{json.dumps(context, ensure_ascii=False)}\n"
                    "支援候选人：\n"
                    f"{json.dumps(candidates[:5], ensure_ascii=False)}"
                ),
            },
            *safe_history,
            {"role": "user", "content": message},
        ]
        return messages

    def _schedule_explanation_messages(self, version: dict[str, Any]) -> list[dict[str, str]]:
        context = self._schedule_context(version)
        return [
            {
                "role": "system",
                "content": (
                    "你是生鲜商超排班负责人助手。请用中文说明本周班表为什么这样排，"
                    "必须覆盖天气、节假日/周末、促销/线上订单、高峰期、专业师傅、正式工保底、临时工混排、风险结果。"
                    "要求具体、业务化、可给门店负责人直接阅读；不要编造上下文没有的数据。"
                ),
            },
            {
                "role": "user",
                "content": f"请详细解释这次下周排班的原因。排班上下文如下：\n{json.dumps(context, ensure_ascii=False)}",
            },
        ]

    def _schedule_context(self, version: dict[str, Any]) -> dict[str, Any]:
        demand_results = version["demand_results"]
        kpis = version.get("kpis") or self.generator.calculate_kpis(
            demand_results,
            version["schedule_items"],
            version["risks"],
            version.get("intervention_count", 0),
        ).model_dump()
        high_demands = sorted(demand_results, key=lambda row: row["demand_score"], reverse=True)[:12]
        factor_counter: Counter[str] = Counter()
        area_peak_counter: defaultdict[str, int] = defaultdict(int)
        for row in demand_results:
            factor_counter.update(row["demand_factors"])
            if row["priority"] == "high":
                area_peak_counter[row["area_name"]] += 1

        weather_rows = self._weather_summary(version["week_start"])
        holidays = self._holiday_summary(version["week_start"])
        promotions = self._promotion_summary(version["week_start"])
        staff_mix = Counter(item["employee_type"] for item in version["schedule_items"])
        protected_count = sum(1 for item in version["schedule_items"] if item["is_protected"])

        return {
            "version_id": version["version_id"],
            "week_start": version["week_start"],
            "store_name": version.get("store_name", self.settings.store_name),
            "kpis": kpis,
            "factor_summary": factor_counter.most_common(10),
            "weather": weather_rows,
            "holidays": holidays,
            "promotions": promotions,
            "high_peak_by_area": dict(area_peak_counter),
            "top_high_demands": [
                {
                    "date": row["date"],
                    "weekday": row["weekday"],
                    "slot": row["slot"],
                    "area": row["area_name"],
                    "task": row["task_name"],
                    "score": row["demand_score"],
                    "required_count": row["required_count"],
                    "professional_required_count": row["professional_required_count"],
                    "regular_required_count": row["regular_required_count"],
                    "temporary_required_count": row["temporary_required_count"],
                    "factors": row["demand_factors"],
                }
                for row in high_demands
            ],
            "staff_mix": {
                "regular_assignments": staff_mix["regular"],
                "temporary_assignments": staff_mix["temporary"],
                "protected_professional_assignments": protected_count,
            },
            "risks": version["risks"][:8],
        }

    def _weather_summary(self, week_start: str) -> list[str]:
        start_dates = self._week_dates(week_start)
        rows = [
            row
            for row in self.generator.seed["weather"]
            if row["date"] in start_dates and int(row.get("rain_level", 0)) >= 2
        ]
        return [
            f"{row['date']} {row['slot']} {row['weather_type']}，雨量等级{row['rain_level']}，需求侧上调线上拣货与到店集中度"
            for row in rows[:8]
        ]

    def _holiday_summary(self, week_start: str) -> list[str]:
        start_dates = self._week_dates(week_start)
        return [
            f"{row['date']} {row['holiday_name']}，按{row['holiday_type']}处理"
            for row in self.generator.seed["holidays"]
            if row["date"] in start_dates
        ]

    def _promotion_summary(self, week_start: str) -> list[str]:
        start_dates = self._week_dates(week_start)
        return [
            f"{row['date']} {self.generator.areas[row['area_code']]['name']} {row['description']}，系数{row['boost_factor']}"
            for row in self.generator.seed["promotions"]
            if row["date"] in start_dates
        ]

    def _week_dates(self, week_start: str) -> set[str]:
        from datetime import datetime, timedelta

        start = datetime.strptime(week_start, "%Y-%m-%d").date()
        return {(start + timedelta(days=offset)).isoformat() for offset in range(7)}

    def _is_support_question(self, message: str) -> bool:
        return "谁能" in message or "支援" in message or "候选" in message

    def _guess_area(self, message: str) -> str:
        if "水产" in message:
            return "aquatic"
        if "肉" in message:
            return "meat"
        if "收银" in message:
            return "cashier"
        if "补货" in message:
            return "replenishment"
        return "produce"

    def _first_friday(self, version: dict[str, Any] | None) -> str | None:
        if not version:
            return None
        for row in version["demand_results"]:
            if row["weekday"] == "Friday":
                return row["date"]
        return version["week_start"]
