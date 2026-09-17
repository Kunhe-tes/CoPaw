export type ScenarioPresetNodeKind = "domain" | "capability" | "scenario";

export interface ScenarioPresetScenario {
  id: string;
  name: string;
  prompt_draft: string;
}

export interface ScenarioPresetCapability {
  id: string;
  name: string;
  scenarios: ScenarioPresetScenario[];
}

export interface ScenarioPresetDomain {
  id: string;
  name: string;
  capabilities: ScenarioPresetCapability[];
}

export interface EffectiveScenarioPresetCatalog {
  domains: ScenarioPresetDomain[];
}

export interface ScenarioPresetNode {
  id: string;
  source_id: string;
  kind: ScenarioPresetNodeKind;
  parent_id: string | null;
  name: string;
  prompt_draft: string;
  sort_order: number;
  is_active: boolean;
}

export interface ScenarioPresetBinding {
  resource_id: string;
  resource_type: "skill" | "mcp_service";
  display_name: string;
  sort_order: number;
}
