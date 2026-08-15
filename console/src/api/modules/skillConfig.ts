import { request } from "../request";

const SKILL_CONFIG_BASE_PATH = "/monitor/busiconfig/skill-config";

export type SkillConfigSource = Record<string, unknown>;

export interface SkillConfigItem {
  id?: string | number;
  skillId: string;
  name: string;
  sort: number;
  groupId?: string;
  groupName?: string;
  businessCenterEnabled: boolean;
  customerInsightEnabled: boolean;
  outboundCallEnabled: boolean;
  enabled: boolean;
  source: SkillConfigSource;
}

export interface SkillConfigFormValues {
  skillId: string;
  name: string;
  sort: number;
  groupId?: string;
  businessCenterEnabled: boolean;
  customerInsightEnabled: boolean;
  outboundCallEnabled: boolean;
}

function firstDefined(source: SkillConfigSource, keys: string[]): unknown {
  for (const key of keys) {
    if (source[key] !== undefined && source[key] !== null) {
      return source[key];
    }
  }
  return undefined;
}

function readString(source: SkillConfigSource, keys: string[]): string {
  const value = firstDefined(source, keys);
  return typeof value === "string" || typeof value === "number"
    ? String(value)
    : "";
}

function readBoolean(
  source: SkillConfigSource,
  keys: string[],
  fallback = false,
): boolean {
  const value = firstDefined(source, keys);
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value === 1;
  if (typeof value === "string") {
    return ["1", "true", "enabled", "yes"].includes(value.toLowerCase());
  }
  return fallback;
}

function unwrapList(response: unknown): SkillConfigSource[] {
  if (Array.isArray(response)) {
    return response.filter(
      (item): item is SkillConfigSource =>
        typeof item === "object" && item !== null,
    );
  }
  if (!response || typeof response !== "object") return [];

  const source = response as SkillConfigSource;
  for (const key of ["data", "rows", "list", "items", "records"]) {
    const value = source[key];
    if (value !== undefined) {
      const items = unwrapList(value);
      if (items.length || Array.isArray(value)) return items;
    }
  }
  return [];
}

function unwrapDetail(response: unknown): SkillConfigSource {
  if (!response || typeof response !== "object" || Array.isArray(response)) {
    return {};
  }
  const source = response as SkillConfigSource;
  const data = source.data;
  return data && typeof data === "object" && !Array.isArray(data)
    ? unwrapDetail(data)
    : source;
}

export function normalizeSkillConfig(
  source: SkillConfigSource,
): SkillConfigItem {
  const skillId = readString(source, ["skillId", "skill_id", "code"]);
  const name = readString(source, [
    "name",
    "skillName",
    "skill_name",
    "jobName",
    "job_name",
  ]);
  const rawSort = firstDefined(source, ["sort", "sortOrder", "sort_order"]);
  const parsedSort = Number(rawSort);

  return {
    id: firstDefined(source, ["id", "skillConfigId", "skill_config_id"]) as
      | string
      | number
      | undefined,
    skillId,
    name: name || skillId,
    sort: Number.isFinite(parsedSort) ? parsedSort : 0,
    groupId:
      readString(source, ["groupId", "group_id", "parentSkillId"]) || undefined,
    groupName:
      readString(source, ["groupName", "group_name", "parentSkillName"]) ||
      undefined,
    businessCenterEnabled: readBoolean(source, [
      "businessCenterEnabled",
      "business_center_enabled",
      "businessOpportunityEnabled",
    ]),
    customerInsightEnabled: readBoolean(source, [
      "customerInsightEnabled",
      "customer_insight_enabled",
    ]),
    outboundCallEnabled: readBoolean(source, [
      "outboundCallEnabled",
      "outbound_call_enabled",
      "telemarketingEnabled",
    ]),
    enabled: readBoolean(source, ["enabled", "status", "active"], true),
    source,
  };
}

function assignUsingExistingKey(
  target: SkillConfigSource,
  aliases: string[],
  fallbackKey: string,
  value: unknown,
) {
  const existingKey = aliases.find((key) => key in target);
  target[existingKey ?? fallbackKey] = value;
}

export function buildSkillConfigPayload(
  values: SkillConfigFormValues,
  current?: SkillConfigItem,
): SkillConfigSource {
  const payload: SkillConfigSource = { ...(current?.source ?? {}) };
  assignUsingExistingKey(
    payload,
    ["skillId", "skill_id"],
    "skillId",
    values.skillId,
  );
  assignUsingExistingKey(
    payload,
    ["name", "skillName", "skill_name", "jobName", "job_name"],
    "name",
    values.name,
  );
  assignUsingExistingKey(
    payload,
    ["sort", "sortOrder", "sort_order"],
    "sort",
    values.sort,
  );
  assignUsingExistingKey(
    payload,
    ["groupId", "group_id", "parentSkillId"],
    "groupId",
    values.groupId,
  );
  assignUsingExistingKey(
    payload,
    [
      "businessCenterEnabled",
      "business_center_enabled",
      "businessOpportunityEnabled",
    ],
    "businessCenterEnabled",
    values.businessCenterEnabled,
  );
  assignUsingExistingKey(
    payload,
    ["customerInsightEnabled", "customer_insight_enabled"],
    "customerInsightEnabled",
    values.customerInsightEnabled,
  );
  assignUsingExistingKey(
    payload,
    ["outboundCallEnabled", "outbound_call_enabled", "telemarketingEnabled"],
    "outboundCallEnabled",
    values.outboundCallEnabled,
  );
  return payload;
}

export const skillConfigApi = {
  async listSkillConfigs(): Promise<SkillConfigItem[]> {
    const response = await request<unknown>(`${SKILL_CONFIG_BASE_PATH}/list`);
    return unwrapList(response).map(normalizeSkillConfig);
  },

  async getSkillConfigDetail(skillId: string): Promise<SkillConfigItem> {
    const response = await request<unknown>(
      `${SKILL_CONFIG_BASE_PATH}/detail?skillId=${encodeURIComponent(skillId)}`,
    );
    return normalizeSkillConfig(unwrapDetail(response));
  },

  createSkillConfig(payload: SkillConfigSource) {
    return request<unknown>(`${SKILL_CONFIG_BASE_PATH}/create`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  updateSkillConfig(payload: SkillConfigSource) {
    return request<unknown>(`${SKILL_CONFIG_BASE_PATH}/update`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
