import { useState } from "react";
import { Popover, Progress } from "antd";
import type {
  ContextUsageAvailableSnapshot,
  ContextUsageSnapshot,
  ContextUsageStatus,
} from "@/api/types/contextUsage";
import styles from "./index.module.less";

const STATUS_LABELS: Record<ContextUsageStatus, string> = {
  normal: "正常",
  governance: "接近治理阈值",
  active: "已进入压缩区间",
  emergency: "紧急",
  overflow: "已超出上限",
};

const TRIGGER_STATUS_LABELS: Partial<Record<ContextUsageStatus, string>> = {
  governance: "注意",
  active: "压缩",
  emergency: "紧急",
  overflow: "超限",
};

export interface ContextUsageIndicatorProps {
  snapshot?: ContextUsageSnapshot;
  error: boolean;
  refresh: () => void;
}

function formatCompactTokens(value: number): string {
  const compact = (divisor: number, suffix: string) => {
    const scaled = value / divisor;
    const digits = scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2;
    return `${Number(scaled.toFixed(digits))}${suffix}`;
  };

  if (value >= 1_000_000) return compact(1_000_000, "M");
  if (value >= 1_000) return compact(1_000, "K");
  return String(value);
}

function formatFullTokens(value: number): string {
  return value.toLocaleString("en-US");
}

function getPercentage(snapshot: ContextUsageAvailableSnapshot): number {
  return Math.max(0, Math.round(snapshot.usage_ratio * 100));
}

function ContextUsageDetails({
  error,
  refresh,
  snapshot,
}: {
  error: boolean;
  refresh: () => void;
  snapshot?: ContextUsageSnapshot;
}) {
  if (!snapshot?.available) {
    return (
      <div className={styles.details} role="dialog" aria-label="上下文占用详情">
        <div className={styles.title}>上下文占用</div>
        <p className={styles.guidance}>
          {error
            ? "暂时无法获取，请稍后打开重试。"
            : "尚无可用快照，发送一条消息后再查看。"}
        </p>
        {error ? (
          <button type="button" onClick={refresh}>
            重试
          </button>
        ) : null}
      </div>
    );
  }

  const percentage = getPercentage(snapshot);
  const progressPercentage = Math.min(percentage, 100);
  const categories = [
    ["系统上下文", snapshot.system_context_tokens],
    ["工具定义", snapshot.tool_definition_tokens],
    ["对话消息", snapshot.conversation_tokens],
  ] as const;

  return (
    <div className={styles.details} role="dialog" aria-label="上下文占用详情">
      <div className={styles.header}>
        <div>
          <div className={styles.title}>上下文占用</div>
          <div className={styles.total}>
            约 {formatCompactTokens(snapshot.used_tokens)} /{" "}
            {formatCompactTokens(snapshot.max_tokens)}
          </div>
        </div>
        <span className={`${styles.status} ${styles[snapshot.status]}`}>
          {STATUS_LABELS[snapshot.status]}
        </span>
      </div>
      <div
        className={styles.progress}
        role="progressbar"
        aria-label="上下文占用"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progressPercentage}
      >
        <Progress
          percent={progressPercentage}
          showInfo={false}
          strokeColor="currentColor"
          trailColor="#e8edf5"
          aria-hidden="true"
        />
      </div>
      <div className={styles.remaining}>
        剩余约 {formatCompactTokens(snapshot.remaining_tokens)}
      </div>
      <div className={styles.categories}>
        {categories.map(([label, value]) => {
          const compactValue = formatCompactTokens(value);
          const fullValue = formatFullTokens(value);
          return (
            <div className={styles.category} key={label}>
              <span>{label}</span>
              <span className={styles.value}>
                ~{compactValue}
                {compactValue !== fullValue ? (
                  <span className={styles.fullValue}>{fullValue}</span>
                ) : null}
              </span>
            </div>
          );
        })}
      </div>
      {snapshot.stale ? (
        <p className={styles.notice}>正在生成，显示上次保存结果。</p>
      ) : null}
      {error ? (
        <p className={styles.notice}>刷新失败，继续显示上次结果。</p>
      ) : null}
      <p className={styles.disclosure}>估算值，不是模型供应商账单。</p>
    </div>
  );
}

export default function ContextUsageIndicator({
  snapshot,
  error,
  refresh,
}: ContextUsageIndicatorProps) {
  const [open, setOpen] = useState(false);
  const available = snapshot?.available === true;
  const percentage = available ? getPercentage(snapshot) : null;
  const statusLabel = available ? STATUS_LABELS[snapshot.status] : "暂无数据";
  const compactStatus = available
    ? TRIGGER_STATUS_LABELS[snapshot.status]
    : undefined;

  return (
    <Popover
      content={
        <ContextUsageDetails
          snapshot={snapshot}
          error={error}
          refresh={refresh}
        />
      }
      trigger="click"
      placement="topLeft"
      open={open}
      onOpenChange={setOpen}
      overlayClassName={styles.popover}
    >
      <button
        type="button"
        className={`${styles.trigger} ${
          available ? styles[snapshot.status] : styles.unavailable
        }`}
        aria-label={
          available
            ? `上下文占用 ${percentage}%，状态${statusLabel}`
            : "上下文占用，暂无数据"
        }
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <span>上下文</span>
        <span className={styles.percentage}>
          {percentage === null ? "--" : `${percentage}%`}
        </span>
        {compactStatus ? (
          <span className={styles.compactStatus}>· {compactStatus}</span>
        ) : null}
      </button>
    </Popover>
  );
}
