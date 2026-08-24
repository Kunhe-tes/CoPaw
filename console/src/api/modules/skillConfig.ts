import { request } from "../request";

const SKILL_CONFIG_BASE_PATH = "/monitor/busiconfig/skill-config";
const ACTIVITY_CLASS_LIST_PATH = "/monitor/busiconfig/actv-cls/list";

export type SkillConfigSource = Record<string, unknown>;

export interface SkillConfigItem {
  id?: string | number;
  skillId: string;
  bbkId?: string;
  name: string;
  bbkName?: string;
  sort: number;
  groupId?: string;
  groupName?: string;
  businessCenterEnabled: boolean;
  customerInsightEnabled: boolean;
  outboundCallEnabled: boolean;
  enabled: boolean;
  createdAt?: string;
  updatedAt?: string;
  source: SkillConfigSource;
}

interface SkillConfigResponse<T> {
  code: number;
  message: string;
  data: T;
}

type SkillConfigListResponse = SkillConfigResponse<SkillConfigSource[]>;
type SkillConfigDetailResponse = SkillConfigResponse<SkillConfigSource>;
type SkillConfigCreateResponse = SkillConfigResponse<SkillConfigSource>;
type SkillConfigUpdateResponse = SkillConfigResponse<SkillConfigSource>;

interface SkillPreviewStatsResponseData {
  uv: number;
  pv: number;
}

type SkillPreviewStatsResponse =
  SkillConfigResponse<SkillPreviewStatsResponseData>;

export interface SkillPreviewStats {
  uv: number;
  pv: number;
}

interface SkillValueReturnStatsResponseData {
  contact_count: number;
  list_count: number;
  contact_rate: number;
  accept_count: number;
  accept_rate: number;
  aum_increase: number;
  wealth_product_amount: number;
}

type SkillValueReturnStatsResponse =
  SkillConfigResponse<SkillValueReturnStatsResponseData>;

export interface SkillValueReturnStats {
  contactCount: number;
  listCount: number;
  contactRate: number;
  acceptCount: number;
  acceptRate: number;
  aumIncrease: number;
  wealthProductAmount: number;
}

interface SkillExposureStatsResponseData {
  total_count: number;
  items: Array<{
    seq: number;
    event_target_id: string;
    event_target_name: string;
    exposure_count: number;
    exposure_rate: string;
  }>;
}

type SkillExposureStatsResponse =
  SkillConfigResponse<SkillExposureStatsResponseData>;

export interface SkillExposureStatsItem {
  sequence: number;
  targetId: string;
  targetName: string;
  exposureCount: number;
  exposureRate: string;
}

export interface SkillExposureStats {
  totalCount: number;
  items: SkillExposureStatsItem[];
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

export interface SkillConfigUpdatePayload {
  skill_id: string;
  bbk_id: string;
  skill_name?: string;
  bbk_name?: string;
  sort_order?: number;
  customer_insight_enabled?: number;
  tele_visit_enabled?: number;
  opportunity_center_enabled?: number;
  actv_cls_cd?: string;
  actv_cls_nm?: string;
}

export interface SkillConfigCreatePayload extends SkillConfigUpdatePayload {
  skill_name: string;
  bbk_name: string;
}

export interface ActivityClassItem {
  bbkOrgId: string;
  activityClassId: string;
  activityClassName: string;
  description: string;
  displayOrder: string;
}

interface ActivityClassListResponse {
  code: number;
  message: string;
  data: {
    code: string;
    errMsg: string | null;
    totalRows: string;
    data: Array<{
      bbkOrgId: string;
      actvClsCd: string;
      actvClsNm: string;
      actvClsCmt: string;
      disSeqNbr: string;
    }>;
  };
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
    bbkId: readString(source, ["bbk_id", "bbkId"]) || undefined,
    name: name || skillId,
    bbkName: readString(source, ["bbk_name", "bbkName"]) || undefined,
    sort: Number.isFinite(parsedSort) ? parsedSort : 0,
    groupId:
      readString(source, [
        "actv_cls_cd",
        "groupId",
        "group_id",
        "parentSkillId",
      ]) || undefined,
    groupName:
      readString(source, [
        "actv_cls_nm",
        "groupName",
        "group_name",
        "parentSkillName",
      ]) || undefined,
    businessCenterEnabled: readBoolean(source, [
      "opportunity_center_enabled",
      "businessCenterEnabled",
      "business_center_enabled",
      "businessOpportunityEnabled",
    ]),
    customerInsightEnabled: readBoolean(source, [
      "customerInsightEnabled",
      "customer_insight_enabled",
    ]),
    outboundCallEnabled: readBoolean(source, [
      "tele_visit_enabled",
      "outboundCallEnabled",
      "outbound_call_enabled",
      "telemarketingEnabled",
    ]),
    enabled: readBoolean(source, ["enabled", "status", "active"], true),
    createdAt: readString(source, ["created_at", "createdAt"]) || undefined,
    updatedAt: readString(source, ["updated_at", "updatedAt"]) || undefined,
    source,
  };
}

