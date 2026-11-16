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

export interface AgentObservabilityAttempt {
  attempt_id: string;
  run_id: string;
  attempt_index: number;
  predecessor_attempt_id: string | null;
  started_at: string;
  ended_at: string | null;
  status: string | null;
  duration_us: number | null;
}

export interface AgentObservabilitySpan {
  span_id: string;
  run_id: string;
  attempt_id: string | null;
  parent_span_id: string | null;
  span_type: string;
  operation: string;
  kind: string;
  name: string;
  step_index: number | null;
  started_at: string;
  ended_at: string | null;
  status: string | null;
  technical_status: string | null;
  has_error: number | null;
  error_type: string | null;
  duration_us: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
}

export interface AgentObservabilityRunDetail {
  run: AgentObservabilityRun;
  attempts: AgentObservabilityAttempt[];
  spans: AgentObservabilitySpan[];
  spans_has_more: boolean;
}

export interface AgentObservabilityEvent {
  event_id: string;
  event_name: string;
  entity_kind: string;
  entity_id: string;
  phase_key: string;
  local_seq: number;
  occurred_at: string;
  metadata: Record<string, unknown>;
}

export interface AgentObservabilityEventPage {
  items: AgentObservabilityEvent[];
  next_cursor: string | null;
  generated_at: string;
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

export function getAgentObservabilityRunDetail(
  runId: string,
  query: { attemptId?: string; spanLimit?: number } = {},
  signal?: AbortSignal,
): Promise<AgentObservabilityRunDetail> {
  const params = new URLSearchParams();
  if (query.attemptId) params.set("attempt_id", query.attemptId);
  if (query.spanLimit) params.set("span_limit", String(query.spanLimit));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<AgentObservabilityRunDetail>(
    `/agent-observability/runs/${encodeURIComponent(runId)}${suffix}`,
    { signal },
  );
}

export function getAgentObservabilityRunEvents(
  runId: string,
  query: { spanId?: string; cursor?: string; limit?: number } = {},
  signal?: AbortSignal,
): Promise<AgentObservabilityEventPage> {
  const params = new URLSearchParams();
  if (query.spanId) params.set("span_id", query.spanId);
  if (query.cursor) params.set("cursor", query.cursor);
  params.set("limit", String(query.limit ?? 100));
  return request<AgentObservabilityEventPage>(
    `/agent-observability/runs/${encodeURIComponent(runId)}/events?${params.toString()}`,
    { signal },
  );
}
