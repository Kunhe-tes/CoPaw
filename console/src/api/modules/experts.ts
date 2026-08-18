import { request } from "../request";

export interface ExpertPayload {
  name: string;
  description: string;
  instruction: string;
  trigger_keywords: string[];
  skills: string[];
  mcps: string[] | null;
  tools: Record<string, unknown>;
  model: Record<string, string> | null;
  budget: Record<string, number>;
}

export interface AgentOwnedExpertMetadata {
  declared_skills: string[];
  declared_mcps: string[] | null;
}

export interface ExpertDefinition {
  name: string;
  description: string;
  instruction: string;
  trigger_keywords: string[];
  agent_owned: AgentOwnedExpertMetadata | null;
}

export interface Expert {
  definition_id: string;
  revision: string;
  valid: boolean;
  validation_error: string;
  enabled: boolean;
  definition: ExpertDefinition | null;
  toml: string;
}

const mutation = (method: "POST" | "PUT" | "DELETE", body?: unknown, revision?: string) => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
  headers: revision ? { "If-Match": revision } : undefined,
});

export const expertsApi = {
  listExperts: () => request<Expert[]>("/experts"),
  previewExpert: (payload: ExpertPayload) => request<Expert>("/experts/preview", mutation("POST", payload)),
  createExpert: (payload: ExpertPayload) => request<Expert>("/experts", mutation("POST", payload)),
  updateExpert: (id: string, payload: ExpertPayload, revision: string) =>
    request<Expert>(`/experts/${encodeURIComponent(id)}`, mutation("PUT", payload, revision)),
  enableExpert: (id: string, revision: string) =>
    request<Expert>(`/experts/${encodeURIComponent(id)}/enable`, mutation("POST", undefined, revision)),
  disableExpert: (id: string, revision: string) =>
    request<Expert>(`/experts/${encodeURIComponent(id)}/disable`, mutation("POST", undefined, revision)),
  deleteExpert: (id: string, revision: string) =>
    request<void>(`/experts/${encodeURIComponent(id)}`, mutation("DELETE", undefined, revision)),
};
