/**
 * 分发预览概览卡片组件
 *
 * 展示分发统计：首次分发、覆盖更新、跳过（冲突）
 */
import { useMemo } from "react";
import { Checkbox, Spin } from "antd";
import { useTranslation } from "react-i18next";
import type { UserSkillStatus } from "@/api/modules/market";
import styles from "./index.module.less";

interface DistributionPreviewProps {
  skillVersion: string;
  users: UserSkillStatus[];
  distributedUserIds: string[];
  selectedTenantIds: string[];
  loading?: boolean;
  onSelectDistributed: (distributedIds: string[]) => void;
}

export function DistributionPreview({
  skillVersion,
  users,
  distributedUserIds,
  selectedTenantIds,
  loading,
  onSelectDistributed,
}: DistributionPreviewProps) {
  const { t } = useTranslation();

  // 计算当前选中用户的分发统计
  const stats = useMemo(() => {
    const selectedUsers = users.filter((u) =>
      selectedTenantIds.includes(u.tenant_id)
    );
    const firstTime = selectedUsers.filter(
      (u) => u.status === "first_time"
    ).length;
    const update = selectedUsers.filter(
      (u) => u.status === "update"
    ).length;
    const conflict = selectedUsers.filter(
      (u) => u.status === "conflict"
    ).length;
    return { firstTime, update, conflict };
  }, [users, selectedTenantIds]);

  // 是否勾选了"默认选中已分发用户"
  const isSelectDistributedChecked = useMemo(() => {
    if (distributedUserIds.length === 0) return false;
    // 所有已分发用户都在选中列表中
    return distributedUserIds.every((id) =>
      selectedTenantIds.includes(id)
    );
  }, [distributedUserIds, selectedTenantIds]);

  // 勾选/取消勾选"默认选中已分发用户"
  const handleSelectDistributedChange = (checked: boolean) => {
    if (checked) {
      onSelectDistributed(distributedUserIds);
    } else {
      // 取消勾选时，清空选择（由父组件处理）
      onSelectDistributed([]);
    }
  };

  return (
    <div className={styles.previewCard}>
      <div className={styles.previewHeader}>
        <span className={styles.previewTitle}>
          {t("distributionPreview.title", "分发预览")}
        </span>
        {distributedUserIds.length > 0 && (
          <Checkbox
            checked={isSelectDistributedChecked}
            onChange={(e) => handleSelectDistributedChange(e.target.checked)}
          >
            {t(
              "distributionPreview.selectDistributed",
              "默认选中已分发用户"
            )}
          </Checkbox>
        )}
      </div>

      {loading ? (
        <Spin size="small" className={styles.previewSpin} />
      ) : (
        <>
          <div className={styles.statsRow}>
            <div className={styles.statItem}>
              <div className={styles.statNumber} style={{ color: "#52c41a" }}>
                {stats.firstTime}
              </div>
              <div className={styles.statLabel} style={{ color: "#52c41a" }}>
                {t("distributionPreview.firstTime", "首次分发")}
              </div>
            </div>
            <div className={styles.statItem}>
              <div className={styles.statNumber} style={{ color: "#1890ff" }}>
                {stats.update}
              </div>
              <div className={styles.statLabel} style={{ color: "#1890ff" }}>
                {t("distributionPreview.update", "覆盖更新")}
              </div>
            </div>
            <div className={styles.statItem}>
              <div className={styles.statNumber} style={{ color: "#faad14" }}>
                {stats.conflict}
              </div>
              <div className={styles.statLabel} style={{ color: "#faad14" }}>
                {t("distributionPreview.conflict", "跳过(冲突)")}
              </div>
            </div>
          </div>

          <div className={styles.previewInfo}>
            {t("distributionPreview.currentVersion", "当前技能版本")}:{" "}
            {skillVersion} | {t("distributionPreview.distributedCount", "已分发用户数")}:{" "}
            {distributedUserIds.length}
          </div>
        </>
      )}
    </div>
  );
}

export default DistributionPreview;