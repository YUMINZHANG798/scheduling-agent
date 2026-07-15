from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

from app.data.seed_loader import SeedLoader


WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SLOTS = [
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
]


class DemandService:
    def __init__(self, seed_loader: SeedLoader | None = None) -> None:
        self.seed_loader = seed_loader or SeedLoader()
        self.data = self.seed_loader.all()
        self.areas = {row["code"]: row for row in self.data["areas"]}
        self.tasks_by_area = self._tasks_by_area()

    def calculate_week(self, week_start: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        start = datetime.strptime(week_start, "%Y-%m-%d").date()
        traffic_baseline = self._traffic_baseline()
        sales_baseline = self._sales_baseline()
        orders_baseline = self._orders_baseline()
        weather_by_date_slot = {(r["date"], r["slot"]): r for r in self.data["weather"]}
        holidays_by_date = {r["date"]: r for r in self.data["holidays"]}
        promotions = {(r["date"], r["area_code"]): r for r in self.data["promotions"]}

        demand_results: list[dict[str, Any]] = []
        seq = 1
        for offset in range(7):
            current = start + timedelta(days=offset)
            current_text = current.isoformat()
            weekday = WEEKDAY_NAMES[current.weekday()]
            is_weekend = current.weekday() >= 5 or current_text in holidays_by_date
            for slot in SLOTS:
                traffic = traffic_baseline.get(slot, 100)
                orders = orders_baseline.get(slot, 10)
                for area_code, area in self.areas.items():
                    sales = sales_baseline.get((area_code, slot), 600)
                    score = self._score(slot, traffic, sales, orders)
                    factors = self._base_factors(slot, score)
                    if is_weekend:
                        score *= 1.12
                        factors.append("周末客流上浮")
                    promo = promotions.get((current_text, area_code))
                    if promo:
                        score *= float(promo["boost_factor"])
                        factors.append(promo["description"])
                    weather = weather_by_date_slot.get((current_text, slot))
                    if weather and int(weather["rain_level"]) >= 2:
                        score *= 1.08
                        factors.append("降雨提升线上拣货与到店集中度")
                    if current.weekday() == 4 and slot in {"17:00-18:00", "18:00-19:00", "19:00-20:00"}:
                        score *= 1.15
                        factors.append("周五晚高峰")

                    task = self._pick_task(area_code, slot, score)
                    final_score = min(100, round(score))
                    required_count = self._required_count(area, final_score, task["is_professional"])
                    labor_breakdown = self._labor_breakdown(area, task, final_score, required_count)
                    demand_results.append(
                        {
                            "id": f"dr_{seq:04d}",
                            "date": current_text,
                            "weekday": weekday,
                            "slot": slot,
                            "area_code": area_code,
                            "area_name": area["name"],
                            "task_code": task["task_code"],
                            "task_name": task["task_name"],
                            "required_count": required_count,
                            **labor_breakdown,
                            "demand_score": final_score,
                            "demand_factors": factors,
                            "priority": "high" if final_score >= 78 else ("medium" if final_score >= 55 else "low"),
                            "confidence": "high" if len(factors) >= 3 else "medium",
                            "is_protected": int(task["is_professional"] or slot in {"08:00-12:00", "17:00-21:00"}),
                        }
                    )
                    seq += 1

        insights = sorted(
            [
                {
                    "date": row["date"],
                    "weekday": row["weekday"],
                    "slot": row["slot"],
                    "area_code": row["area_code"],
                    "area_name": row["area_name"],
                    "required_count": row["required_count"],
                    "professional_required_count": row["professional_required_count"],
                    "regular_required_count": row["regular_required_count"],
                    "temporary_required_count": row["temporary_required_count"],
                    "demand_score": row["demand_score"],
                    "demand_factors": row["demand_factors"],
                    "priority": row["priority"],
                    "confidence": row["confidence"],
                }
                for row in demand_results
                if row["priority"] == "high"
            ],
            key=lambda row: row["demand_score"],
            reverse=True,
        )[:12]
        return demand_results, insights

    def source_summary(self) -> dict[str, Any]:
        employees = self.data["employees"]
        regular_count = sum(1 for row in employees if row["employee_type"] == "regular")
        return {
            "store_id": "fresh_store_001",
            "employees_count": len(employees),
            "regular_count": regular_count,
            "temporary_count": len(employees) - regular_count,
            "areas": self.data["areas"],
            "historical_sales_rows": len(self.data["historical_sales"]),
            "historical_traffic_rows": len(self.data["historical_traffic"]),
            "online_orders_rows": len(self.data["online_orders"]),
            "weather_rows": len(self.data["weather"]),
            "promotions": self.data["promotions"],
        }

    def _tasks_by_area(self) -> dict[str, list[dict[str, Any]]]:
        tasks: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in self.data["area_tasks"]:
            tasks[row["area_code"]].append(row)
        for rows in tasks.values():
            rows.sort(key=lambda row: row["priority"], reverse=True)
        return dict(tasks)

    def _traffic_baseline(self) -> dict[str, float]:
        values: dict[str, list[float]] = defaultdict(list)
        for row in self.data["historical_traffic"]:
            values[row["slot"]].append(float(row["customer_count"]))
        return {slot: mean(numbers) for slot, numbers in values.items()}

    def _sales_baseline(self) -> dict[tuple[str, str], float]:
        values: dict[tuple[str, str], list[float]] = defaultdict(list)
        for row in self.data["historical_sales"]:
            values[(row["area_code"], row["slot"])].append(float(row["sales_amount"]))
        return {key: mean(numbers) for key, numbers in values.items()}

    def _orders_baseline(self) -> dict[str, float]:
        values: dict[str, list[float]] = defaultdict(list)
        for row in self.data["online_orders"]:
            values[row["slot"]].append(float(row["order_count"]) + float(row["picking_count"]) * 0.5)
        return {slot: mean(numbers) for slot, numbers in values.items()}

    def _score(self, slot: str, traffic: float, sales: float, orders: float) -> float:
        traffic_component = min(35, traffic / 8)
        sales_component = min(35, sales / 65)
        order_component = min(20, orders * 0.7)
        slot_component = 10 if slot in {"10:00-11:00", "17:00-18:00", "18:00-19:00"} else 4
        return traffic_component + sales_component + order_component + slot_component

    def _base_factors(self, slot: str, score: float) -> list[str]:
        factors = ["历史销售/客流基线"]
        if slot in {"10:00-11:00", "11:00-12:00"}:
            factors.append("午前采购高峰")
        if slot in {"17:00-18:00", "18:00-19:00", "19:00-20:00"}:
            factors.append("晚高峰")
        if score < 45:
            factors.append("低峰时段")
        return factors

    def _pick_task(self, area_code: str, slot: str, score: float) -> dict[str, Any]:
        tasks = self.tasks_by_area[area_code]
        professional = [task for task in tasks if task["is_professional"]]
        non_professional = [task for task in tasks if not task["is_professional"]]
        protected_professional_slots = {
            "08:00-09:00",
            "09:00-10:00",
            "10:00-11:00",
            "17:00-18:00",
            "18:00-19:00",
            "19:00-20:00",
            "20:00-21:00",
        }
        if professional and slot in protected_professional_slots:
            return professional[0]
        if non_professional:
            return non_professional[0]
        return (professional or non_professional)[0]

    def _required_count(self, area: dict[str, Any], score: int, is_professional: int) -> int:
        if is_professional:
            return 2 if score >= 68 else 1
        if score >= 86:
            return int(area["baseline_max"]) + 1
        if score >= 68:
            return int(area["baseline_max"])
        if score >= 45:
            return int(area["baseline_min"])
        return max(1, int(area["baseline_min"]) - 1)

    def _labor_breakdown(
        self,
        area: dict[str, Any],
        task: dict[str, Any],
        score: int,
        required_count: int,
    ) -> dict[str, int]:
        baseline_min = int(area["baseline_min"])
        if task["is_professional"]:
            professional_required = required_count
            return {
                "professional_required_count": professional_required,
                "regular_required_count": max(0, baseline_min - professional_required),
                "temporary_required_count": 0,
            }

        regular_required = baseline_min
        temporary_required = max(0, required_count - regular_required)
        if score >= 86:
            temporary_required = max(1, temporary_required)
        return {
            "professional_required_count": 0,
            "regular_required_count": regular_required,
            "temporary_required_count": temporary_required,
        }
