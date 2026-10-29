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
const DISCOVERY_WINDOW_MS = 30_000;
const REQUEST_TIMEOUT_MS = 10_000;
const REFRESH_ERROR = "状态刷新失败，正在重试";
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
  const [refreshError, setRefreshError] = useState(false);
  const resetKeyRef = useRef(resetKey);
  const snapshotRef = useRef<SubAgentRunSnapshot | null>(null);
  const stoppingIdsRef = useRef(new Set<string>());
  const ownerRef = useRef<object | null>(null);
  const refreshControlRef = useRef({ refresh: () => {}, invalidate: () => {} });

  const commitSnapshot = useCallback((next: SubAgentRunSnapshot | null) => {
    snapshotRef.current = next;
    setSnapshot(next);
  }, []);

  useEffect(() => {
    const owner = {};
    ownerRef.current = owner;
    let controller: AbortController | null = null;
    let queued = false;
    let pollTimer: number | undefined;
    let confirmTimer: number | undefined;
    let discoveryUntil = 0;
    let knownRunIds = new Set<string>();
    const isCurrent = () => ownerRef.current === owner;

    commitSnapshot(null);
    setExpanded(false);
    stoppingIdsRef.current = new Set();
    setStoppingIds(new Set());
    setRowErrors({});
    setHiddenRunIds(null);
    setRefreshError(false);

    const invalidate = () => {
      window.clearTimeout(pollTimer);
      queued = false;
      const previous = controller;
      controller = null;
      previous?.abort();
    };

    const refresh = async () => {
      if (!chatId || !isCurrent()) return;
      if (controller) {
        queued = true;
        return;
      }
      window.clearTimeout(pollTimer);
      const requestController = new AbortController();
      controller = requestController;
      const isRequestCurrent = () =>
        isCurrent() && controller === requestController;
      const timeout = window.setTimeout(
        () => requestController.abort(),
        REQUEST_TIMEOUT_MS,
      );
      let removeAbortListener = () => {};
      const aborted = new Promise<never>((_, reject) => {
        const onAbort = () =>
          reject(new Error("SubAgent status request aborted"));
        requestController.signal.addEventListener("abort", onAbort, {
          once: true,
        });
        removeAbortListener = () =>
          requestController.signal.removeEventListener("abort", onAbort);
      });
      let failed = false;
      try {
        const next = await Promise.race([
          chatApi.getSubAgentRuns(chatId, requestController.signal),
          aborted,
        ]);
        if (!isRequestCurrent()) return;
        if (next.chat_id !== chatId)
          throw new Error("SubAgent snapshot chat mismatch");
        if (next.runs.some((run) => !knownRunIds.has(run.run_id)))
          discoveryUntil = 0;
        commitSnapshot(next);
        setRefreshError(false);
      } catch {
        if (!isRequestCurrent()) return;
        failed = true;
        setRefreshError(true);
      } finally {
        window.clearTimeout(timeout);
        removeAbortListener();
        if (isRequestCurrent()) {
          controller = null;
          if (queued) {
            queued = false;
            void refresh();
          } else if (
            failed ||
            hasNonTerminalRuns(snapshotRef.current?.runs ?? []) ||
            Date.now() < discoveryUntil
          ) {
            pollTimer = window.setTimeout(
              () => void refresh(),
              POLL_INTERVAL_MS,
            );
          }
        }
      }
    };

    refreshControlRef.current = { refresh: () => void refresh(), invalidate };
    const handleRefreshEvent = (event: Event) => {
      const detail = (
        event as CustomEvent<{ chatId?: string; discover?: boolean }>
      ).detail;
      if (detail?.chatId && detail.chatId !== chatId) return;
      if (detail?.discover !== false) {
        discoveryUntil = Date.now() + DISCOVERY_WINDOW_MS;
        knownRunIds = new Set(
          snapshotRef.current?.runs.map((run) => run.run_id) ?? [],
        );
      }
      void refresh();
      window.clearTimeout(confirmTimer);
      confirmTimer = window.setTimeout(
        () => void refresh(),
        EVENT_CONFIRM_REFRESH_DELAY_MS,
      );
    };
    document.addEventListener(SUBAGENT_RUNS_REFRESH_EVENT, handleRefreshEvent);
    void refresh();
    return () => {
      ownerRef.current = null;
      invalidate();
      window.clearTimeout(confirmTimer);
      document.removeEventListener(
        SUBAGENT_RUNS_REFRESH_EVENT,
        handleRefreshEvent,
      );
    };
  }, [chatId, commitSnapshot]);

  useEffect(() => {
    if (resetKeyRef.current === resetKey) return;
    resetKeyRef.current = resetKey;
    setExpanded(false);
    setHiddenRunIds(
      (previous) =>
        new Set([
          ...(previous ?? []),
          ...(snapshotRef.current?.runs
            .filter((run) => TERMINAL_STATUSES.has(run.status))
            .map((run) => run.run_id) ?? []),
        ]),
    );
    refreshControlRef.current.refresh();
  }, [resetKey]);

  const visibleRuns = useMemo(
    () =>
      snapshot?.chat_id === chatId
        ? snapshot.runs.filter((run) => isVisibleAfterReset(run, hiddenRunIds))
        : [],
    [chatId, hiddenRunIds, snapshot],
  );

  const handleStop = useCallback(
    async (run: SubAgentRunSnapshotItem) => {
      if (
        !chatId ||
        run.status !== "running" ||
        stoppingIdsRef.current.has(run.run_id)
      )
        return;
      const owner = ownerRef.current;
      const isCurrent = () => owner !== null && ownerRef.current === owner;
      stoppingIdsRef.current.add(run.run_id);
      setStoppingIds(new Set(stoppingIdsRef.current));
      setRowErrors((previous) => {
        const next = { ...previous };
        delete next[run.run_id];
        return next;
      });
      try {
        const result = await chatApi.cancelSubAgentRun(chatId, run.run_id);
        if (!isCurrent()) return;
        refreshControlRef.current.invalidate();
        const previous = snapshotRef.current;
        if (previous) {
          commitSnapshot({
            ...previous,
            runs: previous.runs.map((item) =>
              item.run_id === result.run.run_id ? result.run : item,
            ),
          });
        }
        refreshControlRef.current.refresh();
      } catch {
        if (!isCurrent()) return;
        setRowErrors((previous) => ({
          ...previous,
          [run.run_id]: "停止请求失败",
        }));
        message.error("停止请求失败");
        refreshControlRef.current.refresh();
      } finally {
        if (isCurrent()) {
          stoppingIdsRef.current.delete(run.run_id);
          setStoppingIds(new Set(stoppingIdsRef.current));
        }
      }
    },
    [chatId, commitSnapshot, message],
  );

  if (!chatId) return null;
  if (visibleRuns.length === 0) {
    return refreshError ? (
      <div className={styles.anchor}>
        <p className={styles.refreshError} role="status">
          {REFRESH_ERROR}
        </p>
      </div>
    ) : null;
  }

  return (
    <div className={styles.anchor}>
      {refreshError ? (
        <p className={styles.refreshError} role="status">
          {REFRESH_ERROR}
        </p>
      ) : null}
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
                    <span>时间 {timeBudgetLabel(run)}</span>
                    <span>轮次 {turnBudgetLabel(run)}</span>
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
        </button>
      )}
    </div>
  );
}
