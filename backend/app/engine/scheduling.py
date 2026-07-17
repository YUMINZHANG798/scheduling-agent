from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.data.seed_loader import SeedLoader
from app.models.schemas import KpiResult


WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SHIFT_SLOTS = {
    "morning": "08:00-16:00",
    "midday": "10:00-18:00",
    "evening": "14:00-22:00",
    "split": "08:00-12:00,17:00-21:00",
}
SLOT_RANGES = {
    "08:00-16:00": [(8, 16)],
    "10:00-18:00": [(10, 18)],
    "14:00-22:00": [(14, 22)],
    "08:00-12:00,17:00-21:00": [(8, 12), (17, 21)],
    "18:00-21:00": [(18, 21)],
    "18:00-22:00": [(18, 22)],
    "10:00-14:00": [(10, 14)],
    "14:00-18:00": [(14, 18)],
    "16:00-21:00": [(16, 21)],
    "17:00-22:00": [(17, 22)],
}
SKILL_RANK = {"S": 4, "A": 3, "B": 2, "C": 1}


class SchedulingGenerator:
    def __init__(self, seed_loader: SeedLoader | None = None) -> None:
        self.settings = get_settings()
        self.seed_loader = seed_loader or SeedLoader()
        self.seed = self.seed_loader.all()
        self.areas = {row["code"]: row for row in self.seed["areas"]}
        self.tasks = {(row["area_code"], row["task_code"]): row for row in self.seed["area_tasks"]}
        self.tasks_by_area = self._tasks_by_area()
        self.employees = {row["id"]: row for row in self.seed["employees"]}
        self.skills = self._skills()

    def generate(self, week_start: str, demand_results: list[dict[str, Any]]) -> dict[str, Any]:
        version_id = f"sch_{uuid4().hex[:8]}"
        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        leave_resolution = self.resolve_leave(week_start)
        preferences = self._preferences(week_start)
        schedule_items: list[dict[str, Any]] = []
        employee_hours: Counter[str] = Counter()
        employee_days: Counter[str] = Counter()
        demand_by_day_area = self._demand_by_day_area(demand_results)
        regular_pool_by_area = self._regular_pool_by_area(demand_results)

        start = datetime.strptime(week_start, "%Y-%m-%d").date()
        for offset in range(7):
            current = start + timedelta(days=offset)
            current_text = current.isoformat()
            weekday = WEEKDAY_NAMES[current.weekday()]
            for area_code, area in self.areas.items():
                approved_leave = leave_resolution.get((current_text, area_code), set())
                regulars = [
                    emp
                    for emp in self.employees.values()
                    if emp["employee_type"] == "regular"
                    and emp["main_area"] == area_code
                    and emp["id"] in regular_pool_by_area.get(area_code, set())
                    and emp["id"] not in approved_leave
                    and emp["is_active"]
                ]
                baseline_min = int(area["baseline_min"])
                day_demands = demand_by_day_area.get((current_text, area_code), [])
                professional_total = [emp for emp in regulars if self._has_professional_skill(emp["id"], area_code)]
                needed_professionals = self._daily_professional_target(area_code, day_demands, len(professional_total))
                target = self._daily_regular_target(
                    area_code,
                    area,
                    day_demands,
                    len(regulars),
                    needed_professionals,
                )
                professional_total.sort(
                    key=lambda emp: (
                        employee_days[emp["id"]],
                        employee_hours[emp["id"]],
                        self._rotation_index(emp["id"], offset),
                    )
                )
                scheduled_regulars = professional_total[:needed_professionals]
                selected_ids = {emp["id"] for emp in scheduled_regulars}
                remaining_regulars = [emp for emp in regulars if emp["id"] not in selected_ids]
                remaining_regulars.sort(
                    key=lambda emp: (
                        employee_days[emp["id"]],
                        employee_hours[emp["id"]],
                        bool(emp.get("is_protected")),
                        self._rotation_index(emp["id"], offset),
                    )
                )
                for emp in remaining_regulars:
                    if len(scheduled_regulars) >= target:
                        break
                    scheduled_regulars.append(emp)
                professional_capable = [
                    emp
                    for emp in scheduled_regulars
                    if self._has_professional_skill(emp["id"], area_code)
                ]
                professional_shift_plan = self._professional_shift_plan(len(professional_capable))
                professional_shift_index = 0
                non_sole_position = 0
                non_professional_shift_plan = self._non_professional_shift_plan(baseline_min, day_demands)
                for position, emp in enumerate(scheduled_regulars):
                    shift_type = preferences.get(emp["id"], emp.get("regular_shift_type") or "morning")
                    if self._has_professional_skill(emp["id"], area_code) and len(professional_capable) >= 2:
                        shift_type = professional_shift_plan[professional_shift_index]
                        professional_shift_index += 1
                    elif self._has_professional_skill(emp["id"], area_code):
                        shift_type = "split"
                    elif non_sole_position < len(non_professional_shift_plan):
                        shift_type = non_professional_shift_plan[non_sole_position]
                        non_sole_position += 1
                    if shift_type == "rotating":
                        shift_type = "morning" if (offset + int(emp["id"].split("_")[1])) % 2 == 0 else "evening"
                    task = self._regular_task_for_shift(
                        emp["id"],
                        area_code,
                        current_text,
                        position,
                        shift_type,
                        day_demands,
                    )
                    slot = SHIFT_SLOTS.get(shift_type, SHIFT_SLOTS["morning"])
                    hours = self._slot_hours(slot)
                    employee_hours[emp["id"]] += hours
                    employee_days[emp["id"]] += 1
                    schedule_items.append(
                        self._item(
                            version_id,
                            len(schedule_items) + 1,
                            current.isoformat(),
                            weekday,
                            slot,
                            area_code,
                            task["task_code"],
                            emp,
                            "regular",
                            shift_type,
                            hours,
                            int(task["is_professional"]),
                            f"{emp['name']}为{area['name']}正式工，按{self._shift_label(shift_type)}主要负责{task['task_name']}；正式工不跨区排班，专业师傅同时承担关键时段兜底。",
                        )
                    )

        self._assign_temporary_support(version_id, demand_results, schedule_items, employee_hours)
        risks = self.detect_risks(version_id, demand_results, schedule_items)
        kpis = self.calculate_kpis(demand_results, schedule_items, risks, 0).model_dump()
        summary = self._summary(kpis, risks)
        return {
            "version_id": version_id,
            "store_id": self.settings.store_id,
            "store_name": self.settings.store_name,
            "week_start": week_start,
            "generated_at": generated_at,
            "agent_summary": summary,
            "agent_fallback": True,
            "demand_results": demand_results,
            "schedule_items": schedule_items,
            "risks": risks,
            "kpis": kpis,
            "leave_resolution": self._leave_payload(week_start, leave_resolution),
        }

    def resolve_leave(self, week_start: str) -> dict[tuple[str, str], set[str]]:
        start = datetime.strptime(week_start, "%Y-%m-%d").date()
        leave_by_day_area: dict[tuple[str, str], list[str]] = defaultdict(list)
        regular_ids_by_area: dict[str, list[str]] = defaultdict(list)
        professional_ids_by_area: dict[str, set[str]] = defaultdict(set)
        for emp in self.employees.values():
            if emp["employee_type"] == "regular" and emp["is_active"]:
                regular_ids_by_area[emp["main_area"]].append(emp["id"])
                if self._has_professional_skill(emp["id"], emp["main_area"]):
                    professional_ids_by_area[emp["main_area"]].add(emp["id"])
        for row in self.seed["employee_weekly_leave"]:
            if row["week_start"] != week_start:
                continue
            emp = self.employees.get(row["employee_id"])
            if not emp or emp["employee_type"] != "regular":
                continue
            day_offset = WEEKDAY_NAMES.index(row["preferred_day_off"])
            day = (start + timedelta(days=day_offset)).isoformat()
            leave_by_day_area[(day, emp["main_area"])].append(emp["id"])

        approved: dict[tuple[str, str], set[str]] = defaultdict(set)
        for key, emp_ids in leave_by_day_area.items():
            _, area_code = key
            capacity = self._daily_leave_capacity(area_code)
            ordered = sorted(emp_ids, key=lambda eid: (self.employees[eid].get("is_protected"), eid))
            for eid in ordered:
                if len(approved[key]) >= capacity:
                    continue
                if self._would_break_professional_leave(area_code, key[0], eid, approved, professional_ids_by_area):
                    continue
                approved[key].add(eid)

        approved_by_employee = {eid for ids in approved.values() for eid in ids}
        for area_code, emp_ids in regular_ids_by_area.items():
            for eid in sorted(emp_ids):
                if eid in approved_by_employee:
                    continue
                candidate_days = [
                    ((start + timedelta(days=offset)).isoformat(), area_code)
                    for offset in range(7)
                ]
                candidate_days.sort(key=lambda key: (len(approved[key]), key[0]))
                for key in candidate_days:
                    if len(approved[key]) >= self._daily_leave_capacity(area_code):
                        continue
                    if self._would_break_professional_leave(area_code, key[0], eid, approved, professional_ids_by_area):
                        continue
                    approved[key].add(eid)
                    approved_by_employee.add(eid)
                    break
        return approved

    def recommend_support(
        self,
        version: dict[str, Any],
        date: str,
        slot: str,
        area_code: str,
        task_code: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        task_code = task_code or self._non_professional_task(area_code)["task_code"]
        candidates = []
        for emp in self.employees.values():
            if emp["employee_type"] != "temporary":
                continue
            skill = self.skills.get((emp["id"], area_code, task_code))
            if not skill:
                continue
            used_hours = sum(item["hours"] for item in version["schedule_items"] if item["employee_id"] == emp["id"])
            if used_hours >= emp["weekly_hours_limit"]:
                continue
            score = self._candidate_score(emp["id"], area_code, task_code, used_hours)
            candidates.append(
                {
                    "employee_id": emp["id"],
                    "employee_name": emp["name"],
                    "skill_level": skill["skill_level"],
                    "weekly_hours": used_hours,
                    "weekly_hours_limit": emp["weekly_hours_limit"],
                    "score": score,
                    "reason": f"{emp['name']}可跨区支援{self.areas[area_code]['name']}，{task_code}技能{skill['skill_level']}，本周已排{used_hours:g}小时。",
                }
            )
        return sorted(candidates, key=lambda row: row["score"], reverse=True)[:limit]

    def detect_risks(
        self,
        version_id: str,
        demand_results: list[dict[str, Any]],
        schedule_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        risks: list[dict[str, Any]] = []
        for row in demand_results:
            assigned = [
                item
                for item in schedule_items
                if item["date"] == row["date"]
                and item["area_code"] == row["area_code"]
                and self._covers(item["slot"], row["slot"])
            ]
            if row["is_protected"] and self.tasks[(row["area_code"], row["task_code"])]["is_professional"]:
                qualified_count = self._qualified_professional_count(row, schedule_items)
                required_professionals = row.get("professional_required_count", row["required_count"])
                if qualified_count < required_professionals:
                    risks.append(
                        {
                            "id": f"risk_{len(risks)+1:04d}",
                            "type": "professional_gap",
                            "level": "critical",
                            "description": f"{row['date']} {row['slot']} {row['area_name']}{row['task_name']}需要{required_professionals}名合格师傅，当前{qualified_count}名。",
                            "affected_item_ids": [],
                            "suggestion": "优先保留本区域S/A级正式工，不建议跨区抽调。",
                        }
                    )
            if row["priority"] == "high" and len(assigned) < row["required_count"]:
                gap = row["required_count"] - len(assigned)
                risks.append(
                    {
                        "id": f"risk_{len(risks)+1:04d}",
                        "type": "peak_gap",
                        "level": "warning",
                        "description": f"{row['date']} {row['slot']} {row['area_name']}需求{row['required_count']}人，当前覆盖{len(assigned)}人，缺口{gap}人。",
                        "affected_item_ids": [item["id"] for item in assigned],
                        "suggestion": "从临时工混排池推荐候选人补位。",
                    }
                )
        return risks

    def calculate_kpis(
        self,
        demand_results: list[dict[str, Any]],
        schedule_items: list[dict[str, Any]],
        risks: list[dict[str, Any]],
        intervention_count: int,
    ) -> KpiResult:
        professional_demand = [
            row
            for row in demand_results
            if self.tasks[(row["area_code"], row["task_code"])]["is_professional"]
        ]
        professional_covered = 0
        for row in professional_demand:
            if self._qualified_professional_count(row, schedule_items) >= row.get("professional_required_count", row["required_count"]):
                professional_covered += 1
        baseline_checks = 0
        baseline_hits = 0
        checked = {(row["date"], row["slot"], row["area_code"]) for row in demand_results}
        for day, slot, area_code in checked:
            baseline_checks += 1
            regular_count = sum(
                1
                for item in schedule_items
                if item["date"] == day
                and item["area_code"] == area_code
                and item["employee_type"] == "regular"
                and self._covers(item["slot"], slot)
            )
            if regular_count >= int(self.areas[area_code]["baseline_min"]):
                baseline_hits += 1
        mixed_items = [item for item in schedule_items if item["assignment_type"] == "temporary"]
        temp_count = sum(1 for emp in self.employees.values() if emp["employee_type"] == "temporary")
        peak_gap_count = sum(1 for risk in risks if risk["type"] == "peak_gap")
        total_items = max(1, len(schedule_items))
        return KpiResult(
            professional_coverage_rate=round(professional_covered / max(1, len(professional_demand)), 4),
            baseline_achievement_rate=round(baseline_hits / max(1, baseline_checks), 4),
            mixed_utilization_rate=round(len({item["employee_id"] for item in mixed_items}) / max(1, temp_count), 4),
            peak_gap_count=peak_gap_count,
            intervention_rate=round(intervention_count / total_items, 4),
        )

    def _qualified_professional_count(self, demand: dict[str, Any], schedule_items: list[dict[str, Any]]) -> int:
        task = self.tasks[(demand["area_code"], demand["task_code"])]
        if not task["is_professional"]:
            return 0
        count = 0
        for item in schedule_items:
            if (
                item["date"] == demand["date"]
                and item["area_code"] == demand["area_code"]
                and item["employee_type"] == "regular"
                and self._covers(item["slot"], demand["slot"])
            ):
                skill = self.skills.get((item["employee_id"], demand["area_code"], demand["task_code"]))
                if skill and SKILL_RANK[skill["skill_level"]] >= SKILL_RANK[task["min_skill_level"]]:
                    count += 1
        return count

    def _assign_temporary_support(
        self,
        version_id: str,
        demand_results: list[dict[str, Any]],
        schedule_items: list[dict[str, Any]],
        employee_hours: Counter[str],
    ) -> None:
        peak_demands = [
            row
            for row in sorted(demand_results, key=lambda item: item["demand_score"], reverse=True)
            if row["priority"] == "high" and not self.tasks[(row["area_code"], row["task_code"])]["is_professional"]
        ]
        assigned_by_day: set[tuple[str, str]] = set()
        for demand in peak_demands:
            slot = self._temporary_slot_for_demand(demand)
            task_code = demand["task_code"]
            candidates = [
                emp
                for emp in self.employees.values()
                if emp["employee_type"] == "temporary"
                and (demand["date"], emp["id"]) not in assigned_by_day
                and employee_hours[emp["id"]] + self._slot_hours(slot) <= emp["weekly_hours_limit"]
                and (emp["id"], demand["area_code"], task_code) in self.skills
            ]
            if not candidates:
                continue
            candidates.sort(
                key=lambda emp: self._candidate_score(emp["id"], demand["area_code"], task_code, employee_hours[emp["id"]]),
                reverse=True,
            )
            emp = candidates[0]
            task = self.tasks[(demand["area_code"], task_code)]
            hours = self._slot_hours(slot)
            employee_hours[emp["id"]] += hours
            assigned_by_day.add((demand["date"], emp["id"]))
            schedule_items.append(
                self._item(
                    version_id,
                    len(schedule_items) + 1,
                    demand["date"],
                    demand["weekday"],
                    slot,
                    demand["area_code"],
                    task_code,
                    emp,
                    "temporary",
                    None,
                    hours,
                    0,
                    f"{emp['name']}来自全店临时工池，支援{demand['area_name']}{task['task_name']}；依据：{', '.join(demand['demand_factors'][:3])}。",
                )
            )

    def _item(
        self,
        version_id: str,
        index: int,
        date: str,
        weekday: str,
        slot: str,
        area_code: str,
        task_code: str,
        employee: dict[str, Any],
        assignment_type: str,
        regular_shift_type: str | None,
        hours: float,
        is_protected: int,
        explanation: str,
    ) -> dict[str, Any]:
        area = self.areas[area_code]
        task = self.tasks[(area_code, task_code)]
        return {
            "id": f"si_{index:04d}",
            "version_id": version_id,
            "date": date,
            "weekday": weekday,
            "slot": slot,
            "area_code": area_code,
            "area_name": area["name"],
            "task_code": task_code,
            "task_name": task["task_name"],
            "employee_id": employee["id"],
            "employee_name": employee["name"],
            "employee_type": employee["employee_type"],
            "assignment_type": assignment_type,
            "regular_shift_type": regular_shift_type,
            "hours": hours,
            "risk_level": "none",
            "explanation": explanation,
            "source": "system",
            "is_protected": is_protected,
        }

    def _tasks_by_area(self) -> dict[str, list[dict[str, Any]]]:
        rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for task in self.seed["area_tasks"]:
            rows[task["area_code"]].append(task)
        for tasks in rows.values():
            tasks.sort(key=lambda row: row["priority"], reverse=True)
        return rows

    def _demand_by_day_area(self, demand_results: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
        rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for demand in demand_results:
            rows[(demand["date"], demand["area_code"])].append(demand)
        return rows

    def _regular_pool_by_area(self, demand_results: list[dict[str, Any]]) -> dict[str, set[str]]:
        demand_by_area: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for demand in demand_results:
            demand_by_area[demand["area_code"]].append(demand)

        pools: dict[str, set[str]] = {}
        for area_code, area in self.areas.items():
            regulars = [
                emp
                for emp in self.employees.values()
                if emp["employee_type"] == "regular" and emp["main_area"] == area_code and emp["is_active"]
            ]
            target = self._weekly_regular_pool_size(area_code, area, demand_by_area.get(area_code, []), len(regulars))
            ordered = sorted(
                regulars,
                key=lambda emp: (
                    not self._has_professional_skill(emp["id"], area_code),
                    not emp.get("is_protected"),
                    emp["id"],
                ),
            )
            pools[area_code] = {emp["id"] for emp in ordered[:target]}
        return pools

    def _weekly_regular_pool_size(
        self,
        area_code: str,
        area: dict[str, Any],
        area_demands: list[dict[str, Any]],
        available_count: int,
    ) -> int:
        days: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for demand in area_demands:
            days[demand["date"]].append(demand)

        peak_score = max((int(row["demand_score"]) for row in area_demands), default=0)
        boosted_days = sum(1 for rows in days.values() if self._has_external_boost(rows))
        severe_days = sum(1 for rows in days.values() if self._high_slot_count(rows) >= 6)
        extreme_days = sum(1 for rows in days.values() if self._high_slot_count(rows) >= 10)

        if self._has_professional_tasks(area_code):
            target = min(available_count, 14)
            if peak_score >= 96 or severe_days >= 2 or boosted_days >= 3:
                target += 1
            if extreme_days:
                target += 1
            professional_count = sum(1 for emp in self.employees.values() if emp["main_area"] == area_code and self._has_professional_skill(emp["id"], area_code))
            return min(available_count, max(target, professional_count))

        baseline_max = int(area["baseline_max"])
        if area_code == "produce":
            target = 20
            if peak_score >= 96 or boosted_days >= 3:
                target += 1
            if extreme_days:
                target += 1
            return min(available_count, max(target, baseline_max + 2))

        if area_code == "cashier":
            target = 14
            if peak_score >= 92 or boosted_days >= 3:
                target += 1
            if extreme_days:
                target += 1
            return min(available_count, max(target, baseline_max + 2))

        target = 7
        if peak_score >= 90 or boosted_days >= 3:
            target += 1
        return min(available_count, max(target, baseline_max + 2))

    def _daily_regular_target(
        self,
        area_code: str,
        area: dict[str, Any],
        day_demands: list[dict[str, Any]],
        available_count: int,
        needed_professionals: int,
    ) -> int:
        baseline_min = int(area["baseline_min"])
        baseline_max = int(area["baseline_max"])
        has_professional_tasks = self._has_professional_tasks(area_code)
        base_target = baseline_min * 2 + 1 if has_professional_tasks else baseline_min + 1
        peak_score = max((int(row["demand_score"]) for row in day_demands), default=0)
        high_slot_count = self._high_slot_count(day_demands)
        has_external_boost = self._has_external_boost(day_demands)

        target = max(base_target, baseline_max, needed_professionals)
        if peak_score >= 86:
            target += 1
        if high_slot_count >= 6:
            target += 1
        if has_external_boost and peak_score >= 78:
            target += 1

        if not has_professional_tasks:
            if peak_score >= 86:
                target = max(target, baseline_max + 2)
            elif peak_score >= 68:
                target = max(target, baseline_max + 1)
            elif peak_score < 55 and not high_slot_count:
                target = max(baseline_min, target - 1)

        if has_professional_tasks and peak_score < 60 and not high_slot_count:
            target = max(needed_professionals, target - 1)

        return min(available_count, target)

    def _daily_professional_target(
        self,
        area_code: str,
        day_demands: list[dict[str, Any]],
        available_count: int,
    ) -> int:
        if not self._has_professional_tasks(area_code) or available_count <= 0:
            return 0

        professional_demands = [
            demand
            for demand in day_demands
            if self.tasks[(demand["area_code"], demand["task_code"])]["is_professional"]
        ]
        if not professional_demands:
            return 0

        max_required = max(demand.get("professional_required_count", demand["required_count"]) for demand in professional_demands)
        high_professional_slots = sum(
            1
            for demand in professional_demands
            if demand["priority"] == "high" or int(demand["demand_score"]) >= 78
        )
        target = max(2, max_required + 1)
        if high_professional_slots >= 6:
            target += 1
        return min(available_count, target, 3)

    def _high_slot_count(self, demands: list[dict[str, Any]]) -> int:
        return len({
            demand["slot"]
            for demand in demands
            if demand["priority"] == "high" or int(demand["demand_score"]) >= 78
        })

    def _has_external_boost(self, demands: list[dict[str, Any]]) -> bool:
        return any(
            any(keyword in factor for keyword in ("周末", "促销", "会员", "降雨", "团购", "暑期") for factor in demand["demand_factors"])
            for demand in demands
        )

    def _skills(self) -> dict[tuple[str, str, str], dict[str, Any]]:
        return {
            (row["employee_id"], row["area_code"], row["task_code"]): row
            for row in self.seed["employee_skills"]
        }

    def _preferences(self, week_start: str) -> dict[str, str]:
        return {
            row["employee_id"]: row["preferred_shift_type"]
            for row in self.seed["employee_weekly_preferences"]
            if row["week_start"] == week_start
        }

    def _regular_task_for_shift(
        self,
        employee_id: str,
        area_code: str,
        date_text: str,
        position: int,
        shift_type: str,
        day_demands: list[dict[str, Any]],
    ) -> dict[str, Any]:
        tasks = self.tasks_by_area[area_code]
        skilled_tasks = [
            task
            for task in tasks
            if (employee_id, area_code, task["task_code"]) in self.skills
        ]
        if not skilled_tasks:
            return self._non_professional_task(area_code)

        professional_tasks = [task for task in skilled_tasks if task["is_professional"]]
        non_professional_tasks = [task for task in skilled_tasks if not task["is_professional"]]
        day_number = int(date_text[-2:])

        if professional_tasks:
            task_by_code = {task["task_code"]: task for task in skilled_tasks}
            core_professional_slots = {
                demand["slot"]
                for demand in day_demands
                if self.tasks[(demand["area_code"], demand["task_code"])]["is_professional"]
                and demand.get("professional_required_count", 0) >= 2
            }

            if area_code == "aquatic":
                if shift_type == "morning" and {"09:00-10:00", "10:00-11:00"} & core_professional_slots and "fish_butcher" in task_by_code:
                    return task_by_code["fish_butcher"]
                if shift_type in {"evening", "split"} and {"17:00-18:00", "18:00-19:00"} & core_professional_slots:
                    return task_by_code.get("aquatic_process") or task_by_code.get("fish_butcher") or professional_tasks[0]
                return (
                    task_by_code.get("weighing")
                    or task_by_code.get("aquatic_process")
                    or task_by_code.get("cleaning")
                    or professional_tasks[0]
                )

            if area_code == "meat":
                if shift_type == "morning" and {"09:00-10:00", "10:00-11:00"} & core_professional_slots and "meat_cut" in task_by_code:
                    return task_by_code["meat_cut"]
                if shift_type in {"evening", "split"} and {"17:00-18:00", "18:00-19:00"} & core_professional_slots:
                    return task_by_code.get("meat_divide") or task_by_code.get("meat_cut") or professional_tasks[0]
                return (
                    task_by_code.get("weighing")
                    or task_by_code.get("display")
                    or task_by_code.get("meat_divide")
                    or professional_tasks[0]
                )

            ordered_non_professional = sorted(non_professional_tasks, key=lambda task: (-task["priority"], task["task_code"]))
            if ordered_non_professional:
                return ordered_non_professional[(day_number + position) % len(ordered_non_professional)]
            return sorted(professional_tasks, key=lambda task: (-task["priority"], task["task_code"]))[0]

        return sorted(
            non_professional_tasks,
            key=lambda task: (
                -SKILL_RANK[self.skills[(employee_id, area_code, task["task_code"])]["skill_level"]],
                (day_number + position + task["priority"]) % max(1, len(non_professional_tasks)),
                -task["priority"],
            ),
        )[0]

    def _best_regular_task(self, employee_id: str, area_code: str) -> dict[str, Any]:
        return self._regular_task_for_shift(employee_id, area_code, "2026-01-01", 0, "morning", [])

    def _rotation_index(self, employee_id: str, offset: int) -> int:
        numeric_id = int(employee_id.split("_")[1])
        return (numeric_id + offset * 7) % 97

    def _has_professional_skill(self, employee_id: str, area_code: str) -> bool:
        for task in self.tasks_by_area[area_code]:
            if not task["is_professional"]:
                continue
            skill = self.skills.get((employee_id, area_code, task["task_code"]))
            if skill and SKILL_RANK[skill["skill_level"]] >= SKILL_RANK[task["min_skill_level"]]:
                return True
        return False

    def _has_professional_tasks(self, area_code: str) -> bool:
        return any(task["is_professional"] for task in self.tasks_by_area[area_code])

    def _professional_shift_plan(self, count: int) -> list[str]:
        if count <= 0:
            return []
        if count == 1:
            return ["split"]
        if count == 2:
            return ["morning", "evening"]
        if count == 3:
            return ["morning", "evening", "split"]
        return ["morning", "evening", "morning", "evening"] + ["split"] * max(0, count - 4)

    def _non_professional_shift_plan(self, baseline_min: int, day_demands: list[dict[str, Any]]) -> list[str]:
        needs_midday = any(
            demand["priority"] == "high" and demand["slot"] in {"12:00-13:00", "13:00-14:00", "14:00-15:00"}
            for demand in day_demands
        )
        plan = ["morning", "evening"] * baseline_min
        if needs_midday:
            insert_at = min(2, len(plan))
            plan.insert(insert_at, "midday")
        plan.append("split")
        return plan

    def _daily_leave_capacity(self, area_code: str) -> int:
        regular_count = sum(
            1
            for emp in self.employees.values()
            if emp["employee_type"] == "regular" and emp["main_area"] == area_code and emp["is_active"]
        )
        area = self.areas[area_code]
        area_target = int(area["baseline_min"]) * 3 if self._has_professional_tasks(area_code) else int(area["baseline_min"]) * 2
        scheduled_target = max(area_target, int(area["baseline_max"]))
        return max(1, regular_count - scheduled_target)

    def _would_break_professional_leave(
        self,
        area_code: str,
        date_text: str,
        employee_id: str,
        approved: dict[tuple[str, str], set[str]],
        professional_ids_by_area: dict[str, set[str]],
    ) -> bool:
        professional_ids = professional_ids_by_area.get(area_code, set())
        if employee_id not in professional_ids:
            return False
        off_count = sum(1 for eid in approved[(date_text, area_code)] if eid in professional_ids)
        min_available = min(3, len(professional_ids))
        return len(professional_ids) - off_count - 1 < min_available

    def _non_professional_task(self, area_code: str) -> dict[str, Any]:
        return next(task for task in self.tasks_by_area[area_code] if not task["is_professional"])

    def _candidate_score(self, employee_id: str, area_code: str, task_code: str, used_hours: float) -> float:
        skill = self.skills[(employee_id, area_code, task_code)]
        return round(SKILL_RANK[skill["skill_level"]] * 20 + float(skill["area_familiarity"]) * 30 - used_hours * 0.7, 2)

    def _temporary_slot_for_demand(self, demand: dict[str, Any]) -> str:
        start_hour = int(demand["slot"][:2])
        if start_hour < 14:
            return "10:00-14:00"
        if start_hour < 17:
            return "14:00-18:00"
        if start_hour >= 20:
            return "17:00-22:00"
        return "18:00-22:00"

    def _covers(self, assignment_slot: str, demand_slot: str) -> bool:
        start_hour = int(demand_slot[:2])
        for start, end in SLOT_RANGES.get(assignment_slot, []):
            if start <= start_hour < end:
                return True
        return False

    def _slot_hours(self, slot: str) -> float:
        return sum(end - start for start, end in SLOT_RANGES[slot])

    def _shift_label(self, shift_type: str) -> str:
        return {
            "morning": "早班8:00-16:00",
            "midday": "午间班10:00-18:00",
            "evening": "晚班14:00-22:00",
            "split": "两头班8:00-12:00/17:00-21:00",
        }.get(shift_type, "轮班")

    def _summary(self, kpis: dict[str, Any], risks: list[dict[str, Any]]) -> str:
        return (
            "已按半混班规则生成7天班表：正式工固定在所属部门，专业岗优先锁定S/A级师傅；"
            f"临时工用于高峰补位。专业岗覆盖率{kpis['professional_coverage_rate']:.0%}，"
            f"区域保底达成率{kpis['baseline_achievement_rate']:.0%}，当前高峰缺口{len([r for r in risks if r['type']=='peak_gap'])}个。"
        )

    def _leave_payload(self, week_start: str, approved: dict[tuple[str, str], set[str]]) -> list[dict[str, Any]]:
        requested = [row for row in self.seed["employee_weekly_leave"] if row["week_start"] == week_start]
        rows = []
        start = datetime.strptime(week_start, "%Y-%m-%d").date()
        for row in requested:
            emp = self.employees[row["employee_id"]]
            day = (start + timedelta(days=WEEKDAY_NAMES.index(row["preferred_day_off"]))).isoformat()
            ok = row["employee_id"] in approved.get((day, emp["main_area"]), set())
            rows.append(
                {
                    **row,
                    "employee_name": emp["name"],
                    "date": day,
                    "status": "approved" if ok else "rejected",
                    "reason": "同意休假" if ok else "同区域同日休假过多，保留区域保底正式工",
                }
            )
        return rows
