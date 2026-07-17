import type { AgentResponse, Candidate, ChatMessage, EmployeeOption, GenerateScheduleOptions, ScheduleResponse, ScheduleVersionSummary } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) },
    ...options
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail?.detail?.message ?? detail?.detail?.error_code ?? detail?.message ?? `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function streamRequest(path: string, body: unknown, onDelta: (delta: string) => void): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail?.detail?.message ?? detail?.detail?.error_code ?? detail?.message ?? `HTTP ${response.status}`);
  }
  if (!response.body) throw new Error("浏览器不支持流式响应");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const event of events) {
      const dataLines = event
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim());
      if (!dataLines.length) continue;
      const payload = JSON.parse(dataLines.join("\n")) as { delta?: string; error?: string; done?: boolean };
      if (payload.error) throw new Error(payload.error);
      if (payload.delta) {
        onDelta(payload.delta);
        await nextPaint();
      }
    }
  }
}

function nextPaint() {
  return new Promise<void>((resolve) => {
    window.requestAnimationFrame(() => resolve());
  });
}

function toApiHistory(history: ChatMessage[]) {
  return history.map((item) => ({
    role: item.role,
    content: item.content
  }));
}

export const api = {
  generateSchedule(weekStart: string, options: GenerateScheduleOptions = {}) {
    return request<ScheduleResponse>("/schedule/generate", {
      method: "POST",
      body: JSON.stringify({
        store_id: "fresh_store_001",
        week_start: weekStart,
        instruction: "根据历史数据、天气和节假日生成下周半混班班表",
        reschedule_from: options.rescheduleFrom
      })
    });
  },
  leaveOptions() {
    return request<EmployeeOption[]>("/schedule/leave-options");
  },
  scheduleVersions(weekStart?: string) {
    const query = weekStart ? `?week_start=${encodeURIComponent(weekStart)}` : "";
    return request<ScheduleVersionSummary[]>(`/schedule/versions${query}`);
  },
  getSchedule(versionId: string) {
    return request<ScheduleResponse>(`/schedule/${versionId}`);
  },
  updateLeavePreference(employeeId: string, weekStart: string, preferredDayOff: string) {
    return request<{ message: string; employee_name: string; preferred_day_off: string; effective_date: string }>("/schedule/leave-preferences", {
      method: "POST",
      body: JSON.stringify({
        employee_id: employeeId,
        week_start: weekStart,
        preferred_day_off: preferredDayOff
      })
    });
  },
  resetDemo() {
    return request<{ ok: boolean; message: string }>("/demo/reset", { method: "POST" });
  },
  chat(versionId: string, message: string, context = {}, history: ChatMessage[] = []) {
    return request<AgentResponse>("/agent/chat", {
      method: "POST",
      body: JSON.stringify({ version_id: versionId, message, context, history: toApiHistory(history) })
    });
  },
  streamChat(versionId: string, message: string, onDelta: (delta: string) => void, context = {}, history: ChatMessage[] = []) {
    return streamRequest("/agent/chat/stream", { version_id: versionId, message, context, history: toApiHistory(history) }, onDelta);
  },
  scheduleExplanation(versionId: string) {
    return request<AgentResponse>("/agent/schedule-explanation", {
      method: "POST",
      body: JSON.stringify({ version_id: versionId })
    });
  },
  streamScheduleExplanation(versionId: string, onDelta: (delta: string) => void) {
    return streamRequest("/agent/schedule-explanation/stream", { version_id: versionId }, onDelta);
  },
  recommend(versionId: string, date: string, slot: string, areaCode: string, taskCode?: string) {
    return request<{ candidates: Candidate[] }>("/agent/recommend-support", {
      method: "POST",
      body: JSON.stringify({ version_id: versionId, date, slot, area_code: areaCode, task_code: taskCode })
    });
  },
  modify(versionId: string, itemId: string, after: Record<string, unknown>, reasonText: string) {
    return request(`/schedule/${versionId}/items/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify({
        after,
        reason_code: "manager_experience",
        reason_text: reasonText,
        force: true
      })
    });
  },
  optimizeHc(versionId: string) {
    return request<{ suggestions: unknown[] }>("/hc/optimize", {
      method: "POST",
      body: JSON.stringify({ version_id: versionId })
    });
  }
};