export function buildSkillConfigCreatePayload(
  values: SkillConfigFormValues,
  bbkId: string,
  bbkName: string,
  groupName?: string,
): SkillConfigCreatePayload {
  if (!values.skillId || values.skillId.length > 100) {
    throw new Error("技能ID不能为空且不能超过100个字符");
  }
  if (!bbkId) {
    throw new Error("无法获取所属分行ID，请刷新页面后重试");
  }
  if (!values.name) {
    throw new Error("技能名称不能为空");
  }
  if (!bbkName || bbkName === "-") {
    throw new Error("无法获取所属分行名称，请刷新页面后重试");
  }
  if (values.groupId && values.groupId.length > 100) {
    throw new Error("商机中心分组ID不能超过100个字符");
  }

  return {
    skill_id: values.skillId,
    bbk_id: bbkId,
    skill_name: values.name,
    bbk_name: bbkName,
    sort_order: values.sort,
    customer_insight_enabled: values.customerInsightEnabled ? 1 : 0,
    tele_visit_enabled: values.outboundCallEnabled ? 1 : 0,
    opportunity_center_enabled: values.businessCenterEnabled ? 1 : 0,
    actv_cls_cd: values.groupId,
    actv_cls_nm: values.groupId ? groupName : undefined,
  };
}

export function buildSkillConfigUpdatePayload(
  values: SkillConfigFormValues,
  current: SkillConfigItem | undefined,
  bbkId: string,
  groupName?: string,
): SkillConfigUpdatePayload {
  return {
    skill_id: values.skillId,
    bbk_id: current?.bbkId || bbkId,
    skill_name: values.name || undefined,
    bbk_name: current?.bbkName,
    sort_order: values.sort,
    customer_insight_enabled: values.customerInsightEnabled ? 1 : 0,
    tele_visit_enabled: values.outboundCallEnabled ? 1 : 0,
    opportunity_center_enabled: values.businessCenterEnabled ? 1 : 0,
    actv_cls_cd: values.groupId,
    actv_cls_nm: values.groupId ? groupName : undefined,
  };
}

