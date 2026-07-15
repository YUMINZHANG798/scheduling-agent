import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { api } from "./api";
import type { ChatMessage, EmployeeOption, ScheduleItem, ScheduleResponse } from "./types";

const WEEK_START = "2026-07-13";
const BUSINESS_TODAY = "2026-07-15";
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const AREA_ORDER = ["aquatic", "meat", "produce", "cashier", "replenishment"];
const AREA_OPTIONS = [
  { code: "aquatic", name: "水产区" },
  { code: "meat", name: "肉类区" },
  { code: "produce", name: "果蔬区" },
  { code: "cashier", name: "收银/前场" },
  { code: "replenishment", name: "补货区" }
];
const DAY_OPTIONS = [
  { code: "Monday", name: "周一" },
  { code: "Tuesday", name: "周二" },
  { code: "Wednesday", name: "周三" },
  { code: "Thursday", name: "周四" },
  { code: "Friday", name: "周五" },
  { code: "Saturday", name: "周六" },
  { code: "Sunday", name: "周日" }
];

function percent(value?: number) {
  return `${Math.round((value ?? 0) * 100)}%`;
}

type LeaveNotice = {
  type: "success" | "error";
  title: string;
  message: string;
};

export function App() {
  const [schedule, setSchedule] = useState<ScheduleResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [leaveSubmitting, setLeaveSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "assistant", content: "生成下周排班后，我会说明本次排班原因。之后可以在这里继续追问排班相关问题。" }
  ]);
  const [agentInput, setAgentInput] = useState("");
  const [agentThinking, setAgentThinking] = useState(false);
  const [selectedArea, setSelectedArea] = useState(AREA_OPTIONS[0].code);
  const [employees, setEmployees] = useState<EmployeeOption[]>([]);
  const [leaveEmployeeId, setLeaveEmployeeId] = useState("");
  const [leaveDay, setLeaveDay] = useState("Thursday");
  const [leaveNotice, setLeaveNotice] = useState<LeaveNotice | null>(null);
  const [rescheduleFrom, setRescheduleFrom] = useState<string | undefined>();

  useEffect(() => {
    api.leaveOptions()
      .then((options) => {
        setEmployees(options);
        setLeaveEmployeeId((current) => current || options[0]?.employee_id || "");
      })
      .catch(() => setLeaveNotice({ type: "error", title: "申请失败", message: "正式工列表加载失败" }));
  }, []);

  useEffect(() => {
    if (leaveNotice?.type !== "success") return;
    const timer = window.setTimeout(() => setLeaveNotice(null), 3000);
    return () => window.clearTimeout(timer);
  }, [leaveNotice]);

  async function generate() {
    setLoading(true);
    setError("");
    try {
      const response = await api.generateSchedule(WEEK_START, { rescheduleFrom });
      setSchedule(response);
      setRescheduleFrom(undefined);
      setMessages([{ role: "assistant", content: "" }]);
      await api.streamScheduleExplanation(response.version_id, (delta) => appendAssistantDelta(delta));
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败");
    } finally {
      setLoading(false);
    }
  }

  async function reset() {
    setLoading(true);
    setError("");
    try {
      await api.resetDemo();
      setSchedule(null);
      setMessages([{ role: "assistant", content: "Demo 数据已重置，可以重新生成班表。" }]);
      setAgentInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "重置失败");
    } finally {
      setLoading(false);
    }
  }

  async function askAgent(question: string) {
    const trimmed = question.trim();
    if (!trimmed) return;
    if (!schedule) {
      setMessages((items) => [...items, { role: "assistant", content: "请先生成下周班表，我才能基于具体班表回答。" }]);
      return;
    }
    const friday = schedule.demand_insights.find((item) => item.weekday === "Friday") ?? schedule.demand_insights[0];
    const userMessage: ChatMessage = { role: "user", content: trimmed };
    const history = [...messages, userMessage];
    setMessages([...history, { role: "assistant", content: "" }]);
    setAgentInput("");
    setAgentThinking(true);
    try {
      await api.streamChat(
        schedule.version_id,
        trimmed,
        (delta) => appendAssistantDelta(delta),
        {
          date: friday?.date,
          slot: friday?.slot ?? "18:00-19:00",
          area_code: friday?.area_code ?? "produce",
          task_code: "restock"
        },
        history
      );
    } catch (err) {
      replaceLastAssistant(err instanceof Error ? err.message : "Agent 暂时无法回答，请稍后再试。");
    } finally {
      setAgentThinking(false);
    }
  }

  function submitAgentQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void askAgent(agentInput);
  }

  function appendAssistantDelta(delta: string) {
    setMessages((items) => {
      const next = [...items];
      const last = next[next.length - 1];
      if (!last || last.role !== "assistant") return [...next, { role: "assistant", content: delta }];
      next[next.length - 1] = { ...last, content: last.content + delta };
      return next;
    });
  }

  function replaceLastAssistant(content: string) {
    setMessages((items) => {
      const next = [...items];
      const last = next[next.length - 1];
      if (!last || last.role !== "assistant") return [...next, { role: "assistant", content }];
      next[next.length - 1] = { ...last, content };
      return next;
    });
  }

  async function submitLeavePreference() {
    if (!leaveEmployeeId) {
      setLeaveNotice({ type: "error", title: "申请失败", message: "请选择正式工" });
      return;
    }
    if (!isLeaveDaySelectable(leaveDay)) {
      setLeaveNotice({ type: "error", title: "申请失败", message: "请假至少需要提前一天，已过去或当天的班表不能修改。" });
      return;
    }
    const currentSchedule = schedule;
    setLeaveSubmitting(true);
    try {
      const response = await api.updateLeavePreference(leaveEmployeeId, WEEK_START, leaveDay);
      const updatedSchedule = await api.generateSchedule(WEEK_START, { rescheduleFrom: response.effective_date });
      const dayName = DAY_OPTIONS.find((day) => day.code === response.preferred_day_off)?.name ?? response.preferred_day_off;
      setSchedule(updatedSchedule);
      setRescheduleFrom(undefined);
      setLeaveNotice({
        type: "success",
        title: "申请成功",
        message: `${response.employee_name} 已提交 ${dayName} 休假申请，班表已从休假日开始自动重排。`
      });
    } catch (err) {
      setSchedule(currentSchedule);
      setLeaveNotice({
        type: "error",
        title: "申请失败",
        message: err instanceof Error ? err.message : "休假申请提交失败"
      });
    } finally {
      setLeaveSubmitting(false);
    }
  }

  const groupedByDay = useMemo(() => {
    const rows = new Map<string, ScheduleItem[]>();
    for (const day of DAYS) rows.set(day, []);
    for (const item of schedule?.schedule_items ?? []) {
      if (item.area_code !== selectedArea) continue;
      rows.get(item.weekday)?.push(item);
    }
    for (const items of rows.values()) {
      items.sort((a, b) => {
        const startDiff = slotStartMinutes(a.slot) - slotStartMinutes(b.slot);
        if (startDiff !== 0) return startDiff;
        const typeDiff = employeeTypeOrder(a.employee_type) - employeeTypeOrder(b.employee_type);
        if (typeDiff !== 0) return typeDiff;
        return AREA_ORDER.indexOf(a.area_code) - AREA_ORDER.indexOf(b.area_code) || a.employee_name.localeCompare(b.employee_name, "zh-CN");
      });
    }
    return rows;
  }, [schedule, selectedArea]);

  const selectedAreaName = AREA_OPTIONS.find((area) => area.code === selectedArea)?.name ?? "";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">社区生鲜示范店 · fresh_store_001</p>
          <h1>智慧排班 Agent</h1>
        </div>
        <div className="toolbar">
          <span className="week-pill">2026-07-13 至 2026-07-19</span>
          <button className="icon-button secondary" onClick={reset} disabled={loading} title="重置 Demo">↺</button>
          <button className="primary-button" onClick={generate} disabled={loading}>
            {loading ? "生成中" : "生成下周半混班班表"}
          </button>
        </div>
      </header>

      {error && <div className="error-strip">{error}</div>}

      <section className="summary-band">
        <Kpi label="专业岗覆盖" value={percent(schedule?.kpis.professional_coverage_rate)} tone="green" />
        <Kpi label="区域保底达成" value={percent(schedule?.kpis.baseline_achievement_rate)} tone="blue" />
        <Kpi label="混排池利用" value={percent(schedule?.kpis.mixed_utilization_rate)} tone="teal" />
        <Kpi label="人工干预率" value={percent(schedule?.kpis.intervention_rate)} tone="gray" />
        <Kpi label="高峰缺口" value={String(schedule?.kpis.peak_gap_count ?? 0)} tone="amber" />
      </section>

      <section className="workbench-grid">
        <aside className="panel area-panel">
          <PanelTitle title="区域保底" />
          <AreaRows schedule={schedule} />
          <LeaveRequestPanel
            employees={employees}
            employeeId={leaveEmployeeId}
            day={leaveDay}
            notice={leaveNotice}
            disabled={leaveSubmitting}
            onEmployeeChange={setLeaveEmployeeId}
            onDayChange={setLeaveDay}
            onSubmit={submitLeavePreference}
            onDismissNotice={() => setLeaveNotice(null)}
          />
        </aside>

        <section className="panel board-panel">
          <PanelTitle title={`一周班表 · ${selectedAreaName}`} action={schedule?.version_id} />
          <AreaSwitcher selectedArea={selectedArea} onSelect={setSelectedArea} schedule={schedule} />
          {!schedule ? <EmptyState /> : <WeekBoard groupedByDay={groupedByDay} />}
        </section>

        <aside className="panel agent-panel">
          <PanelTitle title="Agent" />
          <div className="chat-window">
            <div className="chat-list">
              {messages.map((message, index) => (
                <div key={index} className={`chat-bubble ${message.role}`}>
                  {message.content}
                </div>
              ))}
              {agentThinking && !messages[messages.length - 1]?.content && (
                <div className="chat-bubble assistant">正在结合班表、需求预测和人员约束分析...</div>
              )}
            </div>
            <form className="chat-form" onSubmit={submitAgentQuestion}>
              <textarea
                value={agentInput}
                onChange={(event) => setAgentInput(event.target.value)}
                placeholder={schedule ? "询问排班原因、支援候选、请假影响..." : "先生成下周排班"}
                disabled={agentThinking}
                rows={3}
              />
              <button type="submit" disabled={agentThinking || !agentInput.trim()}>
                发送
              </button>
            </form>
          </div>
        </aside>
      </section>

      <section className="bottom-grid">
        <div className="panel">
          <PanelTitle title="需求洞察" />
          <div className="insight-list">
            {(schedule?.demand_insights ?? []).slice(0, 8).map((item) => (
              <div key={`${item.date}-${item.slot}-${item.area_code}`} className="insight-row">
                <strong>{item.area_name}</strong>
                <span>{item.date} {item.slot}</span>
                <meter min={0} max={100} value={item.demand_score} />
                <span>
                  师傅 {item.professional_required_count} · 正式 {item.regular_required_count} · 小时工 {item.temporary_required_count}
                </span>
              </div>
            ))}
          </div>
        </div>
        <div className="panel">
          <PanelTitle title="风险与缺口" />
          <div className="risk-list">
            {(schedule?.risks ?? []).slice(0, 8).map((risk) => (
              <div className="risk-row" key={risk.id}>
                <span className={`risk-dot ${risk.level}`} />
                <p>{risk.description}</p>
              </div>
            ))}
            {!schedule && <p className="muted">生成班表后展示风险。</p>}
          </div>
        </div>
      </section>
    </main>
  );
}

