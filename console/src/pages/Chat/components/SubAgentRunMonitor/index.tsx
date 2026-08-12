import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { StopOutlined } from "@ant-design/icons";
import { chatApi } from "../../../../api/modules/chat";
import type {
  SubAgentRunSnapshot,
  SubAgentRunSnapshotItem,
  SubAgentRunStatus,
} from "../../../../api/types/chat";
import { useAppMessage } from "../../../../hooks/useAppMessage";
import { SUBAGENT_RUNS_REFRESH_EVENT } from "../../subAgentRunEvents";
import styles from "./index.module.less";

export { SUBAGENT_RUNS_REFRESH_EVENT };
const POLL_INTERVAL_MS = 10_000;
const EVENT_CONFIRM_REFRESH_DELAY_MS = 400;
const TERMINAL_STATUSES = new Set<SubAgentRunStatus>([
  "completed",
  "partial",
  "failed",
  "cancelled",
  "expired",
]);

const STATUS_LABELS: Record<SubAgentRunStatus, string> = {
  pending: "启动中",
  running: "运行中",
  paused: "已暂停",
  completed: "已完成",
  partial: "部分完成",
  failed: "失败",
  cancelled: "已停止",
  expired: "已过期",
};

function hasNonTerminalRuns(runs: SubAgentRunSnapshotItem[]): boolean {
  return runs.some((run) => !TERMINAL_STATUSES.has(run.status));
}

function isVisibleAfterReset(
  run: SubAgentRunSnapshotItem,
  hiddenRunIds: Set<string> | null,
): boolean {
  return !hiddenRunIds?.has(run.run_id);
}

function formatDuration(ms: number | null | undefined): string {
  if (ms === undefined || ms === null) return "-";
  if (ms < 1000) return `${ms}ms`;
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest > 0 ? `${minutes}m ${rest}s` : `${minutes}m`;
}

function budgetPercent(run: SubAgentRunSnapshotItem): number {
  return Math.max(
    0,
    Math.min(100, Math.round(run.budget_consumption.ratio * 100)),
  );
}

function timeBudgetLabel(run: SubAgentRunSnapshotItem): string {
  return `${formatDuration(
    run.budget_consumption.elapsed_ms,
  )} / ${formatDuration(run.budget_consumption.timeout_ms)}`;
}

function turnBudgetLabel(run: SubAgentRunSnapshotItem): string {
  return `${run.budget_consumption.turns_used} / ${run.budget_consumption.max_turns}`;
}

function displayName(run: SubAgentRunSnapshotItem): string {
  return run.nickname?.trim() || run.agent_name;
}

