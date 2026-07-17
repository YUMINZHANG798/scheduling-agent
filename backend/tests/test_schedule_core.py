from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.data.seed_loader import SeedLoader
from app.data.store import SQLiteStore
from app.engine.scheduling import SchedulingGenerator
from app.models.schemas import GenerateScheduleRequest, ModifyScheduleRequest
from app.services.agent_service import AgentService
from app.services.demand_service import DemandService
from app.services.schedule_service import ScheduleService


ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "backend" / "app" / "seed"


class FakeLlmClient:
    def __init__(self, reply: str | None = None):
        self.reply = reply

    def complete(self, messages):
        return self.reply

    def stream(self, messages):
        if False:
            yield messages


class ScheduleCoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        loader = SeedLoader(SEED)
        store = SQLiteStore(Path(self.tmp.name) / "demo.sqlite", loader)
        demand = DemandService(loader)
        generator = SchedulingGenerator(loader)
        self.service = ScheduleService(store, demand, generator)
        self.agent = AgentService(store, generator)

    def tearDown(self):
        self.tmp.cleanup()

    def test_generate_week_schedule(self):
        response = self.service.generate(
            GenerateScheduleRequest(store_id="fresh_store_001", week_start="2026-07-13")
        )
        self.assertEqual(len(response.demand_results), 490)
        self.assertGreaterEqual(len(response.schedule_items), 140)
        self.assertEqual(response.kpis.professional_coverage_rate, 1.0)
        self.assertEqual(response.kpis.baseline_achievement_rate, 1.0)
        self.assertGreaterEqual(response.kpis.mixed_utilization_rate, 0.8)
        hours_by_employee = {}
        for item in response.schedule_items:
            hours_by_employee[item.employee_id] = hours_by_employee.get(item.employee_id, 0) + item.hours
        for employee_id, hours in hours_by_employee.items():
            limit = self.service.generator.employees[employee_id]["weekly_hours_limit"]
            self.assertLessEqual(hours, limit)

    def test_generate_week_schedule_staffing_summary(self):
        response = self.service.generate(
            GenerateScheduleRequest(store_id="fresh_store_001", week_start="2026-07-13")
        )
        summary = response.staffing_summary
        self.assertEqual(summary.total.total_count, summary.regular.total_count + summary.temporary.total_count)
        self.assertEqual(summary.total.scheduled_count, summary.regular.scheduled_count + summary.temporary.scheduled_count)
        self.assertEqual(summary.total.unscheduled_count, summary.regular.unscheduled_count + summary.temporary.unscheduled_count)
        self.assertEqual(summary.total.leave_count, summary.regular.leave_count + summary.temporary.leave_count)
        self.assertEqual(
            summary.total.total_count,
            summary.total.scheduled_count + summary.total.unscheduled_count + summary.total.leave_count,
        )
        self.assertGreater(summary.total.total_count, 0)
        self.assertGreater(summary.total.scheduled_count, 0)
        self.assertLess(summary.regular.scheduled_count, summary.regular.total_count)
        self.assertGreaterEqual(summary.regular.scheduled_count, summary.regular.total_count - 10)

    def test_lists_saved_schedule_versions(self):
        first = self.service.generate(
            GenerateScheduleRequest(store_id="fresh_store_001", week_start="2026-07-06")
        )
        second = self.service.generate(
            GenerateScheduleRequest(store_id="fresh_store_001", week_start="2026-07-13")
        )
        versions = self.service.versions()
        self.assertGreaterEqual(len(versions), 2)
        self.assertEqual(versions[0]["id"], second.version_id)
        self.assertEqual(versions[1]["id"], first.version_id)
        self.assertGreater(versions[0]["schedule_item_count"], 0)

    def test_get_schedule_uses_saved_staffing_snapshot(self):
        response = self.service.generate(
            GenerateScheduleRequest(store_id="fresh_store_001", week_start="2026-07-13")
        )
        snapshot = response.staffing_summary.model_dump()
        snapshot["total"]["total_count"] = 88
        snapshot["total"]["unscheduled_count"] = 10
        self.service.store.update_version_staffing_summary(response.version_id, snapshot)
        loaded = self.service.get(response.version_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.staffing_summary.total.total_count, 88)
        self.assertEqual(loaded.staffing_summary.total.unscheduled_count, 10)

    def test_reset_rebuilds_demo_schedule_history(self):
        response = self.service.generate(
            GenerateScheduleRequest(store_id="fresh_store_001", week_start="2026-07-13")
        )
        self.service.reset_demo()
        versions = self.service.versions()
        self.assertIsNone(self.service.get(response.version_id))
        self.assertGreaterEqual(len(versions), 5)
        self.assertTrue(all(row["schedule_item_count"] > 0 for row in versions))
        self.assertGreaterEqual(len({row["week_start"] for row in versions}), 5)

    def test_agent_recommends_temporary_support(self):
        response = self.service.generate(
            GenerateScheduleRequest(store_id="fresh_store_001", week_start="2026-07-13")
        )
        candidates = self.agent.recommend_support(
            response.version_id, "2026-07-17", "18:00-19:00", "produce", "restock"
        )
        self.assertTrue(candidates)
        self.assertIn("employee_name", candidates[0])

    def test_agent_answers_employee_schedule_fact_query(self):
        response = self.service.generate(
            GenerateScheduleRequest(store_id="fresh_store_001", week_start="2026-07-13")
        )
        result = self.agent.chat(
            "小宋都是哪几天上班",
            response.version_id,
            {"date": "2026-07-17", "slot": "18:00-19:00", "area_code": "produce"},
            [],
        )
        self.assertEqual(result["intent"], "schedule_fact_query")
        self.assertFalse(result["is_fallback"])
        self.assertIn("小宋", result["message"])
        self.assertTrue(result["sections"][0]["bullets"])

    def test_agent_enhances_fact_query_with_llm_analysis(self):
        response = self.service.generate(
            GenerateScheduleRequest(store_id="fresh_store_001", week_start="2026-07-13")
        )
        agent = AgentService(
            self.service.store,
            self.service.generator,
            FakeLlmClient(
                '{"answer":"小宋本周排班较集中，主要覆盖固定时段。","sections":[{"title":"分析判断","bullets":["当前回答基于已检索到的排班明细。","从已知排班看，小宋承担的是稳定覆盖角色。"]}],"suggested_questions":["小宋在哪些区域上班？"]}'
            ),
        )
        result = agent.chat("小宋都是哪几天上班", response.version_id, {}, [])
        self.assertEqual(result["intent"], "schedule_fact_query")
        self.assertEqual(result["message"], "小宋本周排班较集中，主要覆盖固定时段。")
        self.assertEqual(result["sections"][0]["title"], "小宋排班明细")
        self.assertTrue(any(section["title"] == "分析判断" for section in result["sections"]))
        self.assertEqual(result["suggested_questions"], ["小宋在哪些区域上班？"])

    def test_manual_modify_records_intervention(self):
        response = self.service.generate(
            GenerateScheduleRequest(store_id="fresh_store_001", week_start="2026-07-13")
        )
        item = next(row for row in response.schedule_items if row.assignment_type == "temporary")
        result = self.service.modify(
            response.version_id,
            item.id,
            ModifyScheduleRequest(
                after={"area_code": "cashier", "task_code": "cashier"},
                reason_code="manager_experience",
                reason_text="晚高峰收银更需要支援",
                force=True,
            ),
        )
        self.assertIsNotNone(result)
        interventions = self.service.interventions(response.version_id)
        self.assertEqual(len(interventions), 1)


if __name__ == "__main__":
    unittest.main()
