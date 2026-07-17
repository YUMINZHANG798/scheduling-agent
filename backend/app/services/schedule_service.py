from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.data.store import SQLiteStore
from app.engine.scheduling import SKILL_RANK, SchedulingGenerator
from app.models.schemas import (
    GenerateScheduleRequest,
    LeavePreferenceUpdateRequest,
    ModifyScheduleRequest,
    ModifyScheduleResponse,
    ScheduleResponse,
)
from app.services.demand_service import DemandService


class ScheduleService:
    def __init__(
        self,
        store: SQLiteStore | None = None,
        demand_service: DemandService | None = None,
        generator: SchedulingGenerator | None = None,
    ) -> None:
        self.settings = get_settings()
        self.store = store or SQLiteStore()
        self.demand_service = demand_service or DemandService()
        self.generator = generator or SchedulingGenerator()

    def generate(self, request: GenerateScheduleRequest) -> ScheduleResponse:
        self._validate_generation_request(request)
        demand_results, insights = self.demand_service.calculate_week(request.week_start)
        payload = self.generator.generate(request.week_start, demand_results)
        payload = self._merge_frozen_schedule(request, payload)
        payload["demand_insights"] = insights
        payload["staffing_summary"] = self._staffing_summary(payload["week_start"], payload["schedule_items"])
        self.store.save_version(payload)
        return ScheduleResponse(**payload)

    def reset_demo(self) -> None:
        self.store.reset()
        self.ensure_demo_history(force=True)

    def ensure_demo_history(self, force: bool = False) -> None:
        profiles = [
            {
                "week_start": "2026-06-15",
                "generated_at": "2026-06-14T13:30:00Z",
                "summary": "雨天线上订单波动周",
                "adjustments": [
                    {"weekday": "Wednesday", "slots": {"10:00-11:00", "11:00-12:00", "18:00-19:00"}, "areas": {"produce", "cashier"}, "factor": 1.08, "label": "阵雨带来线上拣货集中"},
                    {"weekday": "Friday", "slots": {"17:00-18:00", "18:00-19:00", "19:00-20:00"}, "areas": {"aquatic", "meat", "produce"}, "factor": 1.07, "label": "周五晚高峰提前备货"},
                ],
            },
            {
                "week_start": "2026-06-22",
                "generated_at": "2026-06-21T13:20:00Z",
                "summary": "社区团购提货增长周",
                "adjustments": [
                    {"weekday": "Thursday", "slots": {"16:00-17:00", "17:00-18:00", "18:00-19:00"}, "areas": {"produce", "replenishment"}, "factor": 1.12, "label": "社区团购提货集中"},
                    {"weekday": "Saturday", "slots": {"10:00-11:00", "11:00-12:00", "12:00-13:00"}, "areas": {"meat"}, "factor": 1.08, "label": "周末肉类备餐需求上浮"},
                ],
            },
            {
                "week_start": "2026-06-29",
                "generated_at": "2026-06-28T13:10:00Z",
                "summary": "月末平峰控工时周",
                "adjustments": [
                    {"weekday": "Monday", "slots": set(SLOTS_FOR_HISTORY), "areas": set(AREA_CODES_FOR_HISTORY), "factor": 0.94, "label": "月末平峰控工时"},
                    {"weekday": "Tuesday", "slots": set(SLOTS_FOR_HISTORY), "areas": set(AREA_CODES_FOR_HISTORY), "factor": 0.95, "label": "工作日客流回落"},
                    {"weekday": "Sunday", "slots": {"17:00-18:00", "18:00-19:00"}, "areas": {"aquatic", "produce"}, "factor": 1.06, "label": "周日晚间补货小高峰"},
                ],
            },
            {
                "week_start": "2026-07-06",
                "generated_at": "2026-07-05T13:25:00Z",
                "summary": "暑期周末家庭采购周",
                "adjustments": [
                    {"weekday": "Saturday", "slots": {"10:00-11:00", "11:00-12:00", "17:00-18:00", "18:00-19:00"}, "areas": {"aquatic", "meat", "produce"}, "factor": 1.13, "label": "暑期家庭采购上浮"},
                    {"weekday": "Sunday", "slots": {"10:00-11:00", "11:00-12:00", "18:00-19:00"}, "areas": {"aquatic", "meat"}, "factor": 1.1, "label": "周末家庭备餐高峰"},
                ],
            },
            {
                "week_start": "2026-07-13",
                "generated_at": "2026-07-12T13:40:00Z",
                "summary": "本周雨天促销预测周",
                "adjustments": [],
            },
        ]
        expected_ids = {f"hist_{profile['week_start'].replace('-', '')}" for profile in profiles}
        existing_ids = {row["id"] for row in self.store.list_versions(self.settings.store_id)}
        if not force and expected_ids.issubset(existing_ids):
            return

        for index, profile in enumerate(profiles, 1):
            demand_results, insights = self.demand_service.calculate_week(profile["week_start"])
            demand_results = self._apply_historical_profile(demand_results, profile["adjustments"])
            insights = self._insights_from_demand(demand_results)
            payload = self.generator.generate(profile["week_start"], demand_results)
            payload["version_id"] = f"hist_{profile['week_start'].replace('-', '')}"
            payload["generated_at"] = profile["generated_at"]
            payload["agent_summary"] = (
                f"历史排班样本{index}：{profile['summary']}。系统基于历史销售、客流、线上订单、天气/周末/促销因素生成，"
                f"专业岗覆盖率{payload['kpis']['professional_coverage_rate']:.0%}，区域保底达成率{payload['kpis']['baseline_achievement_rate']:.0%}。"
            )
            payload["agent_fallback"] = False
            payload["demand_insights"] = insights
            payload["schedule_items"] = [
                {**item, "version_id": payload["version_id"]}
                for item in payload["schedule_items"]
            ]
            payload["staffing_summary"] = self._staffing_summary(payload["week_start"], payload["schedule_items"])
            self.store.save_version(payload)

    def get(self, version_id: str) -> ScheduleResponse | None:
        version = self.store.get_version(version_id)
        if not version:
            return None
        kpis = self.generator.calculate_kpis(
            version["demand_results"],
            version["schedule_items"],
            version["risks"],
            version["intervention_count"],
        ).model_dump()
        insights = sorted(
            [
                {key: row[key] for key in [
                    "date",
                    "weekday",
                    "slot",
                    "area_code",
                    "area_name",
                    "required_count",
                    "professional_required_count",
                    "regular_required_count",
                    "temporary_required_count",
                    "demand_score",
                    "demand_factors",
                    "priority",
                    "confidence",
                ]}
                for row in version["demand_results"]
                if row["priority"] == "high"
            ],
            key=lambda row: row["demand_score"],
            reverse=True,
        )[:12]
        return ScheduleResponse(
            version_id=version["version_id"],
            store_id=version["store_id"],
            store_name=self.settings.store_name,
            week_start=version["week_start"],
            generated_at=version["generated_at"],
            agent_summary=version["agent_summary"],
            agent_fallback=version["agent_fallback"],
            demand_insights=insights,
            demand_results=version["demand_results"],
            schedule_items=version["schedule_items"],
            kpis=kpis,
            staffing_summary=version.get("staffing_summary") or self._staffing_summary(version["week_start"], version["schedule_items"]),
            risks=version["risks"],
        )

    def versions(self, store_id: str | None = None, week_start: str | None = None) -> list[dict[str, Any]]:
        return [
            {
                **row,
                "store_name": self.settings.store_name,
                "is_latest": index == 0,
            }
            for index, row in enumerate(
                row for row in self.store.list_versions(store_id, week_start) if row["schedule_item_count"] > 0
            )
        ]

    def modify(self, version_id: str, item_id: str, request: ModifyScheduleRequest) -> ModifyScheduleResponse | None:
        version = self.store.get_version(version_id)
        if not version:
            return None
        item = next((row for row in version["schedule_items"] if row["id"] == item_id), None)
        if not item:
            return None
        before = dict(item)
        after = {**item, **request.after, "source": "manual", "explanation": request.reason_text or "店长手动调整"}
        employee = self.generator.employees.get(after["employee_id"])
        if employee:
            after["employee_name"] = employee["name"]
            after["employee_type"] = employee["employee_type"]
            after["assignment_type"] = "temporary" if employee["employee_type"] == "temporary" else "regular"
        area = self.generator.areas.get(after["area_code"])
        if area:
            after["area_name"] = area["name"]
        task = self.generator.tasks.get((after["area_code"], after["task_code"]))
        if task:
            after["task_name"] = task["task_name"]
            after["is_protected"] = int(task["is_professional"] and after["employee_type"] == "regular")

        updated_items = [after if row["id"] == item_id else row for row in version["schedule_items"]]
        risks = self.generator.detect_risks(version_id, version["demand_results"], updated_items)
        severe = [risk for risk in risks if risk["level"] == "critical"]
        if severe and not request.force:
            record = self._record(version_id, item_id, before, after, request)
            return ModifyScheduleResponse(
                item=after,
                risks=severe,
                kpis=self.generator.calculate_kpis(version["demand_results"], version["schedule_items"], version["risks"], version["intervention_count"]),
                intervention_record=record,
                requires_confirmation=True,
            )

        record = self._record(version_id, item_id, before, after, request)
        self.store.update_schedule_item(version_id, item_id, after)
        self.store.add_intervention({**record.model_dump(), "version_id": version_id})
        new_intervention_count = version["intervention_count"] + 1
        kpis = self.generator.calculate_kpis(version["demand_results"], updated_items, risks, new_intervention_count)
        return ModifyScheduleResponse(
            item=after,
            risks=risks,
            kpis=kpis,
            intervention_record=record,
            requires_confirmation=False,
        )

    def preferences(self, version_id: str, employee_id: str | None = None) -> list[dict[str, Any]] | None:
        version = self.store.get_version(version_id)
        if not version:
            return None
        rows = [
            {
                **row,
                "employee_name": self.generator.employees[row["employee_id"]]["name"],
                "default_shift_type": self.generator.employees[row["employee_id"]].get("regular_shift_type"),
            }
            for row in self.generator.seed["employee_weekly_preferences"]
            if row["week_start"] == version["week_start"] and (employee_id is None or row["employee_id"] == employee_id)
        ]
        return rows

    def leave_preferences(self, version_id: str, employee_id: str | None = None) -> list[dict[str, Any]] | None:
        version = self.store.get_version(version_id)
        if not version:
            return None
        return [
            {**row, "employee_name": self.generator.employees[row["employee_id"]]["name"]}
            for row in self.generator.seed["employee_weekly_leave"]
            if row["week_start"] == version["week_start"] and (employee_id is None or row["employee_id"] == employee_id)
        ]

    def leave_resolution(self, version_id: str) -> list[dict[str, Any]] | None:
        version = self.store.get_version(version_id)
        if not version:
            return None
        return self.generator._leave_payload(version["week_start"], self.generator.resolve_leave(version["week_start"]))

    def kpis(self, version_id: str) -> dict[str, Any] | None:
        version = self.store.get_version(version_id)
        if not version:
            return None
        return self.generator.calculate_kpis(
            version["demand_results"],
            version["schedule_items"],
            version["risks"],
            version["intervention_count"],
        ).model_dump()

    def risks(self, version_id: str) -> list[dict[str, Any]] | None:
        version = self.store.get_version(version_id)
        if not version:
            return None
        return version["risks"]

    def interventions(self, version_id: str) -> list[dict[str, Any]] | None:
        if not self.store.get_version(version_id):
            return None
        return self.store.interventions(version_id)

    def regular_employees(self) -> list[dict[str, Any]]:
        areas = self.generator.areas
        employees = [
            {
                "employee_id": employee["id"],
                "employee_name": employee["name"],
                "area_code": employee["main_area"],
                "area_name": areas[employee["main_area"]]["name"],
                "is_protected": employee.get("is_protected", 0),
            }
            for employee in self.generator.employees.values()
            if employee["employee_type"] == "regular" and employee["is_active"]
        ]
        return sorted(employees, key=lambda row: (AREA_SORT_ORDER.get(row["area_code"], 99), -row["is_protected"], row["employee_id"]))

    def upsert_leave_preference(self, request: LeavePreferenceUpdateRequest) -> dict[str, Any]:
        employee = self.generator.employees.get(request.employee_id)
        if not employee or employee["employee_type"] != "regular":
            raise ValueError("EMPLOYEE_NOT_FOUND")
        start = datetime.strptime(request.week_start, "%Y-%m-%d").date()
        if start.weekday() != 0:
            raise ValueError("INVALID_WEEK_START")
        requested_date = self._day_off_date(request.week_start, request.preferred_day_off)
        if requested_date <= self._business_today():
            raise ValueError("LEAVE_TOO_LATE")

        rows = self.generator.seed["employee_weekly_leave"]
        original_rows = [dict(row) for row in rows]
        candidate_rows = [dict(row) for row in rows]
        self._apply_leave_preference(candidate_rows, request)

        self.generator.seed["employee_weekly_leave"] = candidate_rows
        try:
            demand_results, _ = self.demand_service.calculate_week(request.week_start)
            feasibility_issues = self._leave_feasibility_issues(
                request,
                employee,
                requested_date,
                candidate_rows,
                demand_results,
            )
            if feasibility_issues:
                raise ValueError(f"LEAVE_REJECTED:{feasibility_issues[0]}")
            simulation = self.generator.generate(request.week_start, demand_results)
            requested_key = (requested_date.isoformat(), employee["main_area"])
            approved_on_requested_day = request.employee_id in self.generator.resolve_leave(request.week_start).get(requested_key, set())
            if not approved_on_requested_day:
                raise ValueError("LEAVE_REJECTED:该休假会导致同区域当天可用人员低于预测需求，系统不批准。")
            if simulation["kpis"]["professional_coverage_rate"] < 1 or simulation["kpis"]["baseline_achievement_rate"] < 1:
                raise ValueError("LEAVE_REJECTED:模拟重排后无法满足专业岗或区域保底，系统不批准。")
        except Exception:
            self.generator.seed["employee_weekly_leave"] = original_rows
            raise

        rows[:] = candidate_rows
        row = next(
            item
            for item in rows
            if item["employee_id"] == request.employee_id and item["week_start"] == request.week_start
        )
        self.generator.seed["employee_weekly_leave"] = rows

        leave_file = self.generator.seed_loader.seed_dir / "employee_weekly_leave.json"
        with leave_file.open("w", encoding="utf-8") as file:
            json.dump(rows, file, ensure_ascii=False, indent=2)

        return {
            **row,
            "employee_name": employee["name"],
            "area_code": employee["main_area"],
            "area_name": self.generator.areas[employee["main_area"]]["name"],
            "effective_date": requested_date.isoformat(),
            "message": "休假申请已保存，重新生成班表时会从休假日开始重排，之前日期保持不变。",
        }

    def _apply_leave_preference(
        self,
        rows: list[dict[str, Any]],
        request: LeavePreferenceUpdateRequest,
    ) -> None:
        existing = next(
            (
                row
                for row in rows
                if row["employee_id"] == request.employee_id and row["week_start"] == request.week_start
            ),
            None,
        )
        created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if existing:
            existing["preferred_day_off"] = request.preferred_day_off
            existing["created_at"] = created_at
        else:
            rows.append({
                "id": f"lv_{len(rows) + 1:04d}",
                "employee_id": request.employee_id,
                "week_start": request.week_start,
                "preferred_day_off": request.preferred_day_off,
                "created_at": created_at,
            })

    def _leave_feasibility_issues(
        self,
        request: LeavePreferenceUpdateRequest,
        employee: dict[str, Any],
        requested_date: date,
        candidate_rows: list[dict[str, Any]],
        demand_results: list[dict[str, Any]],
    ) -> list[str]:
        area_code = employee["main_area"]
        leave_ids = self._leave_employee_ids_for_date(request.week_start, requested_date, area_code, candidate_rows)
        active_regular_ids = {
            emp["id"]
            for emp in self.generator.employees.values()
            if emp["employee_type"] == "regular"
            and emp["main_area"] == area_code
            and emp["is_active"]
        }
        available_regular_ids = active_regular_ids - leave_ids
        issues: list[str] = []

        area_demands = [
            row
            for row in demand_results
            if row["date"] == requested_date.isoformat() and row["area_code"] == area_code
        ]
        max_regular_required = max((row.get("regular_required_count", 0) for row in area_demands), default=0)
        if len(available_regular_ids) < max_regular_required:
            issues.append(
                f"{requested_date.isoformat()} {self.generator.areas[area_code]['name']}预测至少需要{max_regular_required}名普通正式工，扣除请假后仅剩{len(available_regular_ids)}名。"
            )

        for demand in area_demands:
            professional_required = demand.get("professional_required_count", 0)
            if professional_required <= 0:
                continue
            qualified_available = self._qualified_available_professionals(
                area_code,
                demand["task_code"],
                available_regular_ids,
            )
            if qualified_available < professional_required:
                issues.append(
                    f"{requested_date.isoformat()} {demand['slot']} {demand['area_name']}{demand['task_name']}预测需要{professional_required}名专业师傅，扣除请假后仅剩{qualified_available}名。"
                )

        return issues

    def _leave_employee_ids_for_date(
        self,
        week_start: str,
        requested_date: date,
        area_code: str,
        rows: list[dict[str, Any]],
    ) -> set[str]:
        leave_ids: set[str] = set()
        for row in rows:
            if row["week_start"] != week_start:
                continue
            emp = self.generator.employees.get(row["employee_id"])
            if not emp or emp["main_area"] != area_code:
                continue
            if self._day_off_date(week_start, row["preferred_day_off"]) == requested_date:
                leave_ids.add(row["employee_id"])
        return leave_ids

    def _qualified_available_professionals(
        self,
        area_code: str,
        task_code: str,
        available_regular_ids: set[str],
    ) -> int:
        task = self.generator.tasks[(area_code, task_code)]
        count = 0
        for employee_id in available_regular_ids:
            skill = self.generator.skills.get((employee_id, area_code, task_code))
            if skill and SKILL_RANK[skill["skill_level"]] >= SKILL_RANK[task["min_skill_level"]]:
                count += 1
        return count

    def _apply_historical_profile(
        self,
        demand_results: list[dict[str, Any]],
        adjustments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not adjustments:
            return demand_results

        adjusted_rows: list[dict[str, Any]] = []
        for row in demand_results:
            updated = dict(row)
            factor = 1.0
            extra_labels: list[str] = []
            for adjustment in adjustments:
                if row["weekday"] != adjustment["weekday"]:
                    continue
                if row["slot"] not in adjustment["slots"]:
                    continue
                if row["area_code"] not in adjustment["areas"]:
                    continue
                factor *= float(adjustment["factor"])
                extra_labels.append(adjustment["label"])

            if factor != 1.0:
                final_score = max(25, min(100, round(row["demand_score"] * factor)))
                task = next(
                    task
                    for task in self.demand_service.tasks_by_area[row["area_code"]]
                    if task["task_code"] == row["task_code"]
                )
                required_count = self.demand_service._required_count(
                    self.demand_service.areas[row["area_code"]],
                    final_score,
                    task["is_professional"],
                )
                labor_breakdown = self.demand_service._labor_breakdown(
                    self.demand_service.areas[row["area_code"]],
                    task,
                    final_score,
                    required_count,
                )
                updated.update({
                    "required_count": required_count,
                    **labor_breakdown,
                    "demand_score": final_score,
                    "demand_factors": [*row["demand_factors"], *extra_labels],
                    "priority": "high" if final_score >= 78 else ("medium" if final_score >= 55 else "low"),
                    "confidence": "high" if len(row["demand_factors"]) + len(extra_labels) >= 3 else "medium",
                })
            adjusted_rows.append(updated)
        return adjusted_rows

    def _insights_from_demand(self, demand_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        fields = [
            "date",
            "weekday",
            "slot",
            "area_code",
            "area_name",
            "required_count",
            "professional_required_count",
            "regular_required_count",
            "temporary_required_count",
            "demand_score",
            "demand_factors",
            "priority",
            "confidence",
        ]
        return sorted(
            [{key: row[key] for key in fields} for row in demand_results if row["priority"] == "high"],
            key=lambda row: row["demand_score"],
            reverse=True,
        )[:12]

    def _validate_generation_request(self, request: GenerateScheduleRequest) -> None:
        if request.store_id != self.settings.store_id:
            raise ValueError("STORE_NOT_FOUND")
        start = datetime.strptime(request.week_start, "%Y-%m-%d").date()
        if start.weekday() != 0:
            raise ValueError("INVALID_WEEK_START")

    def _record(
        self,
        version_id: str,
        item_id: str,
        before: dict[str, Any],
        after: dict[str, Any],
        request: ModifyScheduleRequest,
    ):
        from app.models.schemas import InterventionRecord

        return InterventionRecord(
            id=f"ir_{uuid4().hex[:8]}",
            schedule_item_id=item_id,
            before=before,
            after=after,
            reason_code=request.reason_code,
            reason_text=request.reason_text,
            created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )

    def _merge_frozen_schedule(
        self,
        request: GenerateScheduleRequest,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        previous = self.store.get_latest_version(request.store_id, request.week_start)
        freeze_before = self._freeze_before_date(request, bool(previous))
        if not previous or not freeze_before:
            return payload

        frozen_items = [
            {**item, "version_id": payload["version_id"]}
            for item in previous["schedule_items"]
            if datetime.strptime(item["date"], "%Y-%m-%d").date() < freeze_before
        ]
        regenerated_items = [
            item
            for item in payload["schedule_items"]
            if datetime.strptime(item["date"], "%Y-%m-%d").date() >= freeze_before
        ]
        merged_items = []
        for index, item in enumerate(frozen_items + regenerated_items, 1):
            merged_items.append({**item, "id": f"si_{index:04d}", "version_id": payload["version_id"]})
        payload["schedule_items"] = merged_items
        payload["risks"] = self.generator.detect_risks(payload["version_id"], payload["demand_results"], merged_items)
        payload["kpis"] = self.generator.calculate_kpis(payload["demand_results"], merged_items, payload["risks"], 0).model_dump()
        payload["agent_summary"] = (
            f"{payload['agent_summary']} 已冻结{freeze_before.isoformat()}之前的既有排班，仅重排可调整日期。"
        )
        return payload

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

    def _freeze_before_date(self, request: GenerateScheduleRequest, has_previous: bool) -> date | None:
        start = datetime.strptime(request.week_start, "%Y-%m-%d").date()
        end = start + timedelta(days=6)
        if request.reschedule_from:
            freeze_before = datetime.strptime(request.reschedule_from, "%Y-%m-%d").date()
            if start <= freeze_before <= end:
                return freeze_before
        today = self._business_today()
        if has_previous and start <= today <= end:
            return today
        return None

    def _business_today(self) -> date:
        return datetime.strptime(self.settings.business_today, "%Y-%m-%d").date()

    def _day_off_date(self, week_start: str, day_off: str) -> date:
        start = datetime.strptime(week_start, "%Y-%m-%d").date()
        return start + timedelta(days=WEEKDAY_NAMES.index(day_off))


AREA_SORT_ORDER = {
    "aquatic": 1,
    "meat": 2,
    "produce": 3,
    "cashier": 4,
    "replenishment": 5,
}

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
AREA_CODES_FOR_HISTORY = {"aquatic", "meat", "produce", "cashier", "replenishment"}
SLOTS_FOR_HISTORY = {
    "08:00-09:00",
    "09:00-10:00",
    "10:00-11:00",
    "11:00-12:00",
    "12:00-13:00",
    "13:00-14:00",
    "14:00-15:00",
    "15:00-16:00",
    "16:00-17:00",
    "17:00-18:00",
    "18:00-19:00",
    "19:00-20:00",
    "20:00-21:00",
    "21:00-22:00",
}