export default function SubAgentRunMonitor(props: {
  chatId: string | null;
  resetKey: number;
}) {
  const { chatId, resetKey } = props;
  const { message } = useAppMessage();
  const [snapshot, setSnapshot] = useState<SubAgentRunSnapshot | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [stoppingIds, setStoppingIds] = useState<Set<string>>(() => new Set());
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [hiddenRunIds, setHiddenRunIds] = useState<Set<string> | null>(null);
  const [expandedResultIds, setExpandedResultIds] = useState<Set<string>>(
    () => new Set(),
  );
  const requestSeqRef = useRef(0);
  const resetKeyRef = useRef(resetKey);
  const snapshotRef = useRef<SubAgentRunSnapshot | null>(null);
  const confirmRefreshTimerRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    if (!chatId) {
      setSnapshot(null);
      return;
    }
    const seq = requestSeqRef.current + 1;
    requestSeqRef.current = seq;
    try {
      const next = await chatApi.getSubAgentRuns(chatId);
      if (requestSeqRef.current === seq) {
        snapshotRef.current = next;
        setSnapshot(next);
      }
    } catch {
      if (requestSeqRef.current === seq) {
        snapshotRef.current = null;
        setSnapshot(null);
      }
    }
  }, [chatId]);

  useEffect(() => {
    snapshotRef.current = null;
    setSnapshot(null);
    setExpanded(false);
    setStoppingIds(new Set());
    setRowErrors({});
    setHiddenRunIds(null);
    setExpandedResultIds(new Set());
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (resetKeyRef.current === resetKey) return;
    resetKeyRef.current = resetKey;
    requestSeqRef.current += 1;
    setSnapshot(null);
    setExpanded(false);
    setStoppingIds(new Set());
    setRowErrors({});
    setExpandedResultIds(new Set());
    setHiddenRunIds(
      new Set(snapshotRef.current?.runs.map((run) => run.run_id) ?? []),
    );
  }, [resetKey]);

  const visibleRuns = useMemo(
    () =>
      snapshot?.runs.filter((run) => isVisibleAfterReset(run, hiddenRunIds)) ??
      [],
    [hiddenRunIds, snapshot],
  );

  useEffect(() => {
    if (!hasNonTerminalRuns(visibleRuns)) return undefined;
    const timer = window.setInterval(() => {
      void refresh();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [refresh, visibleRuns]);

  useEffect(() => {
    const handler = () => {
      void refresh();
      if (confirmRefreshTimerRef.current !== null) {
        window.clearTimeout(confirmRefreshTimerRef.current);
      }
      confirmRefreshTimerRef.current = window.setTimeout(() => {
        confirmRefreshTimerRef.current = null;
        void refresh();
      }, EVENT_CONFIRM_REFRESH_DELAY_MS);
    };
    document.addEventListener(SUBAGENT_RUNS_REFRESH_EVENT, handler);
    return () =>
      document.removeEventListener(SUBAGENT_RUNS_REFRESH_EVENT, handler);
  }, [refresh]);

  useEffect(
    () => () => {
      if (confirmRefreshTimerRef.current !== null) {
        window.clearTimeout(confirmRefreshTimerRef.current);
        confirmRefreshTimerRef.current = null;
      }
    },
    [chatId],
  );

  const activeCount = useMemo(
    () =>
      visibleRuns.filter((run) => !TERMINAL_STATUSES.has(run.status)).length,
    [visibleRuns],
  );

  const handleStop = useCallback(
    async (run: SubAgentRunSnapshotItem) => {
      if (!chatId || run.status !== "running") return;
      setStoppingIds((previous) => new Set(previous).add(run.run_id));
      setRowErrors((previous) => {
        const next = { ...previous };
        delete next[run.run_id];
        return next;
      });
      try {
        const result = await chatApi.cancelSubAgentRun(chatId, run.run_id);
        setSnapshot((previous) => {
          if (!previous) return previous;
          return {
            ...previous,
            runs: previous.runs.map((item) =>
              item.run_id === result.run.run_id ? result.run : item,
            ),
          };
        });
        void refresh();
      } catch {
        setRowErrors((previous) => ({
          ...previous,
          [run.run_id]: "停止请求失败",
        }));
        message.error("停止请求失败");
        void refresh();
      } finally {
        setStoppingIds((previous) => {
          const next = new Set(previous);
          next.delete(run.run_id);
          return next;
        });
      }
    },
    [chatId, message, refresh],
  );

  if (!snapshot || visibleRuns.length === 0) return null;

  return (
    <div className={styles.anchor}>
      {expanded ? (
        <section className={styles.panel} aria-label="助手运行状态">
          <button
            type="button"
            className={styles.header}
            aria-expanded="true"
            onClick={() => setExpanded(false)}
          >
            <span className={styles.activityDots} aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            <span className={styles.title}>助手运行状态</span>
            <span className={styles.count}>{visibleRuns.length}</span>
          </button>
          <ul className={styles.list}>
            {visibleRuns.map((run) => {
              const stopping = stoppingIds.has(run.run_id);
              const name = displayName(run);
              const terminal = TERMINAL_STATUSES.has(run.status);
              const resultExpanded = expandedResultIds.has(run.run_id);
              return (
                <li
                  key={run.run_id}
                  className={styles.row}
                  data-status={stopping ? "stopping" : run.status}
                >
                  <div className={styles.rowMain}>
                    <span className={styles.name} title={name}>
                      {name}
                    </span>
                    <span className={styles.status}>
                      {stopping ? "停止中" : STATUS_LABELS[run.status]}
                    </span>
                    {run.status === "running" ? (
                      <button
                        type="button"
                        className={styles.stopButton}
                        aria-label={`停止 ${name}`}
                        title="停止运行"
                        disabled={stopping}
                        onClick={() => void handleStop(run)}
                      >
                        <StopOutlined />
                      </button>
                    ) : null}
                  </div>
                  <div className={styles.objective} title={run.objective}>
                    {run.objective}
                  </div>
                  <div className={styles.meta}>
                    <span>已用时间 {timeBudgetLabel(run)}</span>
                    <span>已用轮次 {turnBudgetLabel(run)}</span>
                  </div>
                  <div
                    className={styles.progress}
                    role="progressbar"
                    aria-label={`${name} 时间预算消耗`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={budgetPercent(run)}
                  >
                    <div
                      className={styles.progressFill}
                      style={{ width: `${budgetPercent(run)}%` }}
                    />
                  </div>
                  {terminal && run.summary_preview ? (
                    <div className={styles.result}>
                      <button
                        type="button"
                        className={styles.resultToggle}
                        aria-expanded={resultExpanded}
                        onClick={() =>
                          setExpandedResultIds((previous) => {
                            const next = new Set(previous);
                            if (next.has(run.run_id)) {
                              next.delete(run.run_id);
                            } else {
                              next.add(run.run_id);
                            }
                            return next;
                          })
                        }
                      >
                        {resultExpanded ? "收起结果" : "查看结果"}
                      </button>
                      {resultExpanded ? (
                        <p className={styles.preview}>{run.summary_preview}</p>
                      ) : null}
                    </div>
                  ) : null}
                  {run.error_preview ? (
                    <p className={styles.error}>{run.error_preview}</p>
                  ) : null}
                  {rowErrors[run.run_id] ? (
                    <p className={styles.error}>{rowErrors[run.run_id]}</p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ) : (
        <button
          type="button"
          className={styles.trigger}
          aria-expanded="false"
          aria-label="助手运行状态"
          onClick={() => setExpanded(true)}
        >
          <span className={styles.activityDots} aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span>
            {activeCount > 0 ? `${activeCount} 个助手运行中` : "查看助手状态"}
          </span>
        </button>
      )}
    </div>
  );
}
