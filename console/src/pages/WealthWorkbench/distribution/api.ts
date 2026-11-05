import { request } from "../../../api/request";
import { BBK_ID_TO_NAME_MAP } from "../../../constants/bbk";
import { getWorkbenchContext } from "../operations";
import type { DistributeTarget } from "../types";

export interface Institution {
  mOrgCode: string;
  mOrgName: string;
  mOrgLvl: number;
  children: Institution[];
}
export interface DistributionContext {
  bbk: string;
  name: string;
  level: number;
  sysId: string;
}
interface RawInstitution extends Omit<Institution, "children" | "mOrgLvl"> {
  mOrgLvl: number | string;
  children?: RawInstitution[];
}
interface UserPosition {
  sapID: string;
  userName: string;
  branchID?: string | null;
  subBranchID?: string | null;
  branchName?: string | null;
  subBranchName?: string | null;
}
interface Response<T> {
  code: string;
  message?: string;
  data: T;
}

export function distributionContext(): DistributionContext {
  const { bbk, orgLvl, sysId } = getWorkbenchContext();
  const name = bbk ? BBK_ID_TO_NAME_MAP[bbk] : undefined;
  const level = orgLvl?.trim() ? Number(orgLvl) : NaN;
  if (!bbk || !name || !sysId || !Number.isInteger(level) || level < 0) {
    throw new Error("分行名称或登录机构信息不完整，请重新进入系统");
  }
  return { bbk, name, level, sysId };
}

async function query<T>(path: string, body: unknown, signal?: AbortSignal) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  if (signal?.aborted) controller.abort();
  const timeout = setTimeout(abort, 60000);
  try {
    const result = await request<Response<T>>(path, {
      method: "POST",
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (controller.signal.aborted) throw new Error("分发查询已取消或超时");
    if (result.code !== "200")
      throw new Error(result.message || "分发查询失败");
    return result.data;
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abort);
  }
}

function normalize(node: RawInstitution): Institution {
  const level = Number(node.mOrgLvl);
  if (
    !node.mOrgCode ||
    !node.mOrgName ||
    !Number.isInteger(level) ||
    level < 0
  ) {
    throw new Error("机构数据不完整，请重试");
  }
  return {
    mOrgCode: node.mOrgCode,
    mOrgName: node.mOrgName,
    mOrgLvl: level,
    children: (node.children ?? []).map(normalize),
  };
}

export async function queryInstitutionTree(
  context: DistributionContext,
  signal?: AbortSignal,
) {
  const root = await query<RawInstitution>(
    "/zt/wealth/wmadm/bbkTree",
    {
      mmOrgCode: context.bbk,
      mmOrgName: context.name,
      mmOrgLvl: context.level,
      sysId: context.sysId,
    },
    signal,
  );
  if (!root || root.mOrgCode !== context.bbk)
    throw new Error("机构数据与当前分行不一致，请重试");
  return normalize(root);
}

export async function queryInstitutionPeople(
  context: DistributionContext,
  nodes: Institution[],
  signal?: AbortSignal,
): Promise<DistributeTarget[]> {
  const institutions = new Map<string, Institution>();
  const collect = (node: Institution) => {
    if (institutions.has(node.mOrgCode)) return;
    institutions.set(node.mOrgCode, node);
    node.children.forEach(collect);
  };
  nodes.forEach(collect);
  const data = await query<UserPosition[]>(
    "/zt/wealth/wmadm/orgSaps",
    {
      orgList: [...institutions.values()].map((node) => ({
        bbkOrgId: context.bbk,
        mmOrgCode: node.mOrgCode,
        mmOrgLvl: node.mOrgLvl,
      })),
    },
    signal,
  );
  if (!Array.isArray(data)) throw new Error("人员数据格式异常，请重试");
  return data
    .filter((user) => user.sapID)
    .map((user) => ({
      sapId: user.sapID,
      name: user.userName || user.sapID,
      orgName: user.subBranchName || user.branchName || "",
      bbkId: user.branchID ?? context.bbk,
      bbkOrgId: user.subBranchID || user.branchID || "",
    }));
}
