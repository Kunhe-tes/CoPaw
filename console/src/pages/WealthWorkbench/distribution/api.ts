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
      body: body instanceof FormData ? body : JSON.stringify(body),
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

const EXCEL_IMPORT_PATH = "/agent/workspace/claw-customer-list/parse";
export const MAX_EXCEL_FILE_MB = 5;
const EXCEL_RESPONSE_ERROR = "人员名单响应格式异常，请重试";

interface ExcelImportUser {
  sapId: string;
  sapName: string | null;
  frsBbkOrgId: string | null;
  frsBbkOrgNm: string | null;
  bbkOrgId: string | null;
  bbkOrgNm: string | null;
  cprhBrnOrgId: string | null;
  cprhBrnOrgNm: string | null;
  brnOrgId: string | null;
  brnOrgNm: string | null;
  queryStatus: number;
}

interface ExcelImportResponse {
  successList: ExcelImportUser[];
  successCount: number;
  failedCount: number;
  failedRows: number[];
}

function importText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function mapExcelUser(user: ExcelImportUser): DistributeTarget {
  const branches = [
    [user.brnOrgId, user.brnOrgNm],
    [user.cprhBrnOrgId, user.cprhBrnOrgNm],
    [user.bbkOrgId, user.bbkOrgNm],
    [user.frsBbkOrgId, user.frsBbkOrgNm],
  ];
  const org = branches.find(([id]) => importText(id));
  const orgId = importText(org?.[0]);
  const orgName = importText(org?.[1]);
  const branchName = importText(user.frsBbkOrgNm);
  return {
    sapId: importText(user.sapId),
    name: importText(user.sapName),
    orgName: orgName || orgId,
    ...(branchName ? { branchName } : {}),
    bbkId: importText(user.frsBbkOrgId),
    bbkOrgId: orgId,
  };
}

function importFailedRows(result: ExcelImportResponse): string[] {
  if (!result.failedCount && !result.failedRows.length) return [];
  if (result.failedRows.length) {
    const rows = [...new Set(result.failedRows)].join("、");
    return [
      `Excel 第 ${rows} 行的客户经理ID或姓名为空或有误，请核对后重新上传`,
    ];
  }
  return [
    `Excel 有 ${result.failedCount} 行的客户经理ID或姓名为空或有误，请核对后重新上传`,
  ];
}

export async function importExcelPeople(file: File, signal: AbortSignal) {
  if (
    !/\.xlsx$/i.test(file.name) ||
    file.size === 0 ||
    file.size > MAX_EXCEL_FILE_MB * 1024 * 1024
  ) {
    throw new Error(`请选择不超过 ${MAX_EXCEL_FILE_MB} MB 的非空 .xlsx 文件`);
  }
  const body = new FormData();
  body.append("file", file);
  const result = await query<ExcelImportResponse>(
    EXCEL_IMPORT_PATH,
    body,
    signal,
  );
  if (
    !Array.isArray(result?.successList) ||
    !Array.isArray(result.failedRows) ||
    result.failedRows.some((row) => !Number.isSafeInteger(row) || row < 1) ||
    !Number.isSafeInteger(result.successCount) ||
    result.successCount < 0 ||
    !Number.isSafeInteger(result.failedCount) ||
    result.failedCount < 0
  )
    throw new Error(EXCEL_RESPONSE_ERROR);

  const errors = importFailedRows(result);
  let duplicates = 0;
  const targets = new Map<string, DistributeTarget>();
  for (const user of result.successList) {
    const sapId = importText(user?.sapId);
    if (!sapId || (user.queryStatus !== 0 && user.queryStatus !== 1))
      throw new Error(EXCEL_RESPONSE_ERROR);
    const target: DistributeTarget =
      user.queryStatus === 0
        ? {
            sapId,
            name: importText(user.sapName),
            orgName: "",
            bbkId: "",
            bbkOrgId: "",
          }
        : mapExcelUser(user);
    if (!target.name) throw new Error(EXCEL_RESPONSE_ERROR);
    if (user.queryStatus === 1 && (!target.bbkId || !target.bbkOrgId)) {
      errors.push(`客户经理ID ${sapId}：机构信息不完整，请核对后重新上传`);
      continue;
    }
    const previous = targets.get(sapId);
    if (previous) {
      if (
        previous.name !== target.name ||
        previous.bbkId !== target.bbkId ||
        previous.bbkOrgId !== target.bbkOrgId
      )
        throw new Error(`客户经理ID ${sapId} 的人员信息不一致，请重新核对名单`);
      duplicates++;
    } else {
      targets.set(sapId, target);
    }
  }
  if (!targets.size && !errors.length)
    throw new Error("未找到可导入的人员，请核对名单");
  return { people: [...targets.values()], errors, duplicates };
}
