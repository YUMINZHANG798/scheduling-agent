from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ShiftType = Literal["morning", "evening", "split", "rotating"]
RiskLevel = Literal["none", "info", "warning", "critical"]


class GenerateScheduleRequest(BaseModel):
    store_id: str
    week_start: str
    instruction: str = ""
    reschedule_from: str | None = None


class DemandResult(BaseModel):
    id: str
    date: str
    weekday: str
    slot: str
    area_code: str
    area_name: str
    task_code: str
    task_name: str
    required_count: int
    professional_required_count: int = 0
    regular_required_count: int = 0
    temporary_required_count: int = 0
    demand_score: int
    demand_factors: list[str]
    priority: Literal["low", "medium", "high"]
    confidence: Literal["low", "medium", "high"]
    is_protected: int = 0


class DemandInsight(BaseModel):
    date: str
    weekday: str
    slot: str
    area_code: str
    area_name: str
    required_count: int
    professional_required_count: int = 0
    regular_required_count: int = 0
    temporary_required_count: int = 0
    demand_score: int
    demand_factors: list[str]
    priority: Literal["low", "medium", "high"]
    confidence: Literal["low", "medium", "high"]


class ScheduleItem(BaseModel):
    id: str
    version_id: str | None = None
    date: str
    weekday: str
    slot: str
    area_code: str
    area_name: str
    task_code: str
    task_name: str
    employee_id: str
    employee_name: str
    employee_type: Literal["regular", "temporary"]
    assignment_type: Literal["regular", "temporary"]
    regular_shift_type: str | None = None
    hours: float
    risk_level: RiskLevel = "none"
    explanation: str
    source: Literal["system", "manual"] = "system"
    is_protected: int = 0


class KpiResult(BaseModel):
    professional_coverage_rate: float
    baseline_achievement_rate: float
    mixed_utilization_rate: float
    peak_gap_count: int
    intervention_rate: float


class RiskItem(BaseModel):
    id: str
    type: str
    level: Literal["info", "warning", "critical"]
    description: str
    affected_item_ids: list[str] = Field(default_factory=list)
    suggestion: str


class ScheduleResponse(BaseModel):
    version_id: str
    store_id: str
    store_name: str
    week_start: str
    generated_at: str
    agent_summary: str
    agent_fallback: bool
    demand_insights: list[DemandInsight]
    demand_results: list[DemandResult]
    schedule_items: list[ScheduleItem]
    kpis: KpiResult
    risks: list[RiskItem]


class ModifyScheduleRequest(BaseModel):
    after: dict[str, Any]
    reason_code: str
    reason_text: str | None = None
    force: bool = False


class LeavePreferenceUpdateRequest(BaseModel):
    employee_id: str
    week_start: str
    preferred_day_off: Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class InterventionRecord(BaseModel):
    id: str
    schedule_item_id: str
    before: dict[str, Any]
    after: dict[str, Any]
    reason_code: str
    reason_text: str | None = None
    created_at: str


class ModifyScheduleResponse(BaseModel):
    item: ScheduleItem
    risks: list[RiskItem]
    kpis: KpiResult
    intervention_record: InterventionRecord
    requires_confirmation: bool = False


class AgentChatRequest(BaseModel):
    version_id: str | None = None
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, str]] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    message: str
    intent: str
    is_fallback: bool = True
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class ScheduleExplanationRequest(BaseModel):
    version_id: str


class RecommendSupportRequest(BaseModel):
    version_id: str
    date: str
    slot: str
    area_code: str
    task_code: str | None = None


class ExplainDemandRequest(BaseModel):
    version_id: str
    date: str
    slot: str
    area_code: str


class HcSuggestion(BaseModel):
    id: str
    area_code: str
    area_name: str
    suggestion_type: str
    title: str
    description: str
    expected_impact: str
    status: Literal["pending", "confirmed", "rejected"] = "pending"


class ConfirmHcSuggestionRequest(BaseModel):
    suggestion_id: str
    status: Literal["confirmed", "rejected"]
