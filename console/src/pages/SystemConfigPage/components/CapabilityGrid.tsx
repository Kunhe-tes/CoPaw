import { Radio, Tag } from "antd";

import type {
  CapabilityFilter,
  CapabilityId,
  CapabilitySummary,
} from "../workbench";
import styles from "../index.module.less";

interface CapabilityGridProps {
  summaries: readonly CapabilitySummary[];
  filter: CapabilityFilter;
  onFilterChange: (filter: CapabilityFilter) => void;
  onSelect: (id: CapabilityId) => void;
}

const stateLabels = {
  default: "采用默认值",
  custom: "已自定义",
  unsaved: "有未保存修改",
} as const;

export function CapabilityGrid({
  summaries,
  filter,
  onFilterChange,
  onSelect,
}: CapabilityGridProps) {
  return (
    <section className={styles.workbenchOverview} aria-label="系统配置能力概览">
      <Radio.Group
        value={filter}
        onChange={(event) => onFilterChange(event.target.value)}
      >
        <Radio.Button value="all">全部</Radio.Button>
        <Radio.Button value="custom">已自定义</Radio.Button>
        <Radio.Button value="unsaved">有未保存修改</Radio.Button>
      </Radio.Group>
      <div className={styles.capabilityGrid}>
        {summaries.map((summary) => (
          <button
            key={summary.id}
            className={styles.capabilityCard}
            type="button"
            onClick={() => onSelect(summary.id)}
          >
            <span className={styles.capabilityCardHeader}>
              <span className={styles.capabilityCardTitle}>
                {summary.title}
              </span>
              <Tag color={summary.state === "unsaved" ? "gold" : undefined}>
                {stateLabels[summary.state]}
              </Tag>
            </span>
            <span className={styles.capabilityCardDescription}>
              {summary.description}
            </span>
            <span className={styles.capabilityCardFooter}>
              <span>{summary.sourceLabel}</span>
              <span>{summary.summary}</span>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
