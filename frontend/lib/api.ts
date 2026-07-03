const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

export type Supervisor = {
  id: string;
  name: string;
  base_instruction: string;
  tools: string[];
  wake_up_guidance: string;
  model_config_json: Record<string, any>;
  created_at: string;
};

export type Run = {
  id: string;
  order_id: string;
  supervisor_id: string;
  workflow_id: string;
  status: string;
  next_wake_time: string | null;
  memory_summary: string;
  extra_instructions: string[];
  final_summary: Record<string, any> | null;
  order_context: Record<string, any>;
  created_at: string;
  updated_at: string;
};

export type TimelineEvent = {
  id: string;
  run_id: string;
  type: string;
  payload: Record<string, any>;
  important: boolean;
  created_at: string;
};

export type RunDetail = Run & { timeline: TimelineEvent[] };

export const api = {
  listSupervisors: () => request<Supervisor[]>("/api/supervisors"),
  createSupervisor: (body: Partial<Supervisor>) =>
    request<Supervisor>("/api/supervisors", { method: "POST", body: JSON.stringify(body) }),

  listRuns: () => request<Run[]>("/api/runs"),
  getRun: (id: string) => request<RunDetail>(`/api/runs/${id}`),
  createRun: (body: { order_id: string; supervisor_id: string; order_context?: Record<string, any>; base_instruction_override?: string }) =>
    request<Run>("/api/runs", { method: "POST", body: JSON.stringify(body) }),

  sendEvent: (runId: string, event_type: string, payload: Record<string, any> = {}) =>
    request<Run>(`/api/runs/${runId}/events`, {
      method: "POST",
      body: JSON.stringify({ event_type, payload }),
    }),
  addInstruction: (runId: string, instruction: string) =>
    request<Run>(`/api/runs/${runId}/instructions`, { method: "POST", body: JSON.stringify({ instruction }) }),
  interrupt: (runId: string) => request<Run>(`/api/runs/${runId}/interrupt`, { method: "POST" }),
  resume: (runId: string) => request<Run>(`/api/runs/${runId}/resume`, { method: "POST" }),
  terminate: (runId: string, reason = "manually terminated by user") =>
    request<Run>(`/api/runs/${runId}/terminate`, { method: "POST", body: JSON.stringify({ reason }) }),
};