export const skillConfigApi = {
  async listActivityClasses(bbkId: string): Promise<ActivityClassItem[]> {
    const response = await request<ActivityClassListResponse>(
      ACTIVITY_CLASS_LIST_PATH,
      {
        method: "POST",
        body: JSON.stringify({
          bbkOrgId: bbkId,
          pageNum: 999,
          startRow: 0,
        }),
      },
    );
    if (response.code !== 0) {
      throw new Error(response.message || "所属分组列表加载失败");
    }
    if (response.data.code !== "success") {
      throw new Error(response.data.errMsg || "所属分组列表加载失败");
    }
    return response.data.data.map((item) => ({
      bbkOrgId: item.bbkOrgId,
      activityClassId: item.actvClsCd,
      activityClassName: item.actvClsNm,
      description: item.actvClsCmt,
      displayOrder: item.disSeqNbr,
    }));
  },

  async listSkillConfigs(bbkId: string): Promise<SkillConfigItem[]> {
    const response = await request<SkillConfigListResponse>(
      `${SKILL_CONFIG_BASE_PATH}/list`,
      {
        method: "POST",
        body: JSON.stringify({ bbk_id: bbkId }),
      },
    );
    if (response.code !== 0) {
      throw new Error(response.message || "Skill 配置列表加载失败");
    }
    return response.data.map(normalizeSkillConfig);
  },

  async getSkillConfigDetail(
    skillId: string,
    bbkId: string,
  ): Promise<SkillConfigItem> {
    const response = await request<SkillConfigDetailResponse>(
      `${SKILL_CONFIG_BASE_PATH}/detail`,
      {
        method: "POST",
        body: JSON.stringify({ skill_id: skillId, bbk_id: bbkId }),
      },
    );
    if (response.code !== 0) {
      throw new Error(response.message || "Skill 配置详情加载失败");
    }
    return normalizeSkillConfig(response.data);
  },

  async getPreviewStats(
    skillId: string,
    bbkId: string,
  ): Promise<SkillPreviewStats> {
    const response = await request<SkillPreviewStatsResponse>(
      `${SKILL_CONFIG_BASE_PATH}/preview-stats`,
      {
        method: "POST",
        body: JSON.stringify({ skill_id: skillId, bbk_id: bbkId }),
      },
    );
    if (response.code !== 0) {
      throw new Error(response.message || "查看数据加载失败");
    }
    return { uv: response.data.uv, pv: response.data.pv };
  },

  async getValueReturnStats(
    skillId: string,
    bbkId: string,
  ): Promise<SkillValueReturnStats> {
    const response = await request<SkillValueReturnStatsResponse>(
      `${SKILL_CONFIG_BASE_PATH}/value-return-stats`,
      {
        method: "POST",
        body: JSON.stringify({ skill_id: skillId, bbk_id: bbkId }),
      },
    );
    if (response.code !== 0) {
      throw new Error(response.message || "回检数据加载失败");
    }
    return {
      contactCount: response.data.contact_count,
      listCount: response.data.list_count,
      contactRate: response.data.contact_rate,
      acceptCount: response.data.accept_count,
      acceptRate: response.data.accept_rate,
      aumIncrease: response.data.aum_increase,
      wealthProductAmount: response.data.wealth_product_amount,
    };
  },

  async getSkillExposureStats(
    skillId: string,
    bbkId: string,
  ): Promise<SkillExposureStats> {
    const response = await request<SkillExposureStatsResponse>(
      `${SKILL_CONFIG_BASE_PATH}/skill-exposure-stats`,
      {
        method: "POST",
        body: JSON.stringify({ skill_id: skillId, bbk_id: bbkId }),
      },
    );
    if (response.code !== 0) {
      throw new Error(response.message || "客户级方案模块曝光统计加载失败");
    }
    return {
      totalCount: response.data.total_count,
      items: response.data.items.map((item) => ({
        sequence: item.seq,
        targetId: item.event_target_id,
        targetName: item.event_target_name,
        exposureCount: item.exposure_count,
        exposureRate: item.exposure_rate,
      })),
    };
  },

  async createSkillConfig(
    payload: SkillConfigCreatePayload,
  ): Promise<SkillConfigItem> {
    const response = await request<SkillConfigCreateResponse>(
      `${SKILL_CONFIG_BASE_PATH}/create`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
    if (response.code !== 0) {
      throw new Error(response.message || "Skill 配置创建失败");
    }
    return normalizeSkillConfig(response.data);
  },

  async updateSkillConfig(
    payload: SkillConfigUpdatePayload,
  ): Promise<SkillConfigItem> {
    const response = await request<SkillConfigUpdateResponse>(
      `${SKILL_CONFIG_BASE_PATH}/update`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
    if (response.code !== 0) {
      throw new Error(response.message || "Skill 配置更新失败");
    }
    return normalizeSkillConfig(response.data);
  },
};
