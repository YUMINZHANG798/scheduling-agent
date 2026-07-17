import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api } from "./api";
import type { ChatMessage, EmployeeOption, ScheduleItem, ScheduleResponse, ScheduleVersionSummary } from "./types";

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
    {
      role: "assistant",
      content: "生成下周排班后，我会从业务视角解释为什么这样排，并支持你继续追问需求、风险和候选人。"
    }
  ]);
  const [agentInput, setAgentInput] = useState("");
  const [agentThinking, setAgentThinking] = useState(false);
  const [selectedArea, setSelectedArea] = useState(AREA_OPTIONS[0].code);
  const [employees, setEmployees] = useState<EmployeeOption[]>([]);
  const [versions, setVersions] = useState<ScheduleVersionSummary[]>([]);
  const [currentVersion, setCurrentVersion] = useState<ScheduleResponse | null>(null);
  const currentVersionRef = useRef<ScheduleResponse | null>(null);
  const [hasCurrentSessionSchedule, setHasCurrentSessionSchedule] = useState(false);
  const [viewingHistory, setViewingHistory] = useState(false);
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
      .catch(() => {
        setLeaveNotice({ type: "error", title: "加载失败", message: "正式工列表加载失败。" });
      });
  }, []);

  useEffect(() => {
    void loadInitialSchedule();
  }, []);

  useEffect(() => {
    if (leaveNotice?.type !== "success") return;
    const timer = window.setTimeout(() => setLeaveNotice(null), 3000);
    return () => window.clearTimeout(timer);
  }, [leaveNotice]);

  async function generate() {
    if (viewingHistory) {
      await returnToCurrentSchedule();
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await api.generateSchedule(WEEK_START, { rescheduleFrom });
      setSchedule(response);
      setCurrentVersion(response);
      currentVersionRef.current = response;
      setHasCurrentSessionSchedule(true);
      setViewingHistory(false);
      setRescheduleFrom(undefined);
      await refreshVersions();
      setLoading(false);
      setAgentThinking(true);
      setMessages([{ role: "assistant", content: "班表已生成，正在生成排班解释..." }]);
      let streamed = "";
      let hasStreamMessage = false;
      try {
        await api.streamScheduleExplanation(response.version_id, (delta) => {
          streamed += delta;
          if (!hasStreamMessage) {
            hasStreamMessage = true;
            setMessages([{ role: "assistant", content: streamed }]);
            return;
          }
          setMessages((items) => {
            const next = [...items];
            const lastIndex = next.length - 1;
            if (lastIndex >= 0 && next[lastIndex].role === "assistant") {
              next[lastIndex] = { ...next[lastIndex], content: streamed };
              return next;
            }
            return [...next, { role: "assistant", content: streamed }];
          });
        });
      } catch (streamErr) {
        if (streamed) {
          setMessages([{ role: "assistant", content: streamed }]);
          return;
        }
        try {
          const explanation = await api.scheduleExplanation(response.version_id);
          setMessages([
            {
              role: "assistant",
              content: explanation.message,
              sections: explanation.sections,
              suggested_questions: explanation.suggested_questions
            }
          ]);
        } catch (explainErr) {
          setMessages([
            {
              role: "assistant",
              content: "班表已生成，正在等待 LLM 返回排班解释。"
            }
          ]);
        }
      } finally {
        setAgentThinking(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败");
      setLoading(false);
    }
  }

  async function refreshVersions() {
    try {
      const rows = await api.scheduleVersions();
      setVersions(rows);
      return rows;
    } catch {
      setVersions([]);
      return [];
    }
  }

  async function loadInitialSchedule() {
    await refreshVersions();
  }

  async function returnToCurrentSchedule() {
    setLoading(true);
    setError("");
    try {
      const current = currentVersionRef.current;
      if (!hasCurrentSessionSchedule || !current) {
        setSchedule(null);
        setCurrentVersion(null);
        setViewingHistory(false);
        setAgentThinking(false);
        setMessages([{ role: "assistant", content: "当前还没有生成本周排班表，请点击生成下周排班。" }]);
        return;
      }
      setSchedule(current);
      setCurrentVersion(current);
      setViewingHistory(false);
      setAgentThinking(false);
      setMessages([{ role: "assistant", content: "已回到本周最新排班表。" }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "回到本周排班失败");
    } finally {
      setLoading(false);
    }
  }

  async function openVersion(versionId: string) {
    if (schedule?.version_id === versionId) return;
    setLoading(true);
    setError("");
    try {
      const response = await api.getSchedule(versionId);
      if (!viewingHistory && schedule?.week_start === WEEK_START) {
        setCurrentVersion(schedule);
        currentVersionRef.current = schedule;
      }
      setSchedule(response);
      setViewingHistory(currentVersionRef.current?.version_id !== versionId);
      setAgentThinking(false);
      setMessages([{ role: "assistant", content: "已打开历史排班记录。历史查询只展示班表，不调用大模型解释。" }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载历史排班失败");
    } finally {
      setLoading(false);
    }
  }

  async function reset() {
    setLoading(true);
    setError("");
    try {
      await api.resetDemo();
      await refreshVersions();
      setSchedule(null);
      setCurrentVersion(null);
      currentVersionRef.current = null;
      setHasCurrentSessionSchedule(false);
      setViewingHistory(false);
      setAgentThinking(false);
      setMessages([{ role: "assistant", content: "Demo 数据已重置，本次运行生成的排班已清空。点击生成下周排班后会进入本次历史，重启服务后不会保留。" }]);
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
      setMessages((items) => [...items, { role: "assistant", content: "请先生成下周班表，我才能基于实际排班做解释。" }]);
      return;
    }
    if (viewingHistory) {
      setMessages((items) => [
        ...items,
        { role: "assistant", content: "当前是历史排班查看模式，不调用大模型。请回到本周排班表后再询问 Agent。" }
      ]);
      return;
    }

    const friday = schedule.demand_insights.find((item) => item.weekday === "Friday") ?? schedule.demand_insights[0];
    const userMessage: ChatMessage = { role: "user", content: trimmed };
    const history = [...messages, userMessage];
    setMessages(history);
    setAgentInput("");
    setAgentThinking(true);
    try {
      const response = await api.chat(
        schedule.version_id,
        trimmed,
        {
          date: friday?.date,
          slot: friday?.slot ?? "18:00-19:00",
          area_code: friday?.area_code ?? "produce",
          task_code: "restock"
        },
        history
      );
      setMessages((items) => [
        ...items,
        {
          role: "assistant",
          content: response.message,
          sections: response.sections,
          suggested_questions: response.suggested_questions
        }
      ]);
    } catch (err) {
      setMessages((items) => [
        ...items,
        { role: "assistant", content: err instanceof Error ? err.message : "Agent 暂时无法回答，请稍后再试。" }
      ]);
    } finally {
      setAgentThinking(false);
    }
  }

  function submitAgentQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void askAgent(agentInput);
  }

  async function submitLeavePreference() {
    if (!leaveEmployeeId) {
      setLeaveNotice({ type: "error", title: "提交失败", message: "请选择正式工。" });
      return;
    }
    if (!isLeaveDaySelectable(leaveDay)) {
      setLeaveNotice({ type: "error", title: "提交失败", message: "请假至少需要提前一天提交。" });
      return;
    }
    const currentSchedule = schedule;
    setLeaveSubmitting(true);
    try {
      const response = await api.updateLeavePreference(leaveEmployeeId, WEEK_START, leaveDay);
      const updatedSchedule = await api.generateSchedule(WEEK_START, { rescheduleFrom: response.effective_date });
      const dayName = DAY_OPTIONS.find((day) => day.code === response.preferred_day_off)?.name ?? response.preferred_day_off;
      setSchedule(updatedSchedule);
      setCurrentVersion(updatedSchedule);
      currentVersionRef.current = updatedSchedule;
      setHasCurrentSessionSchedule(true);
      setViewingHistory(false);
      setRescheduleFrom(undefined);
      void refreshVersions();
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
        message: err instanceof Error ? err.message : "休假申请提交失败。"
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
          <button className="icon-button secondary" onClick={reset} disabled={loading} title="重置 Demo">↻</button>
          <button className="primary-button" onClick={generate} disabled={loading}>
            {loading ? "处理中..." : viewingHistory ? "回到本周排班表" : schedule ? "重新生成" : "生成下周排班"}
          </button>
        </div>
      </header>

      {error && <div className="error-strip">{error}</div>}

      <StaffingSummaryPanel schedule={schedule} />

      <section className="workbench-grid">
        <aside className="panel area-panel">
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
          <HistoryPanel versions={versions} activeVersionId={schedule?.version_id} onOpen={openVersion} />
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
                  <p>{message.content}</p>
                  {message.role === "assistant" && !!message.sections?.length && (
                    <div className="chat-sections">
                      {message.sections.map((section) => (
                        <section className="chat-section" key={`${index}-${section.title}`}>
                          <strong>{section.title}</strong>
                          <ul>
                            {section.bullets.map((bullet) => (
                              <li key={bullet}>{bullet}</li>
                            ))}
                          </ul>
                        </section>
                      ))}
                    </div>
                  )}
                  {message.role === "assistant" && !!message.suggested_questions?.length && (
                    <div className="chat-suggestions">
                      {message.suggested_questions.map((item) => (
                        <button key={item} type="button" onClick={() => void askAgent(item)} disabled={agentThinking}>
                          {item}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {agentThinking && (
                <div className="chat-bubble assistant">
                  <p>正在结合班表、需求预测和人员约束生成解释...</p>
                </div>
              )}
            </div>
            <form className="chat-form" onSubmit={submitAgentQuestion}>
              <textarea
                value={agentInput}
                onChange={(event) => setAgentInput(event.target.value)}
                placeholder={schedule ? "询问排班原因、风险、补位候选和需求变化..." : "先生成下周排班"}
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
    </main>
  );
}

function StaffingSummaryPanel({ schedule }: { schedule: ScheduleResponse | null }) {
  const summary = schedule?.staffing_summary;
  const groups = [
    { title: "总员工", data: summary?.total },
    { title: "正式工", data: summary?.regular },
    { title: "小时工", data: summary?.temporary }
  ];

  return (
    <section className="staffing-summary" aria-label="人员数量总览">
      {groups.map((group) => (
        <div className="staffing-card" key={group.title}>
          <strong>{group.title}</strong>
          <div className="staffing-main">
            <span>总数</span>
            <b>{group.data?.total_count ?? 0}</b>
          </div>
          <dl>
            <div>
              <dt>本周被排班</dt>
              <dd>{group.data?.scheduled_count ?? 0}</dd>
            </div>
            <div>
              <dt>未被安排</dt>
              <dd>{group.data?.unscheduled_count ?? 0}</dd>
            </div>
            <div>
              <dt>请假人数</dt>
              <dd>{group.data?.leave_count ?? 0}</dd>
            </div>
          </dl>
        </div>
      ))}
    </section>
  );
}

function HistoryPanel({
  versions,
  activeVersionId,
  onOpen
}: {
  versions: ScheduleVersionSummary[];
  activeVersionId?: string;
  onOpen: (versionId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [weekFilter, setWeekFilter] = useState("");
  const weekOptions = useMemo(() => {
    return Array.from(new Set(versions.map((version) => version.week_start))).sort().reverse();
  }, [versions]);
  const filteredVersions = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return versions.filter((version) => {
      if (weekFilter && version.week_start !== weekFilter) return false;
      if (!keyword) return true;
      return [
        version.id,
        version.week_start,
        version.generated_at,
        version.store_name
      ].some((value) => value.toLowerCase().includes(keyword));
    });
  }, [query, versions, weekFilter]);

  return (
    <div className="history-panel">
      <PanelTitle title="历史排班" />
      <div className="history-filters">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索日期 / 版本号"
        />
        <select value={weekFilter} onChange={(event) => setWeekFilter(event.target.value)}>
          <option value="">全部周</option>
          {weekOptions.map((week) => (
            <option value={week} key={week}>{week}</option>
          ))}
        </select>
      </div>
      <div className="history-list">
        {filteredVersions.slice(0, 20).map((version) => (
          <button
            type="button"
            key={version.id}
            className={activeVersionId === version.id ? "active" : ""}
            onClick={() => void onOpen(version.id)}
          >
            <strong>{formatDateTime(version.generated_at)}</strong>
            <span>{version.week_start} · {version.schedule_item_count} 条</span>
          </button>
        ))}
        {!versions.length && <p className="muted">生成排班后会显示在本次运行历史，重启服务后清空。</p>}
        {!!versions.length && !filteredVersions.length && <p className="muted">没有匹配的历史排班。</p>}
      </div>
    </div>
  );
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function slotStartMinutes(slot: string) {
  const [hour, minute] = slot.slice(0, 5).split(":").map(Number);
  return hour * 60 + minute;
}

function employeeTypeOrder(type: ScheduleItem["employee_type"]) {
  return type === "regular" ? 0 : 1;
}

function PanelTitle({ title, action }: { title: string; action?: string }) {
  return (
    <div className="panel-title">
      <h2>{title}</h2>
      {action && <code>{action}</code>}
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
                  {employee.employee_name}{employee.is_protected ? " · 专业岗" : ""}
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
        {disabled ? "提交中..." : "提交申请"}
      </button>
      {notice && (
        <div className={`leave-notice ${notice.type}`} role="status">
          <div>
            <strong>{notice.title}</strong>
            <p>{notice.message}</p>
          </div>
          {notice.type === "error" && (
            <button type="button" onClick={onDismissNotice} aria-label="关闭提示">
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
  return <div className="empty-state">点击生成按钮后，这里会展示 7 天混排班表。</div>;
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
