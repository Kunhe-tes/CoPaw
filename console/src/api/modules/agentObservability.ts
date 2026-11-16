import { request } from "../request";

export interface AgentObservabilityRun {
  run_id: string;
  source_key: string;
  tenant_key: string;
  agent_key: string;
  chat_key: string;
  root_question_key: string;
  started_at: string;
  ended_at: string | null;
  status: string | null;
  quality: string;
  duration_us: number | null;
  llm_calls: number | null;
  tool_calls: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  span_count: number | null;
  error_span_count: number | null;
}

export interface AgentObservabilityRunPage {
  items: AgentObservabilityRun[];
  next_cursor: string | null;
  generated_at: string;
  window_start: string;
  window_end: string;
}

export interface RunQuery {
  sources?: string[];
  cursor?: string;
  start?: string;
  end?: string;
  limit?: number;
}

export interface AgentObservabilityCapabilities {
  capture_enabled: boolean;
  storage_configured: boolean;
  storage_ready: boolean;
  projector_running: boolean;
  queue_events: number;
  queue_bytes: number;
  max_event_bytes: number;
}

export interface AgentObservabilityHealth {
  capture_enabled: boolean;
  storage_ready: boolean;
  projector_running: boolean;
  dropped_events: number | null;
  generated_at: string;
}

export function getAgentObservabilityCapabilities(
  signal?: AbortSignal,
): Promise<AgentObservabilityCapabilities> {
  return request<AgentObservabilityCapabilities>(
    "/agent-observability/capabilities",
    { signal },
  );
}

export function getAgentObservabilityHealth(
  signal?: AbortSignal,
): Promise<AgentObservabilityHealth> {
  return request<AgentObservabilityHealth>("/agent-observability/health", {
    signal,
  });
}

export function listAgentObservabilityRuns(
  query: RunQuery = {},
  signal?: AbortSignal,
): Promise<AgentObservabilityRunPage> {
  const params = new URLSearchParams();
  for (const source of query.sources ?? []) params.append("source_id", source);
  if (query.cursor) params.set("cursor", query.cursor);
  if (query.start) params.set("start", query.start);
  if (query.end) params.set("end", query.end);
  params.set("limit", String(query.limit ?? 50));
  return request<AgentObservabilityRunPage>(
    `/agent-observability/runs?${params.toString()}`,
    { signal },
  );
}
