import type { ReactNode } from "react";
import type { TenantSourceInfo } from "@/api/modules/userInfo";

export interface TenantSelectorProps {
  /** 已选中的租户 ID 列表 */
  selectedTenantIds: string[];

  /** 选择变更回调 */
  onChange: (tenantIds: string[]) => void;

  /** 选中租户详情变更回调 */
  onSelectionInfoChange?: (tenants: TenantSourceInfo[]) => void;

  /** 提示文本 */
  hint?: ReactNode;

  /** 当前租户 ID（用于过滤自身） */
  excludeTenantId?: string;

  /** 加载失败回调 */
  onLoadError?: (error: Error) => void;
}
