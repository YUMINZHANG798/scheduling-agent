from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.core.config import get_settings
from app.data.seed_loader import SeedLoader


DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS areas (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  allow_mixed INTEGER NOT NULL,
  baseline_min INTEGER NOT NULL,
  baseline_max INTEGER NOT NULL,
  sort_order INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS area_tasks (
  id TEXT PRIMARY KEY,
  area_code TEXT NOT NULL,
  task_code TEXT NOT NULL,
  task_name TEXT NOT NULL,
  is_professional INTEGER NOT NULL,
  min_skill_level TEXT NOT NULL,
  priority INTEGER NOT NULL,
  UNIQUE(area_code, task_code)
);
CREATE TABLE IF NOT EXISTS skill_definitions (
  level TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  can_independent INTEGER NOT NULL,
  score REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS employees (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  main_area TEXT,
  employee_type TEXT NOT NULL,
  regular_shift_type TEXT,
  weekly_hours_limit INTEGER NOT NULL,
  is_active INTEGER NOT NULL,
  is_protected INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS employee_skills (
  id TEXT PRIMARY KEY,
  employee_id TEXT NOT NULL,
  area_code TEXT NOT NULL,
  task_code TEXT NOT NULL,
  skill_level TEXT NOT NULL,
  area_familiarity REAL NOT NULL,
  UNIQUE(employee_id, area_code, task_code)
);
CREATE TABLE IF NOT EXISTS employee_weekly_preferences (
  id TEXT PRIMARY KEY,
  employee_id TEXT NOT NULL,
  week_start TEXT NOT NULL,
  preferred_shift_type TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS employee_weekly_leave (
  id TEXT PRIMARY KEY,
  employee_id TEXT NOT NULL,
  week_start TEXT NOT NULL,
  preferred_day_off TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS modified_reasons (
  code TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  sort_order INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS schedule_versions (
  id TEXT PRIMARY KEY,
  store_id TEXT NOT NULL,
  week_start TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  agent_summary TEXT NOT NULL,
  agent_fallback INTEGER NOT NULL,
  staffing_summary_payload TEXT
);
CREATE TABLE IF NOT EXISTS demand_results (
  id TEXT PRIMARY KEY,
  version_id TEXT NOT NULL,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schedule_items (
  id TEXT PRIMARY KEY,
  version_id TEXT NOT NULL,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS risk_items (
  id TEXT PRIMARY KEY,
  version_id TEXT NOT NULL,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS intervention_records (
  id TEXT PRIMARY KEY,
  version_id TEXT NOT NULL,
  schedule_item_id TEXT NOT NULL,
  before_payload TEXT NOT NULL,
  after_payload TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  reason_text TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_messages (
  id TEXT PRIMARY KEY,
  version_id TEXT,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hc_suggestions (
  id TEXT PRIMARY KEY,
  area_code TEXT NOT NULL,
  area_name TEXT NOT NULL,
  suggestion_type TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  expected_impact TEXT NOT NULL,
  status TEXT NOT NULL
);
"""


class SQLiteStore:
    def __init__(self, db_path: Path | None = None, seed_loader: SeedLoader | None = None) -> None:
        self.db_path = db_path or get_settings().database_path
        self.seed_loader = seed_loader or SeedLoader()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(DDL)
            self._migrate(conn)
            count = conn.execute("SELECT COUNT(*) FROM areas").fetchone()[0]
            if count == 0:
                self.load_static_seed(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(schedule_versions)").fetchall()}
        if "staffing_summary_payload" not in columns:
            conn.execute("ALTER TABLE schedule_versions ADD COLUMN staffing_summary_payload TEXT")

    def reset(self) -> None:
        with self.connect() as conn:
            for table in [
                "intervention_records",
                "agent_messages",
                "hc_suggestions",
                "areas",
                "area_tasks",
                "skill_definitions",
                "employees",
                "employee_skills",
                "employee_weekly_preferences",
                "employee_weekly_leave",
                "modified_reasons",
            ]:
                conn.execute(f"DELETE FROM {table}")
            self.load_static_seed(conn)

    def load_static_seed(self, conn: sqlite3.Connection) -> None:
        data = self.seed_loader.all()
        self._insert_many(conn, "areas", data["areas"])
        self._insert_many(conn, "area_tasks", data["area_tasks"])
        self._insert_many(conn, "skill_definitions", data["skill_definitions"])
        self._insert_many(conn, "employees", data["employees"])
        self._insert_many(conn, "employee_skills", data["employee_skills"])
        self._insert_many(conn, "employee_weekly_preferences", data["employee_weekly_preferences"])
        self._insert_many(conn, "employee_weekly_leave", data["employee_weekly_leave"])
        self._insert_many(conn, "modified_reasons", data["modified_reasons"])

    def _insert_many(self, conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        columns = list(rows[0].keys())
        placeholders = ",".join(f":{column}" for column in columns)
        column_sql = ",".join(columns)
        conn.executemany(f"INSERT OR REPLACE INTO {table} ({column_sql}) VALUES ({placeholders})", rows)

    def fetch_all(self, table: str, order_by: str | None = None) -> list[dict[str, Any]]:
        sql = f"SELECT * FROM {table}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql).fetchall()]

    def save_version(self, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO schedule_versions
                (id, store_id, week_start, generated_at, agent_summary, agent_fallback, staffing_summary_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["version_id"],
                    payload["store_id"],
                    payload["week_start"],
                    payload["generated_at"],
                    payload["agent_summary"],
                    int(payload["agent_fallback"]),
                    json.dumps(payload.get("staffing_summary"), ensure_ascii=False),
                ),
            )
            for row in payload["demand_results"]:
                conn.execute(
                    "INSERT OR REPLACE INTO demand_results VALUES (?, ?, ?)",
                    (f"{payload['version_id']}:{row['id']}", payload["version_id"], json.dumps(row, ensure_ascii=False)),
                )
            for row in payload["schedule_items"]:
                conn.execute(
                    "INSERT OR REPLACE INTO schedule_items VALUES (?, ?, ?)",
                    (f"{payload['version_id']}:{row['id']}", payload["version_id"], json.dumps(row, ensure_ascii=False)),
                )
            for row in payload["risks"]:
                conn.execute(
                    "INSERT OR REPLACE INTO risk_items VALUES (?, ?, ?)",
                    (f"{payload['version_id']}:{row['id']}", payload["version_id"], json.dumps(row, ensure_ascii=False)),
                )

    def get_version(self, version_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            version = conn.execute("SELECT * FROM schedule_versions WHERE id = ?", (version_id,)).fetchone()
            if not version:
                return None
            demand = [
                json.loads(row["payload"])
                for row in conn.execute("SELECT payload FROM demand_results WHERE version_id = ?", (version_id,))
            ]
            items = [
                json.loads(row["payload"])
                for row in conn.execute("SELECT payload FROM schedule_items WHERE version_id = ?", (version_id,))
            ]
            risks = [
                json.loads(row["payload"])
                for row in conn.execute("SELECT payload FROM risk_items WHERE version_id = ?", (version_id,))
            ]
            interventions = conn.execute(
                "SELECT COUNT(*) FROM intervention_records WHERE version_id = ?", (version_id,)
            ).fetchone()[0]
        return {
            "version_id": version["id"],
            "store_id": version["store_id"],
            "week_start": version["week_start"],
            "generated_at": version["generated_at"],
            "agent_summary": version["agent_summary"],
            "agent_fallback": bool(version["agent_fallback"]),
            "staffing_summary": json.loads(version["staffing_summary_payload"]) if version["staffing_summary_payload"] else None,
            "demand_results": demand,
            "schedule_items": items,
            "risks": risks,
            "intervention_count": interventions,
        }

    def update_version_staffing_summary(self, version_id: str, staffing_summary: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE schedule_versions SET staffing_summary_payload = ? WHERE id = ?",
                (json.dumps(staffing_summary, ensure_ascii=False), version_id),
            )

    def get_latest_version(self, store_id: str, week_start: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM schedule_versions
                WHERE store_id = ? AND week_start = ?
                ORDER BY generated_at DESC, rowid DESC
                LIMIT 1
                """,
                (store_id, week_start),
            ).fetchone()
        if not row:
            return None
        return self.get_version(row["id"])

    def list_versions(self, store_id: str | None = None, week_start: str | None = None) -> list[dict[str, Any]]:
        sql = """
            SELECT
              v.id,
              v.store_id,
              v.week_start,
              v.generated_at,
              v.agent_summary,
              COUNT(DISTINCT s.id) AS schedule_item_count,
              COUNT(DISTINCT i.id) AS intervention_count
            FROM schedule_versions v
            LEFT JOIN schedule_items s ON s.version_id = v.id
            LEFT JOIN intervention_records i ON i.version_id = v.id
        """
        conditions: list[str] = []
        params: list[Any] = []
        if store_id:
            conditions.append("v.store_id = ?")
            params.append(store_id)
        if week_start:
            conditions.append("v.week_start = ?")
            params.append(week_start)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += """
            GROUP BY v.id, v.store_id, v.week_start, v.generated_at, v.agent_summary
            ORDER BY v.generated_at DESC, v.rowid DESC
        """
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def update_schedule_item(self, version_id: str, item_id: str, item: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE schedule_items SET payload = ? WHERE version_id = ? AND id = ?",
                (json.dumps(item, ensure_ascii=False), version_id, item_id),
            )

    def add_intervention(self, record: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO intervention_records
                (id, version_id, schedule_item_id, before_payload, after_payload, reason_code, reason_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["version_id"],
                    record["schedule_item_id"],
                    json.dumps(record["before"], ensure_ascii=False),
                    json.dumps(record["after"], ensure_ascii=False),
                    record["reason_code"],
                    record.get("reason_text"),
                    record["created_at"],
                ),
            )

    def interventions(self, version_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM intervention_records WHERE version_id = ? ORDER BY created_at DESC", (version_id,)
            ).fetchall()
        return [
            {
                "id": row["id"],
                "schedule_item_id": row["schedule_item_id"],
                "before": json.loads(row["before_payload"]),
                "after": json.loads(row["after_payload"]),
                "reason_code": row["reason_code"],
                "reason_text": row["reason_text"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
