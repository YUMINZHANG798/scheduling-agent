from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterator

import httpx

from app.core.config import get_settings
from app.data.store import SQLiteStore
from app.engine.scheduling import SchedulingGenerator
from app.prompts import (
    build_chat_messages,
    build_chat_stream_messages,
    build_fact_analysis_messages,
    build_schedule_explanation_messages,
    build_schedule_explanation_stream_messages,
)


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

        fact_response = self._fact_schedule_response(message, version, context)
        if fact_response:
            return self._enhance_fact_response(message, version, context, fact_response)

        llm_payload = self._structured_completion(
            self._chat_messages(message, version, context, history, candidates),
            fallback_message="LLM 调用失败，请检查模型配置或稍后重试。",
            fallback_sections=self._fallback_chat_sections(version, context, candidates),
            fallback_questions=self._default_follow_ups(message, candidates),
        )

        return {
            "intent": "llm_schedule_chat" if llm_payload["ok"] else "llm_unavailable",
            "is_fallback": not llm_payload["ok"],
            "message": llm_payload["message"],
            "candidates": candidates,
            "sections": llm_payload["sections"],
            "suggested_questions": llm_payload["suggested_questions"],
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

        yield from self.llm_client.stream(self._chat_stream_messages(message, version, context, history, candidates))

    def schedule_explanation(self, version_id: str) -> dict[str, Any]:
        version = self.store.get_version(version_id)
        if not version:
            return {
                "intent": "schedule_explanation",
                "is_fallback": True,
                "message": "没有找到这版班表，请先生成下周排班。",
                "candidates": [],
                "sections": [],
                "suggested_questions": [],
            }
        if not version["demand_results"] or not version["schedule_items"]:
            return {
                "intent": "schedule_version_incomplete",
                "is_fallback": False,
                "message": "这版班表缺少需求或排班明细，请重新生成下周排班。",
                "candidates": [],
                "sections": [],
                "suggested_questions": [],
            }

        llm_payload = self._structured_completion(
            self._schedule_explanation_messages(version),
            fallback_message="LLM 调用失败，请检查模型配置或稍后重试。",
            fallback_sections=self._fallback_schedule_sections(version),
            fallback_questions=[
                "哪些时段的高峰缺口最大？",
                "为什么这周临时工占比更高？",
                "哪几个风险最需要店长关注？",
            ],
        )
        return {
            "intent": "schedule_explanation",
            "is_fallback": not llm_payload["ok"],
            "message": llm_payload["message"],
            "candidates": [],
            "sections": llm_payload["sections"],
            "suggested_questions": llm_payload["suggested_questions"],
        }

    def stream_schedule_explanation(self, version_id: str) -> Iterator[str]:
        version = self.store.get_version(version_id)
        if not version:
            raise ValueError("VERSION_NOT_FOUND")
        if not version["demand_results"] or not version["schedule_items"]:
            raise ValueError("SCHEDULE_VERSION_INCOMPLETE")
        yield from self.llm_client.stream(self._schedule_explanation_stream_messages(version))

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
                "sections": [],
                "suggested_questions": [],
            }

        factors = "、".join(row["demand_factors"])
        sections = [
            {
                "title": "需求判断",
                "bullets": [
                    f"{row['date']} {row['slot']} 的 {row['area_name']} 需要 {row['required_count']} 人。",
                    f"其中专业岗 {row['professional_required_count']} 人，普通正式工 {row['regular_required_count']} 人，临时工 {row['temporary_required_count']} 人。",
                ],
            },
            {
                "title": "主要依据",
                "bullets": [f"需求分为 {row['demand_score']}，影响因素包括 {factors}。"],
            },
        ]
        return {
            "intent": "explain_demand",
            "is_fallback": True,
            "message": f"{row['date']} {row['slot']} {row['area_name']} 的需求主要由 {factors} 拉动，因此系统把它标记为 {row['priority']} 优先级。",
            "candidates": [],
            "sections": sections,
            "suggested_questions": [
                "这个时段为什么需要临时工？",
                "这个区域还有哪些高峰时段？",
            ],
        }

    def _structured_completion(
        self,
        messages: list[dict[str, str]],
        *,
        fallback_message: str,
        fallback_sections: list[dict[str, Any]],
        fallback_questions: list[str],
    ) -> dict[str, Any]:
        raw = self.llm_client.complete(messages)
        parsed = self._parse_structured_response(raw) if raw else None
        if parsed:
            return {"ok": True, **parsed}
        return {
            "ok": False,
            "message": raw or fallback_message,
            "sections": fallback_sections,
            "suggested_questions": fallback_questions,
        }

    def _parse_structured_response(self, raw: str | None) -> dict[str, Any] | None:
        if not raw:
            return None
        cleaned = raw.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
        if fenced:
            cleaned = fenced.group(1)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start:end + 1]
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return None

        message = str(payload.get("answer", "")).strip()
        if not message:
            return None
        raw_sections = payload.get("sections", [])
        sections: list[dict[str, Any]] = []
        for section in raw_sections[:4]:
            title = str(section.get("title", "")).strip()
            bullets = [str(item).strip() for item in section.get("bullets", []) if str(item).strip()]
            if title and bullets:
                sections.append({"title": title, "bullets": bullets[:4]})
        suggested_questions = [
            str(item).strip()
            for item in payload.get("suggested_questions", [])
            if str(item).strip()
        ][:4]
        return {
            "message": message,
            "sections": sections,
            "suggested_questions": suggested_questions,
        }

    def _chat_messages(
        self,
        message: str,
        version: dict[str, Any] | None,
        context: dict[str, Any],
        history: list[dict[str, str]],
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        schedule_context = self._chat_schedule_context(version, message, context) if version else {"status": "no_schedule"}
        safe_history = [
            {"role": row["role"], "content": row["content"]}
            for row in history[-8:]
            if row.get("role") in {"user", "assistant"} and row.get("content")
        ]
        return build_chat_messages(
            message=message,
            schedule_context=schedule_context,
            page_context=context,
            history=safe_history,
            candidates=candidates,
        )

    def _schedule_explanation_messages(self, version: dict[str, Any]) -> list[dict[str, str]]:
        return build_schedule_explanation_messages(schedule_context=self._schedule_context(version))

    def _chat_stream_messages(
        self,
        message: str,
        version: dict[str, Any] | None,
        context: dict[str, Any],
        history: list[dict[str, str]],
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        schedule_context = self._chat_schedule_context(version, message, context) if version else {"status": "no_schedule"}
        safe_history = [
            {"role": row["role"], "content": row["content"]}
            for row in history[-8:]
            if row.get("role") in {"user", "assistant"} and row.get("content")
        ]
        return build_chat_stream_messages(
            message=message,
            schedule_context=schedule_context,
            page_context=context,
            history=safe_history,
            candidates=candidates,
        )

    def _schedule_explanation_stream_messages(self, version: dict[str, Any]) -> list[dict[str, str]]:
        return build_schedule_explanation_stream_messages(schedule_context=self._schedule_context(version))

    def _enhance_fact_response(
        self,
        message: str,
        version: dict[str, Any] | None,
        page_context: dict[str, Any],
        fact_response: dict[str, Any],
    ) -> dict[str, Any]:
        if not version:
            return fact_response

        llm_payload = self._structured_completion(
            self._fact_analysis_messages(message, version, page_context, fact_response),
            fallback_message=fact_response["message"],
            fallback_sections=fact_response["sections"],
            fallback_questions=fact_response["suggested_questions"],
        )
        if not llm_payload["ok"]:
            return fact_response

        sections = fact_response["sections"][:]
        for section in llm_payload["sections"]:
            if section not in sections:
                sections.append(section)

        return {
            "intent": "schedule_fact_query",
            "is_fallback": False,
            "message": llm_payload["message"],
            "candidates": fact_response["candidates"],
            "sections": sections[:4],
            "suggested_questions": llm_payload["suggested_questions"] or fact_response["suggested_questions"],
        }

    def _chat_schedule_context(
        self,
        version: dict[str, Any],
        message: str,
        page_context: dict[str, Any],
    ) -> dict[str, Any]:
        context = self._schedule_context(version)
        query_focus = self._extract_query_focus(message, page_context)
        context["query_focus"] = query_focus
        context["relevant_schedule_items"] = self._relevant_schedule_items(version["schedule_items"], query_focus)
        if self._needs_schedule_directory(message):
            context["schedule_directory"] = self._schedule_directory(version["schedule_items"])
        return context

    def _fact_analysis_messages(
        self,
        message: str,
        version: dict[str, Any],
        page_context: dict[str, Any],
        fact_response: dict[str, Any],
    ) -> list[dict[str, str]]:
        return build_fact_analysis_messages(
            message=message,
            fact_response=fact_response,
            schedule_context=self._chat_schedule_context(version, message, page_context),
            page_context=page_context,
        )

    def _fact_schedule_response(
        self,
        message: str,
        version: dict[str, Any] | None,
        page_context: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not version or not version.get("schedule_items"):
            return None

        query_focus = self._extract_query_focus(message, page_context)
        if not self._is_schedule_fact_query(message, query_focus):
            return None

        items = self._relevant_schedule_items(version["schedule_items"], query_focus)
        if not items:
            return {
                "intent": "schedule_fact_query",
                "is_fallback": False,
                "message": "这版班表里没有查到匹配的排班记录。",
                "candidates": [],
                "sections": [{
                    "title": "查询条件",
                    "bullets": [self._focus_summary(query_focus) or "当前问题没有明确到员工、日期、区域或时段。"],
                }],
                "suggested_questions": [
                    "周一水产谁上班？",
                    "小宋都是哪几天上班？",
                    "周五晚上收银有哪些人？",
                ],
            }

        if query_focus.get("employee_name"):
            return self._employee_schedule_fact_response(query_focus, items)
        return self._schedule_slot_fact_response(query_focus, items)

    def _is_schedule_fact_query(self, message: str, query_focus: dict[str, Any]) -> bool:
        if query_focus.get("employee_name"):
            return any(keyword in message for keyword in ("上班", "排班", "哪天", "哪几天", "什么时候", "几点", "班"))
        if not any(query_focus.get(key) for key in ("date", "weekday", "slot", "area_code")):
            return False
        return any(keyword in message for keyword in ("谁", "哪些人", "有哪些人", "上班", "值班", "排班", "排了谁", "几个人"))

    def _employee_schedule_fact_response(
        self,
        query_focus: dict[str, Any],
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        employee_name = query_focus["employee_name"]
        ordered_items = sorted(items, key=lambda item: (item["date"], item["slot"], item["area_code"]))
        day_count = len({item["date"] for item in ordered_items})
        bullets = [
            f"{item['date']}（{self._weekday_label(item['weekday'])}）{item['slot']}：{item['area_name']}，{item['task_name']}。"
            for item in ordered_items[:12]
        ]
        if len(ordered_items) > 12:
            bullets.append(f"另有 {len(ordered_items) - 12} 条排班未展开。")

        return {
            "intent": "schedule_fact_query",
            "is_fallback": False,
            "message": f"{employee_name}本周共有 {len(ordered_items)} 条排班，覆盖 {day_count} 天。",
            "candidates": [],
            "sections": [{"title": f"{employee_name}排班明细", "bullets": bullets}],
            "suggested_questions": [
                f"{employee_name}有没有连续上班？",
                f"{employee_name}在哪些区域上班？",
                "周一水产谁上班？",
            ],
        }

    def _schedule_slot_fact_response(
        self,
        query_focus: dict[str, Any],
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ordered_items = sorted(items, key=lambda item: (item["date"], item["slot"], item["area_code"], item["employee_name"]))
        employees = sorted({item["employee_name"] for item in ordered_items})
        title = self._focus_summary(query_focus) or "匹配排班"
        bullets = [
            f"{item['date']}（{self._weekday_label(item['weekday'])}）{item['slot']} {item['area_name']}：{item['employee_name']}，{item['task_name']}。"
            for item in ordered_items[:16]
        ]
        if len(ordered_items) > 16:
            bullets.append(f"另有 {len(ordered_items) - 16} 条排班未展开。")

        return {
            "intent": "schedule_fact_query",
            "is_fallback": False,
            "message": f"查到 {len(ordered_items)} 条匹配排班，涉及 {len(employees)} 名员工：{'、'.join(employees[:8])}。",
            "candidates": [],
            "sections": [{"title": title, "bullets": bullets}],
            "suggested_questions": [
                "这些人分别负责什么任务？",
                "这个时段有没有风险？",
                "小宋都是哪几天上班？",
            ],
        }

    def _focus_summary(self, query_focus: dict[str, Any]) -> str:
        parts: list[str] = []
        if query_focus.get("employee_name"):
            parts.append(f"员工 {query_focus['employee_name']}")
        if query_focus.get("date"):
            parts.append(f"日期 {query_focus['date']}")
        elif query_focus.get("weekday"):
            parts.append(self._weekday_label(query_focus["weekday"]))
        if query_focus.get("slot"):
            parts.append(f"时段 {query_focus['slot']}")
        if query_focus.get("area_code"):
            parts.append(f"区域 {self._area_label(query_focus['area_code'])}")
        return "、".join(parts)

    def _weekday_label(self, weekday: str) -> str:
        return {
            "Monday": "周一",
            "Tuesday": "周二",
            "Wednesday": "周三",
            "Thursday": "周四",
            "Friday": "周五",
            "Saturday": "周六",
            "Sunday": "周日",
        }.get(weekday, weekday)

    def _area_label(self, area_code: str) -> str:
        return {
            "aquatic": "水产",
            "meat": "肉类",
            "produce": "果蔬",
            "cashier": "收银",
            "replenishment": "补货",
        }.get(area_code, area_code)

    def _extract_query_focus(self, message: str, page_context: dict[str, Any]) -> dict[str, Any]:
        focus: dict[str, Any] = {}
        weekday_map = {
            "周一": "Monday",
            "周二": "Tuesday",
            "周三": "Wednesday",
            "周四": "Thursday",
            "周五": "Friday",
            "周六": "Saturday",
            "周日": "Sunday",
            "周天": "Sunday",
            "星期一": "Monday",
            "星期二": "Tuesday",
            "星期三": "Wednesday",
            "星期四": "Thursday",
            "星期五": "Friday",
            "星期六": "Saturday",
            "星期日": "Sunday",
            "星期天": "Sunday",
        }
        area_map = {
            "水产": "aquatic",
            "肉": "meat",
            "肉类": "meat",
            "果蔬": "produce",
            "蔬果": "produce",
            "收银": "cashier",
            "前场": "cashier",
            "补货": "replenishment",
        }

        for label, weekday in weekday_map.items():
            if label in message:
                focus["weekday"] = weekday
                break
        for label, area_code in area_map.items():
            if label in message:
                focus["area_code"] = area_code
                break

        date_match = re.search(r"20\d{2}-\d{2}-\d{2}", message)
        if date_match:
            focus["date"] = date_match.group(0)
        slot_match = re.search(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}", message)
        if slot_match:
            focus["slot"] = slot_match.group(0).replace(" ", "")

        for employee in self.generator.employees.values():
            if employee["name"] in message:
                focus["employee_name"] = employee["name"]
                focus["employee_id"] = employee["id"]
                break

        uses_page_context = any(token in message for token in ("这个", "当前", "这里", "这天", "该", "这个时段", "这个区域"))
        is_employee_week_query = "employee_id" in focus and not uses_page_context
        if not is_employee_week_query:
            for key in ("date", "slot", "area_code", "task_code"):
                if key not in focus and page_context.get(key):
                    focus[key] = page_context[key]
        return focus

    def _relevant_schedule_items(
        self,
        schedule_items: list[dict[str, Any]],
        query_focus: dict[str, Any],
    ) -> list[dict[str, Any]]:
        def matches(item: dict[str, Any]) -> bool:
            for key in ("date", "weekday", "slot", "area_code", "employee_id"):
                if query_focus.get(key) and item.get(key) != query_focus[key]:
                    return False
            if query_focus.get("employee_name") and item.get("employee_name") != query_focus["employee_name"]:
                return False
            return True

        matched = [self._compact_schedule_item(item) for item in schedule_items if matches(item)]
        if matched:
            return matched[:30]
        if query_focus.get("employee_id") or query_focus.get("employee_name"):
            return []

        fallback = []
        for item in schedule_items:
            if query_focus.get("weekday") and item.get("weekday") != query_focus["weekday"]:
                continue
            if query_focus.get("area_code") and item.get("area_code") != query_focus["area_code"]:
                continue
            fallback.append(self._compact_schedule_item(item))
        return fallback[:30]

    def _schedule_directory(self, schedule_items: list[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
        directory: dict[str, dict[str, list[str]]] = {}
        for item in schedule_items:
            weekday = item["weekday"]
            area_code = item["area_code"]
            directory.setdefault(weekday, {}).setdefault(area_code, []).append(
                f"{item['slot']} {item['employee_name']} / {item['task_name']}"
            )
        return directory

    def _compact_schedule_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "date": item["date"],
            "weekday": item["weekday"],
            "slot": item["slot"],
            "area_code": item["area_code"],
            "area_name": item["area_name"],
            "task_name": item["task_name"],
            "employee_name": item["employee_name"],
            "employee_type": item["employee_type"],
        }

    def _needs_schedule_directory(self, message: str) -> bool:
        keywords = ("谁上班", "谁值班", "谁排班", "有哪些人", "哪天", "周", "星期", "时段", "几点", "排了谁")
        return any(keyword in message for keyword in keywords)

    def _fallback_chat_sections(
        self,
        version: dict[str, Any] | None,
        context: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        sections: list[dict[str, Any]] = []
        if version:
            sections.append({
                "title": "当前版本",
                "bullets": [
                    f"排班版本 {version['version_id']}，周起始日 {version['week_start']}。",
                    f"当前可见风险 {len(version['risks'])} 条，人工干预 {version['intervention_count']} 次。",
                ],
            })
        if context.get("date") or context.get("area_code"):
            context_bits = []
            if context.get("date"):
                context_bits.append(f"日期 {context['date']}")
            if context.get("slot"):
                context_bits.append(f"时段 {context['slot']}")
            if context.get("area_code"):
                context_bits.append(f"区域 {context['area_code']}")
            sections.append({"title": "当前问答上下文", "bullets": ["、".join(context_bits)]})
        if candidates:
            sections.append({
                "title": "可参考候选人",
                "bullets": [
                    f"{candidate['employee_name']}：{candidate['reason']}"
                    for candidate in candidates[:3]
                ],
            })
        return sections

    def _fallback_schedule_sections(self, version: dict[str, Any]) -> list[dict[str, Any]]:
        top_demands = sorted(version["demand_results"], key=lambda row: row["demand_score"], reverse=True)[:3]
        top_risks = version["risks"][:3]
        staff_mix = Counter(item["employee_type"] for item in version["schedule_items"])
        return [
            {
                "title": "排班概况",
                "bullets": [
                    f"正式工排班 {staff_mix['regular']} 次，临时工排班 {staff_mix['temporary']} 次。",
                    f"专业岗覆盖率 {round(self.generator.calculate_kpis(version['demand_results'], version['schedule_items'], version['risks'], version['intervention_count']).professional_coverage_rate * 100)}%。",
                ],
            },
            {
                "title": "高峰需求",
                "bullets": [
                    f"{row['date']} {row['slot']} {row['area_name']} 需求分 {row['demand_score']}，需 {row['required_count']} 人。"
                    for row in top_demands
                ],
            },
            {
                "title": "主要风险",
                "bullets": [risk["description"] for risk in top_risks] or ["当前没有突出风险。"],
            },
        ]

    def _default_follow_ups(self, message: str, candidates: list[dict[str, Any]]) -> list[str]:
        if candidates:
            return [
                "为什么优先推荐这些候选人？",
                "如果不使用临时工，风险会增加在哪里？",
                "这个区域本周还有哪些高峰时段？",
            ]
        if "风险" in message:
            return [
                "这些风险里哪个最需要优先处理？",
                "哪些风险和专业岗覆盖有关？",
            ]
        return [
            "这周哪些时段最缺人？",
            "为什么这个区域排了更多正式工？",
            "临时工主要补在哪些时段？",
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
            "staffing_summary": self._staffing_summary(version["week_start"], version["schedule_items"]),
            "risks": version["risks"][:8],
        }

    def _staffing_summary(self, week_start: str, schedule_items: list[dict[str, Any]]) -> dict[str, Any]:
        active_employees = {
            employee_id: employee
            for employee_id, employee in self.generator.employees.items()
            if employee.get("is_active")
        }
        scheduled_ids = {
            item["employee_id"]
            for item in schedule_items
            if item.get("employee_id") in active_employees
        }
        submitted_leave_ids = {
            row["employee_id"]
            for row in self.generator.seed["employee_weekly_leave"]
            if row["week_start"] == week_start
            and row["employee_id"] in active_employees
            and row.get("created_at") != "2026-07-10T08:00:00Z"
        }
        leave_ids = submitted_leave_ids - scheduled_ids

        def bucket(employee_type: str | None = None) -> dict[str, int]:
            scoped_ids = {
                employee_id
                for employee_id, employee in active_employees.items()
                if employee_type is None or employee["employee_type"] == employee_type
            }
            scheduled_scoped = scheduled_ids & scoped_ids
            leave_scoped = leave_ids & scoped_ids
            return {
                "total_count": len(scoped_ids),
                "scheduled_count": len(scheduled_scoped),
                "unscheduled_count": len(scoped_ids) - len(scheduled_scoped) - len(leave_scoped),
                "leave_count": len(leave_scoped),
            }

        return {
            "total": bucket(),
            "regular": bucket("regular"),
            "temporary": bucket("temporary"),
        }

    def _weather_summary(self, week_start: str) -> list[str]:
        start_dates = self._week_dates(week_start)
        rows = [
            row
            for row in self.generator.seed["weather"]
            if row["date"] in start_dates and int(row.get("rain_level", 0)) >= 2
        ]
        return [
            f"{row['date']} {row['slot']} {row['weather_type']}，雨量等级 {row['rain_level']}，需求侧上调线上拣货与到店集中度"
            for row in rows[:8]
        ]

    def _holiday_summary(self, week_start: str) -> list[str]:
        start_dates = self._week_dates(week_start)
        return [
            f"{row['date']} {row['holiday_name']}，按 {row['holiday_type']} 处理"
            for row in self.generator.seed["holidays"]
            if row["date"] in start_dates
        ]

    def _promotion_summary(self, week_start: str) -> list[str]:
        start_dates = self._week_dates(week_start)
        return [
            f"{row['date']} {self.generator.areas[row['area_code']]['name']} {row['description']}，系数 {row['boost_factor']}"
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
