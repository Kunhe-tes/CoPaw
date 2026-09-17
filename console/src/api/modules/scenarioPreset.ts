import { request } from "../request";
import type {
  EffectiveScenarioPresetCatalog,
  ScenarioPresetBinding,
  ScenarioPresetNode,
  ScenarioPresetNodeKind,
} from "../types/scenarioPreset";

/** Read-only new-chat scenario catalog for the current Source. */
export const scenarioPresetApi = {
  getEffectiveCatalog: () =>
    request<EffectiveScenarioPresetCatalog>("/scenario-presets/catalog"),
  getAdminCatalog: () =>
    request<{ nodes: ScenarioPresetNode[] }>("/scenario-presets/admin/catalog"),
  createNode: (payload: {
    kind: ScenarioPresetNodeKind;
    parent_id?: string | null;
    name: string;
    prompt_draft?: string;
    is_active?: boolean;
  }) =>
    request<ScenarioPresetNode>("/scenario-presets/admin/nodes", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateNode: (
    id: string,
    payload: Partial<Pick<ScenarioPresetNode, "name" | "prompt_draft" | "is_active">>,
  ) =>
    request<ScenarioPresetNode>(`/scenario-presets/admin/nodes/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  moveNode: (id: string, parent_id: string) =>
    request<ScenarioPresetNode>(`/scenario-presets/admin/nodes/${id}/move`, {
      method: "POST",
      body: JSON.stringify({ parent_id }),
    }),
  reorderNode: (id: string, sort_order: number) =>
    request<ScenarioPresetNode>(`/scenario-presets/admin/nodes/${id}/reorder`, {
      method: "POST",
      body: JSON.stringify({ sort_order }),
    }),
  deleteNode: (id: string) =>
    request<void>(`/scenario-presets/admin/nodes/${id}`, { method: "DELETE" }),
  getBindings: (scenarioId: string) =>
    request<{ bindings: ScenarioPresetBinding[] }>(
      `/scenario-presets/admin/scenarios/${scenarioId}/bindings`,
    ),
  replaceBindings: (scenarioId: string, bindings: ScenarioPresetBinding[]) =>
    request<void>(`/scenario-presets/admin/scenarios/${scenarioId}/bindings`, {
      method: "PUT",
      body: JSON.stringify({ bindings }),
    }),
};
