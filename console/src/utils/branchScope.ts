/**
 * 统一计算当前用户可用的分行筛选范围。
 */
import { BBK_ID_MAP, getBbkDisplayName } from "../constants/bbk";

/** 总行机构 ID，与 BBK 常量表保持一致。 */
export const HEAD_OFFICE_BBK_ID = "100";

export interface ScopedBranchFilter {
  /** 当前用户是否按总行权限使用分行筛选。 */
  isHeadOffice: boolean;
  /** 非总行用户锁定的分行 ID；总行或未知上下文不锁定。 */
  lockedBbkId?: string;
}

/**
 * 根据当前登录人的 BBK 计算分行下拉框能力。
 *
 * @param currentBbkId - 当前登录人的 BBK ID
 * @returns 分行筛选权限和锁定值
 */
export function getScopedBranchFilter(
  currentBbkId: string | null | undefined,
): ScopedBranchFilter {
  const normalizedBbkId = currentBbkId?.trim();
  if (!normalizedBbkId || normalizedBbkId === HEAD_OFFICE_BBK_ID) {
    return {
      isHeadOffice: true,
      lockedBbkId: undefined,
    };
  }

  return {
    isHeadOffice: false,
    lockedBbkId: normalizedBbkId,
  };
}

/**
 * 确保下拉选项包含当前锁定的分行，避免接口未返回时无法显示已选值。
 *
 * @param lockedBbkId - 当前锁定的分行 ID
 * @param options - 原始下拉选项
 * @returns 补齐后的下拉选项
 */
export function ensureBranchOptions(
  lockedBbkId: string | undefined,
  options = BBK_ID_MAP,
): Array<{ label: string; value: string }> {
  if (!lockedBbkId || options.some((item) => item.value === lockedBbkId)) {
    return options;
  }

  return [
    ...options,
    {
      label: getBbkDisplayName(lockedBbkId),
      value: lockedBbkId,
    },
  ];
}
