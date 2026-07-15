export interface DemandInsight {
  date: string;
  weekday: string;
  slot: string;
  area_code: string;
  area_name: string;
  required_count: number;
  professional_required_count: number;
  regular_required_count: number;
  temporary_required_count: number;
  demand_score: number;
  demand_factors: string[];
  priority: "low" | "medium" | "high";
  confidence: "low" | "medium" | "high";
}

export interface ScheduleItem {
  id: string;
  version_id?: string;
  date: string;
  weekday: string;
  slot: string;
  area_code: string;
  area_name: string;
  task_code: string;
  task_name: string;
  employee_id: string;
  employee_name: string;
  employee_type: "regular" | "temporary";
  assignment_type: "regular" | "temporary";
  regular_shift_type?: string | null;
  hours: number;
  risk_level: string;
  explanation: string;
  source: "system" | "manual";
  is_protected: number;
}

export interface RiskItem {
  id: string;
  type: string;
  level: "info" | "warning" | "critical";
  description: string;
  affected_item_ids: string[];
  suggestion: string;
}

export interface Kpis {
  professional_coverage_rate: number;
  baseline_achievement_rate: number;
  mixed_utilization_rate: number;
  peak_gap_count: number;
  intervention_rate: number;
}

export interface ScheduleResponse {
  version_id: string;
  store_id: string;
  store_name: string;
  week_start: string;
  generated_at: string;
  agent_summary: string;
  agent_fallback: boolean;
  demand_insights: DemandInsight[];
  schedule_items: ScheduleItem[];
  kpis: Kpis;
  risks: RiskItem[];
}

export interface GenerateScheduleOptions {
  rescheduleFrom?: string;
}

export interface Candidate {
  employee_id: string;
  employee_name: string;
  skill_level: string;
  weekly_hours: number;
  weekly_hours_limit: number;
  score: number;
  reason: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AgentResponse {
  message: string;
  intent: string;
  is_fallback: boolean;
  candidates: Candidate[];
}

export interface EmployeeOption {
  employee_id: string;
  employee_name: string;
  area_code: string;
  area_name: string;
  is_protected: number;
}
