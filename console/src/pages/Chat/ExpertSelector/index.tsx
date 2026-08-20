import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckOutlined, LoadingOutlined } from "@ant-design/icons";
import { Dropdown, Spin, Tooltip } from "antd";
import { SparkDownLine } from "@agentscope-ai/icons";
import { expertsApi, type Expert } from "../../../api/modules/experts";
import { useAppMessage } from "../../../hooks/useAppMessage";
import {
  normalizeSelectableExperts,
  resolveExpertLabel,
  toggleExpertSelection,
  type SelectableExpert,
} from "../expertSelection";
import styles from "./index.module.less";

export interface ExpertSelectorProps {
  planModeEnabled: boolean;
  selectedExpertId: string | null;
  onChange: (expertId: string | null) => void;
  onDisablePlanMode: () => void;
  disabled?: boolean;
}

export default function ExpertSelector({
  planModeEnabled,
  selectedExpertId,
  onChange,
  onDisablePlanMode,
  disabled = false,
}: ExpertSelectorProps) {
  const { message } = useAppMessage();
  const [experts, setExperts] = useState<SelectableExpert[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const selectedExpert = useMemo(
    () => experts.find((expert) => expert.id === selectedExpertId) || null,
    [experts, selectedExpertId],
  );

  const loadExperts = useCallback(async () => {
    setLoading(true);
    try {
      const records = await expertsApi.listExperts();
      setExperts(normalizeSelectableExperts(records as Expert[]));
    } catch (error) {
      setExperts([]);
      message.error(error instanceof Error ? error.message : "加载专家失败");
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void loadExperts();
  }, [loadExperts]);

  const handleSelect = (expert: SelectableExpert) => {
    if (disabled) return;
    if (planModeEnabled) {
      onDisablePlanMode();
    }
    onChange(toggleExpertSelection(selectedExpertId, expert.id, false));
    setOpen(false);
  };

  const label = selectedExpert ? resolveExpertLabel(selectedExpert) : "专家";

  return (
    <Dropdown
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) void loadExperts();
      }}
      trigger={["click"]}
      placement="bottomRight"
      disabled={disabled}
      dropdownRender={() => (
        <div className={styles.panel} role="menu" aria-label="专家选择">
          {loading ? (
            <div className={styles.state}>
              <Spin size="small" />
            </div>
          ) : experts.length === 0 ? (
            <div className={styles.state}>暂无可用专家</div>
          ) : (
            experts.map((expert) => (
              <button
                key={expert.id}
                type="button"
                className={`${styles.item} ${
                  expert.id === selectedExpertId ? styles.itemActive : ""
                }`}
                onClick={() => handleSelect(expert)}
                role="menuitem"
              >
                <span className={styles.itemText}>
                  <span className={styles.itemName}>{expert.name}</span>
                  {expert.description ? (
                    <span className={styles.itemDescription}>
                      {expert.description}
                    </span>
                  ) : null}
                </span>
                {expert.id === selectedExpertId ? (
                  <CheckOutlined className={styles.check} />
                ) : null}
              </button>
            ))
          )}
        </div>
      )}
    >
      <Tooltip title="选择专家" mouseEnterDelay={0.5}>
        <button
          type="button"
          className={`${styles.trigger} ${open ? styles.triggerActive : ""}`}
          disabled={disabled}
          aria-label={selectedExpert ? `已选择专家 ${label}` : "选择专家"}
        >
          {loading ? <LoadingOutlined className={styles.loading} /> : null}
          <span className={styles.triggerName}>{label}</span>
          <SparkDownLine
            className={`${styles.arrow} ${open ? styles.arrowOpen : ""}`}
          />
        </button>
      </Tooltip>
    </Dropdown>
  );
}