function slotStartMinutes(slot: string) {
  const [hour, minute] = slot.slice(0, 5).split(":").map(Number);
  return hour * 60 + minute;
}

function employeeTypeOrder(type: ScheduleItem["employee_type"]) {
  return type === "regular" ? 0 : 1;
}

function Kpi({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className={`kpi ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PanelTitle({ title, action }: { title: string; action?: string }) {
  return (
    <div className="panel-title">
      <h2>{title}</h2>
      {action && <code>{action}</code>}
    </div>
  );
}

function AreaRows({ schedule }: { schedule: ScheduleResponse | null }) {
  const rows = useMemo(() => {
    if (!schedule) return [];
    const byArea = new Map<string, { area: string; regular: number; temp: number; protected: number }>();
    for (const item of schedule.schedule_items) {
      const row = byArea.get(item.area_code) ?? { area: item.area_name, regular: 0, temp: 0, protected: 0 };
      if (item.employee_type === "regular") row.regular += 1;
      if (item.employee_type === "temporary") row.temp += 1;
      if (item.is_protected) row.protected += 1;
      byArea.set(item.area_code, row);
    }
    return AREA_ORDER.map((code) => byArea.get(code)).filter(Boolean) as { area: string; regular: number; temp: number; protected: number }[];
  }, [schedule]);

  if (!schedule) return <p className="muted">生成后显示各区域正式工、临时工与专业保护覆盖。</p>;

  return (
    <div className="area-list">
      {rows.map((row) => (
        <div className="area-row" key={row.area}>
          <strong>{row.area}</strong>
          <span>正式工 {row.regular}</span>
          <span>临时 {row.temp}</span>
          <span>保护 {row.protected}</span>
        </div>
      ))}
    </div>
  );
}

function LeaveRequestPanel({
  employees,
  employeeId,
  day,
  notice,
  disabled,
  onEmployeeChange,
  onDayChange,
  onSubmit,
  onDismissNotice
}: {
  employees: EmployeeOption[];
  employeeId: string;
  day: string;
  notice: LeaveNotice | null;
  disabled: boolean;
  onEmployeeChange: (employeeId: string) => void;
  onDayChange: (day: string) => void;
  onSubmit: () => void;
  onDismissNotice: () => void;
}) {
  const groupedEmployees = useMemo(() => {
    return employees.reduce<Record<string, EmployeeOption[]>>((groups, employee) => {
      groups[employee.area_name] = groups[employee.area_name] ?? [];
      groups[employee.area_name].push(employee);
      return groups;
    }, {});
  }, [employees]);

  return (
    <div className="leave-panel">
      <h2>周休假申请</h2>
      <label>
        <span>正式工</span>
        <select value={employeeId} onChange={(event) => onEmployeeChange(event.target.value)} disabled={disabled || !employees.length}>
          {Object.entries(groupedEmployees).map(([areaName, areaEmployees]) => (
            <optgroup label={areaName} key={areaName}>
              {areaEmployees.map((employee) => (
                <option value={employee.employee_id} key={employee.employee_id}>
                  {employee.employee_name}{employee.is_protected ? " · 专业" : ""}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>
      <label>
        <span>休假日</span>
        <select value={day} onChange={(event) => onDayChange(event.target.value)} disabled={disabled}>
          {DAY_OPTIONS.map((item) => (
            <option value={item.code} key={item.code} disabled={!isLeaveDaySelectable(item.code)}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      <button type="button" onClick={onSubmit} disabled={disabled || !employeeId}>
        {disabled ? "提交中" : "提交申请"}
      </button>
      {notice && (
        <div className={`leave-notice ${notice.type}`} role="status">
          <div>
            <strong>{notice.title}</strong>
            <p>{notice.message}</p>
          </div>
          {notice.type === "error" && (
            <button type="button" onClick={onDismissNotice} aria-label="关闭申请失败提示">
              ×
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function isLeaveDaySelectable(dayCode: string) {
  return dayOffDate(dayCode) > BUSINESS_TODAY;
}

function dayOffDate(dayCode: string) {
  const start = new Date(`${WEEK_START}T00:00:00`);
  const offset = DAYS.indexOf(dayCode);
  start.setDate(start.getDate() + offset);
  return start.toISOString().slice(0, 10);
}

function EmptyState() {
  return <div className="empty-state">点击生成按钮后，这里会展示 7 天半混班班表。</div>;
}

function AreaSwitcher({
  selectedArea,
  onSelect,
  schedule
}: {
  selectedArea: string;
  onSelect: (areaCode: string) => void;
  schedule: ScheduleResponse | null;
}) {
  const counts = useMemo(() => {
    const areaCounts = new Map<string, number>();
    for (const item of schedule?.schedule_items ?? []) {
      areaCounts.set(item.area_code, (areaCounts.get(item.area_code) ?? 0) + 1);
    }
    return areaCounts;
  }, [schedule]);

  return (
    <div className="area-switcher" role="tablist" aria-label="区域排班切换">
      {AREA_OPTIONS.map((area) => (
        <button
          key={area.code}
          type="button"
          role="tab"
          aria-selected={selectedArea === area.code}
          className={selectedArea === area.code ? "active" : ""}
          onClick={() => onSelect(area.code)}
        >
          <span>{area.name}</span>
          <strong>{counts.get(area.code) ?? 0}</strong>
        </button>
      ))}
    </div>
  );
}

function WeekBoard({ groupedByDay }: { groupedByDay: Map<string, ScheduleItem[]> }) {
  return (
    <div className="week-board">
      {DAYS.map((day) => (
        <div className="day-column" key={day}>
          <h3>{day}</h3>
          <div className="assignment-list">
            {(groupedByDay.get(day) ?? []).map((item) => (
              <div className={`assignment ${item.assignment_type}`} key={item.id} title={item.explanation}>
                <span className="assignment-time">{item.slot}</span>
                <strong>{item.employee_name}</strong>
                <span>{item.area_name} · {item.task_name}</span>
              </div>
            ))}
            {(groupedByDay.get(day) ?? []).length === 0 && <p className="muted">本区域当日无排班</p>}
          </div>
        </div>
      ))}
    </div>
  );
}
