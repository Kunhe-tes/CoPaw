/**
 * 通用分发目标弹窗。
 *
 * 支持技能和 MCP 分发，统一交互和布局。
 */
import { useEffect, useState } from "react";
import { Modal, message } from "antd";
import { marketApi, DistributeRequest } from "../../api/modules/market";
import { marketMcpApi } from "../../api/modules/marketMcp";
import { TenantSelector } from "../../components/TenantSelector";
import type { MarketSkill } from "../../api/modules/market";
import type { MarketMCPItem } from "../../api/types";

export type DistributeTargetType = "skill" | "mcp";

interface DistributeTargetModalProps {
  open: boolean;
  type: DistributeTargetType;
  item: MarketSkill | MarketMCPItem | null;
  sourceId: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function DistributeTargetModal({
  open,
  type,
  item,
  sourceId,
  onClose,
  onSuccess,
}: DistributeTargetModalProps) {
  const [submitting, setSubmitting] = useState(false);
  const [selectedTenantIds, setSelectedTenantIds] = useState<string[]>([]);

  // 打开时清空选择
  useEffect(() => {
    if (!open) return;
    setSelectedTenantIds([]);
  }, [open]);

  // 提交分发
  const handleSubmit = async () => {
    if (!item || selectedTenantIds.length === 0) return;
    setSubmitting(true);
    try {
      if (type === "skill") {
        const payload: DistributeRequest = {
          target_type: "user_id",
          target_values: selectedTenantIds,
        };
        const result = await marketApi.distributeSkill(
          sourceId,
          (item as MarketSkill).item_id,
          payload,
        );
        const distributedCount = result.distributed_count ?? 0;
        const conflictCount = result.conflict_count ?? 0;
        const conflicts = result.conflicts ?? [];

        if (distributedCount === 0 && conflictCount === 0) {
          message.warning("分发未生效，无用户实际收到该技能");
        } else if (conflictCount > 0) {
          const conflictLines = conflicts.map(
            (c) =>
              `• ${c.user_id}（${
                c.reason === "customized" ? "已有自建技能" : c.reason
              }）`,
          );
          Modal.confirm({
            title: distributedCount > 0 ? "部分分发成功" : "分发未生效",
            content: (
              <div style={{ display: "grid", gap: 8 }}>
                {distributedCount > 0 && (
                  <div>成功分发/更新 {distributedCount} 个用户</div>
                )}
                <div style={{ display: "grid", gap: 4 }}>
                  <div>以下 {conflictCount} 个用户跳过（已有自建技能）：</div>
                  <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                    {conflictLines.join("\n")}
                  </pre>
                </div>
              </div>
            ),
            okText: "关闭",
            cancelButtonProps: { style: { display: "none" } },
          });
        } else {
          message.success(`分发成功，共 ${distributedCount} 个用户`);
        }
      } else {
        const result = await marketMcpApi.distributeMCP(
          (item as MarketMCPItem).item_id,
          {
            target_tenant_ids: selectedTenantIds,
            overwrite: true,
          },
        );

        const items = Array.isArray(result.results) ? result.results : [];
        const succeeded = items.filter((r) => r.success);
        const failed = items.filter((r) => !r.success);

        if (failed.length > 0) {
          const successLines = succeeded.map((r) => {
            const suffix = r.bootstrapped ? " (已初始化)" : "";
            return `• ${r.tenant_id}${suffix}`;
          });
          const failureLines = failed.map(
            (r) => `• ${r.tenant_id}: ${r.error || "分发失败"}`,
          );
          Modal.confirm({
            title: succeeded.length > 0 ? "部分租户分发失败" : "分发失败",
            content: (
              <div style={{ display: "grid", gap: 8 }}>
                {succeeded.length > 0 ? (
                  <div style={{ display: "grid", gap: 4 }}>
                    <div>以下租户分发成功：</div>
                    <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                      {successLines.join("\n")}
                    </pre>
                  </div>
                ) : null}
                <div style={{ display: "grid", gap: 4 }}>
                  <div>以下租户分发失败：</div>
                  <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                    {failureLines.join("\n")}
                  </pre>
                </div>
              </div>
            ),
            okText: "关闭",
            cancelButtonProps: { style: { display: "none" } },
          });
        } else if (succeeded.length > 0) {
          message.success(`分发成功，共 ${succeeded.length} 个租户`);
        }
      }
      onSuccess();
      onClose();
    } catch (error) {
      console.error("分发失败:", error);
      message.error(error instanceof Error ? error.message : "分发失败");
    } finally {
      setSubmitting(false);
    }
  };

  const typeLabel = type === "skill" ? "技能" : "MCP";
  const hintText =
    type === "skill"
      ? "将当前技能分发到目标用户的工作空间中，用户可在「我的技能」中查看。"
      : "将当前市场 MCP 分发到目标租户的 default agent 中，如已存在同名 MCP 将覆盖。";

  return (
    <Modal
      open={open}
      title={`分发「${item?.name || ""}」`}
      onCancel={submitting ? undefined : onClose}
      onOk={handleSubmit}
      okText="分发"
      cancelText="取消"
      okButtonProps={{
        disabled: selectedTenantIds.length === 0,
        loading: submitting,
      }}
      width={600}
    >
      <div style={{ display: "grid", gap: 12 }}>
        <div style={{ color: "#666", fontSize: 12 }}>{hintText}</div>
        <div style={{ fontWeight: 500 }}>
          当前条目：{item?.name || "-"}（共选择 {selectedTenantIds.length}{" "}
          个用户）
        </div>
        <TenantSelector
          selectedTenantIds={selectedTenantIds}
          onChange={setSelectedTenantIds}
        />
      </div>
    </Modal>
  );
}
