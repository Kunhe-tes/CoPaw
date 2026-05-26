/**
 * 撤回弹窗组件。
 *
 * 支持技能和 MCP 撤回，可从已分发用户列表选择或手动输入用户 ID。
 */
import { useEffect, useMemo, useState } from "react";
import { Modal, message, Checkbox, Spin, Collapse, Input, Alert } from "antd";
import { UserOutlined, WarningOutlined } from "@ant-design/icons";
import { marketApi } from "../../../api/modules/market";
import { marketMcpApi } from "../../../api/modules/marketMcp";
import { fetchTenantsBySource, TenantSourceInfo } from "../../../api/modules/userInfo";
import { BBK_ID_TO_NAME_MAP } from "../../../constants/bbk";
import { useIframeStore } from "../../../stores/iframeStore";
import { DEFAULT_SOURCE_ID } from "../../../constants/identity";
import type { DistributionRecord, RecallResponse } from "../../../api/types";

export type RecallTargetType = "skill" | "mcp";

interface RecallModalProps {
  open: boolean;
  type: RecallTargetType;
  itemId: string;
  itemName: string;
  sourceId: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function RecallModal({
  open,
  type,
  itemId,
  itemName,
  sourceId,
  onClose,
  onSuccess,
}: RecallModalProps) {
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [distributions, setDistributions] = useState<DistributionRecord[]>([]);
  const [tenantOptions, setTenantOptions] = useState<TenantSourceInfo[]>([]);
  const [selectedUserIds, setSelectedUserIds] = useState<Set<string>>(new Set());
  const [manualUserIdsText, setManualUserIdsText] = useState("");

  const resolvedSourceId = useIframeStore((state) => state.source) || DEFAULT_SOURCE_ID || sourceId;

  // 加载分发记录和用户列表
  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setSelectedUserIds(new Set());
    setManualUserIdsText("");

    Promise.all([
      type === "skill"
        ? marketApi.getSkillDistributions(resolvedSourceId, itemId)
        : marketMcpApi.getMCPDistributions(resolvedSourceId, itemId),
      fetchTenantsBySource(resolvedSourceId),
    ])
      .then(([distList, tenantList]) => {
        setDistributions(distList);
        setTenantOptions(tenantList);
      })
      .catch((err) => {
        console.error("获取分发记录失败:", err);
        message.error("获取分发记录失败");
      })
      .finally(() => setLoading(false));
  }, [open, type, itemId, resolvedSourceId]);

  // 手动输入的用户 ID 中，存在于用户列表的部分
  const manualUserIdsInList = useMemo(() => {
    const inputIds = manualUserIdsText
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    return inputIds.filter((id) =>
      tenantOptions.some((t) => t.tenant_id === id),
    );
  }, [manualUserIdsText, tenantOptions]);

  // 手动输入的用户 ID 中，不存在于用户列表的部分（额外的用户）
  const manualUserIds = useMemo(() => {
    const inputIds = manualUserIdsText
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    return Array.from(
      new Set(
        inputIds.filter((id) => !tenantOptions.some((t) => t.tenant_id === id)),
      ),
    );
  }, [manualUserIdsText, tenantOptions]);

  // 合并选择 + 手动输入
  const finalUserIds = useMemo(() => {
    return Array.from(
      new Set([...selectedUserIds, ...manualUserIdsInList, ...manualUserIds]),
    );
  }, [selectedUserIds, manualUserIdsInList, manualUserIds]);

  // 用户去重（同一用户只保留最新记录）
  const uniqueDistributions = useMemo(() => {
    const userMap = new Map<string, DistributionRecord>();
    for (const dist of distributions) {
      const existing = userMap.get(dist.target_user_id);
      if (!existing || (dist.distributed_at && (!existing.distributed_at || dist.distributed_at > existing.distributed_at))) {
        userMap.set(dist.target_user_id, dist);
      }
    }
    return Array.from(userMap.values());
  }, [distributions]);

  // 按机构分组分发记录
  const groupedDistributions = useMemo(() => {
    const groups: Record<string, DistributionRecord[]> = {};
    for (const dist of uniqueDistributions) {
      const bbkId = dist.target_bbk_id || "unknown";
      if (!groups[bbkId]) {
        groups[bbkId] = [];
      }
      groups[bbkId].push(dist);
    }
    return Object.entries(groups).map(([bbkId, records]) => ({
      bbkId,
      bbkName: bbkId === "unknown" ? "未分配机构" : BBK_ID_TO_NAME_MAP[bbkId] || bbkId,
      records,
    }));
  }, [uniqueDistributions]);

  // 全选/清空
  const handleSelectAll = () => {
    setSelectedUserIds(new Set(uniqueDistributions.map((d) => d.target_user_id)));
  };
  const handleClearAll = () => {
    setSelectedUserIds(new Set());
  };

  // 提交撤回
  const handleSubmit = async () => {
    if (finalUserIds.length === 0) return;
    setSubmitting(true);
    try {
      let result: RecallResponse;
      if (type === "skill") {
        result = await marketApi.recallSkill(resolvedSourceId, itemId, finalUserIds);
      } else {
        result = await marketMcpApi.recallMCP(resolvedSourceId, itemId, finalUserIds);
      }

      const recalledCount = result.recalled_count ?? 0;
      const failedCount = result.failed_count ?? 0;
      const results = result.results ?? [];

      if (recalledCount === 0 && failedCount === 0) {
        message.warning("撤回未生效，无用户被处理");
      } else if (failedCount > 0) {
        const failureLines = results
          .filter((r) => !r.success)
          .map((r) => `• ${r.user_id}（${r.reason || "未知原因"}）`);
        Modal.confirm({
          title: recalledCount > 0 ? "部分撤回成功" : "撤回未生效",
          content: (
            <div style={{ display: "grid", gap: 8 }}>
              {recalledCount > 0 && (
                <div>成功撤回 {recalledCount} 个用户</div>
              )}
              <div style={{ display: "grid", gap: 4 }}>
                <div>以下 {failedCount} 个用户撤回失败：</div>
                <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                  {failureLines.join("\n")}
                </pre>
              </div>
            </div>
          ),
          okText: "关闭",
          cancelButtonProps: { style: { display: "none" } },
        });
      } else {
        message.success(`撤回成功，共 ${recalledCount} 个用户`);
      }
      onSuccess();
      onClose();
    } catch (error) {
      console.error("撤回失败:", error);
      message.error(error instanceof Error ? error.message : "撤回失败");
    } finally {
      setSubmitting(false);
    }
  };

  const typeLabel = type === "skill" ? "技能" : "MCP";
  const hintText = type === "skill"
    ? "从已分发用户的工作空间中撤回该技能，用户将无法继续使用。"
    : "从已分发租户的 default agent 中移除该 MCP 配置，租户将无法继续使用。";

  return (
    <Modal
      open={open}
      title={`撤回「${itemName}」`}
      onCancel={submitting ? undefined : onClose}
      onOk={handleSubmit}
      okText="确认撤回"
      cancelText="取消"
      okButtonProps={{
        disabled: finalUserIds.length === 0,
        loading: submitting,
        danger: true,
      }}
      width={600}
    >
      <div style={{ display: "grid", gap: 12 }}>
        <Alert
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          message={hintText}
        />

        <div style={{ fontWeight: 500 }}>
          当前条目：{itemName}（已分发 {uniqueDistributions.length} 个用户）
        </div>

        {loading ? (
          <Spin size="small" style={{ marginLeft: 16 }} />
        ) : (
          <>
            {/* 已分发用户列表 */}
            {uniqueDistributions.length === 0 ? (
              <div style={{ color: "#666", fontSize: 12, marginBottom: 12 }}>
                该{typeLabel}暂无分发记录，可手动输入用户 ID 进行撤回
              </div>
            ) : (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ fontWeight: 500 }}>已分发用户</div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <Checkbox
                      checked={selectedUserIds.size === uniqueDistributions.length && uniqueDistributions.length > 0}
                      indeterminate={selectedUserIds.size > 0 && selectedUserIds.size < uniqueDistributions.length}
                      onChange={(e) => {
                        if (e.target.checked) {
                          handleSelectAll();
                        } else {
                          handleClearAll();
                        }
                      }}
                    >
                      全选
                    </Checkbox>
                    <a onClick={handleClearAll} style={{ fontSize: 12 }}>
                      清空
                    </a>
                  </div>
                </div>

                {/* 按机构分组展示 */}
                <Collapse
                  size="small"
                  style={{ maxHeight: 240, overflow: "auto" }}
                  items={groupedDistributions.map((group) => ({
                    key: group.bbkId,
                    label: (
                      <span style={{ fontSize: 13 }}>
                        <UserOutlined style={{ marginRight: 6, color: "#1677ff" }} />
                        {group.bbkName}
                        <span style={{ color: "#999", marginLeft: 8 }}>
                          {group.records.length} 人
                        </span>
                      </span>
                    ),
                    children: (
                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
                          gap: 4,
                        }}
                      >
                        {group.records.map((dist) => {
                          const tenant = tenantOptions.find((t) => t.tenant_id === dist.target_user_id);
                          const displayName = tenant?.tenant_name
                            ? `${tenant.tenant_name} (${dist.target_user_id})`
                            : dist.target_user_id;
                          // 选中状态：手动输入匹配（即时）或点击选中（持久）
                          const isManualMatch = manualUserIdsInList.includes(dist.target_user_id);
                          const isClickSelected = selectedUserIds.has(dist.target_user_id);
                          const selected = isManualMatch || isClickSelected;
                          return (
                            <div
                              key={dist.target_user_id}
                              onClick={() => {
                                const next = new Set(selectedUserIds);
                                if (selected) {
                                  // 取消选中：从 selectedUserIds 移除
                                  next.delete(dist.target_user_id);
                                } else {
                                  // 选中：持久化到 selectedUserIds
                                  next.add(dist.target_user_id);
                                }
                                setSelectedUserIds(next);
                              }}
                              style={{
                                fontSize: 12,
                                color: "#333",
                                padding: "4px 8px",
                                borderRadius: 4,
                                cursor: "pointer",
                                backgroundColor: selected ? "#e6f4ff" : "transparent",
                                border: selected ? "1px solid #1890ff" : "1px solid transparent",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                              title={displayName}
                            >
                              {displayName}
                            </div>
                          );
                        })}
                      </div>
                    ),
                  }))}
                />
              </>
            )}

            {/* 手动输入用户 ID */}
            <div>
              <div style={{ fontWeight: 500 }}>手动输入用户</div>
              <div style={{ marginTop: 8, marginBottom: 8, color: "#666", fontSize: 12 }}>
                输入要撤回的用户ID，多个用户用空格或逗号分隔
              </div>
              <Input.TextArea
                rows={3}
                value={manualUserIdsText}
                onChange={(e) => setManualUserIdsText(e.target.value)}
                placeholder="例如：user001 user002 user003"
              />
            </div>

            {/* 选择汇总 */}
            <div style={{ color: "#666", fontSize: 12 }}>
              已选择 {finalUserIds.length} 个用户
              {uniqueDistributions.length > 0 && (
                <span>（{selectedUserIds.size} 个已分发用户 + {manualUserIdsInList.length + manualUserIds.length} 个手动输入）</span>
              )}
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}