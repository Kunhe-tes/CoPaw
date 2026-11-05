import { request } from "@/api/request";
import { getWorkbenchContext } from "../../operations";
import { getUserId } from "@/utils/identity";
import { DEFAULT_BBK_ID } from "@/constants/identity";
import type { Customer } from "../../types";

export const INTENTION_LABELS = {
  0: "待了解",
  1: "低意向",
  2: "中意向",
  3: "高意向",
} as const;
export type Intention = keyof typeof INTENTION_LABELS;
export type EditKind = "insurancePlan" | "contactPlan" | "followUp";

export interface ContactEntry {
  date: string;
  method: FollowUpMethod;
  content: string;
}

export const FOLLOW_UP_RESULTS = {
  0: "待跟进",
  1: "已完成",
} as const;
export const FOLLOW_UP_METHODS = {
  0: "企微",
  1: "招乎",
  2: "电访",
  3: "面访",
} as const;
export type FollowUpMethod = keyof typeof FOLLOW_UP_METHODS;
export type FollowUpResult = keyof typeof FOLLOW_UP_RESULTS;
export interface FollowUpEntry extends ContactEntry {
  result: FollowUpResult;
}
export type ContactRecord = ContactEntry & { id: string };
export type FollowUpRecord = FollowUpEntry & { id: string };

/** 页面视图模型；外部字段名、枚举与分页方式待接口文档确认后在此适配。 */
export interface InsuranceCustomer {
  id: string;
  custUid: string;
  name: string;
  branchName?: string;
  sceneName?: string;
  bbkOrgId?: string;
  /** 经营方案完整地址，对齐原名单的 filename 字段。 */
  link?: string;
  assets?: string;
  assetsDescription?: string;
  insurancePlan?: string;
  contactPlans?: ContactRecord[];
  followUps?: FollowUpRecord[];
  intention: Intention;
}

export interface InsuranceList {
  customers: InsuranceCustomer[];
  counts: { customers: number; highIntention: number; tracking: number };
}

export interface JoinTrackingValues {
  insurancePlan: string;
  contactPlans: ContactEntry[];
  intention: Intention;
}

export type InsuranceChange =
  | { kind: "insurancePlan"; value: string }
  | {
      kind: "contactPlan";
      value: ContactEntry;
      recordId?: string;
      requestId: string;
    }
  | {
      kind: "followUp";
      value: FollowUpEntry;
      recordId?: string;
      requestId: string;
    }
  | { kind: "intention"; value: Intention };

export type InsuranceEditorChange = Exclude<
  InsuranceChange,
  { kind: "intention" }
>;

export class InsuranceApiUnavailableError extends Error {
  constructor() {
    super("保险核心跟踪服务暂未接入");
  }
}

const API_PREFIX = "/agent/workspace";

// 全部跟踪接口共用上述服务前缀；此处仅配置前缀后的路径，并在本模块转换实际 DTO。
// 正式文档待补充；join/remove 使用临时约定，其余路径待确认，不回退为本地保存。
const ENDPOINTS: Record<
  "list" | "join" | "remove" | InsuranceChange["kind"],
  string | null
> = {
  list: null,
  insurancePlan: null,
  contactPlan: null,
  followUp: null,
  intention: null,
  // 临时约定，待正式接口文档替换；复用今日任务网关和公共请求上下文。
  join: "/insurance-tracking/add",
  remove: "/insurance-tracking/remove",
};

async function insuranceRequest<T>(
  operation: keyof typeof ENDPOINTS,
  payload: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<T> {
  const path = ENDPOINTS[operation];
  if (!path) throw new InsuranceApiUnavailableError();
  const context = getWorkbenchContext();
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  signal?.addEventListener("abort", abort, { once: true });
  const timeout = setTimeout(abort, 60000);
  try {
    const response = await request<{
      code: string | number;
      message?: string;
      data: T;
    }>(`${API_PREFIX}${path}`, {
      method: "POST",
      signal: controller.signal,
      body: JSON.stringify({
        sapId: getUserId(),
        bbkId: context.bbk || DEFAULT_BBK_ID,
        ...(context.orgCode ? { subBbkId: context.orgCode } : {}),
        ...(context.positionId ? { posId: context.positionId } : {}),
        platformSource: "WP",
        pageSource: "WP_AGENT_WORKSPACE_TASK_LIST",
        ...payload,
      }),
    });
    if (String(response?.code) !== "200") {
      throw new Error(response?.message || "保险跟踪请求失败，请重试");
    }
    return response.data;
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
}

export async function fetchInsuranceTracking(
  signal?: AbortSignal,
): Promise<InsuranceList> {
  const data = await insuranceRequest<{
    customers: (InsuranceCustomer & { filename?: string | null })[];
    counts: InsuranceList["counts"];
  }>("list", {}, signal);
  if (!Array.isArray(data?.customers) || !data.counts) {
    throw new Error("保险跟踪数据格式异常，请联系管理员");
  }
  return {
    ...data,
    customers: data.customers.map(({ filename, ...customer }) => ({
      ...customer,
      link: filename ?? customer.link,
    })),
  };
}

/** 临时请求约定：服务端按客户去重创建跟踪记录，requestId 支持失败重试幂等。 */
export async function joinInsuranceTracking(
  customer: Pick<Customer, "custUid" | "skillId" | "bbkOrgId">,
  values: JoinTrackingValues,
  requestId: string,
  signal?: AbortSignal,
): Promise<void> {
  await insuranceRequest(
    "join",
    {
      custUid: customer.custUid,
      skillId: customer.skillId,
      bbkOrgId: customer.bbkOrgId,
      ...values,
      requestId,
    },
    signal,
  );
}

/** 临时约定：按跟踪记录 ID 移除，成功返回 code=200；重复请求按 requestId 去重。 */
export async function removeInsuranceTracking(
  customer: InsuranceCustomer,
  requestId: string,
  signal?: AbortSignal,
): Promise<void> {
  await insuranceRequest(
    "remove",
    {
      id: customer.id,
      custUid: customer.custUid,
      bbkOrgId: customer.bbkOrgId,
      requestId,
    },
    signal,
  );
}

export async function saveInsuranceChange(
  customer: InsuranceCustomer,
  change: InsuranceChange,
): Promise<ContactRecord | FollowUpRecord | void> {
  const record = await insuranceRequest<ContactRecord | FollowUpRecord>(
    change.kind,
    {
      id: customer.id,
      custUid: customer.custUid,
      bbkOrgId: customer.bbkOrgId,
      value: change.value,
      ...("requestId" in change
        ? {
            recordId: change.recordId,
            requestId: change.requestId,
            operation: change.recordId ? "update" : "create",
          }
        : {}),
    },
  );
  // 新增需回填服务端 ID；重试使用同一 requestId，由服务端保障幂等。
  if (change.kind === "contactPlan" || change.kind === "followUp") {
    if (
      !record?.id ||
      !record.date ||
      typeof record.content !== "string" ||
      typeof record.method !== "number" ||
      !(record.method in FOLLOW_UP_METHODS) ||
      (change.kind === "followUp" &&
        (!("result" in record) ||
          typeof record.result !== "number" ||
          !(record.result in FOLLOW_UP_RESULTS)))
    ) {
      throw new Error("保存响应缺少完整记录，请联系管理员");
    }
    return record;
  }
}

export const EDIT_LABELS: Record<EditKind, string> = {
  insurancePlan: "保险计划",
  contactPlan: "接触计划",
  followUp: "跟进记录",
};
