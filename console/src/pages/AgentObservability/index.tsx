import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Drawer,
  Empty,
  Input,
  Select,
  Spin,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { RefreshCw } from "lucide-react";
import {
  getAgentObservabilityCapabilities,
  getAgentObservabilityHealth,
  getAgentObservabilityRunDetail,
  getAgentObservabilityRunEvents,
  listAgentObservabilityRuns,
  type AgentObservabilityCapabilities,
  type AgentObservabilityHealth,
  type AgentObservabilityRun,
  type AgentObservabilityRunPage,
  type AgentObservabilityRunDetail,
  type AgentObservabilitySpan,
  type AgentObservabilityEvent,
} from "../../api/modules/agentObservability";
import { useIframeStore } from "../../stores/iframeStore";
import styles from "./index.module.less";

const { Text } = Typography;

function valueOrDash(value: string | number | null | undefined) {
  return value === null || value === undefined || value === "" ? "-" : value;
}

function statusColor(status: string | null) {
  if (status === "succeeded") return "green";
  if (status === "failed" || status === "rejected") return "red";
  if (status === "running" || status === "waiting_approval") return "blue";
  return "default";
}

function isActiveStatus(status: string | null | undefined) {
  return (
    status === "accepted" ||
    status === "running" ||
    status === "waiting_approval"
  );
}

function spanStatusLabel(span: AgentObservabilitySpan) {
  return span.ended_at ? span.status ?? "终态未知" : "未观察到结束";
}

function spanRowStatusLabel(span: AgentObservabilitySpan) {
  if (!span.ended_at) return "缺结束事件";
  if (span.status === "succeeded") return "成功";
  if (span.status === "failed") return "失败";
  if (span.status === "cancelled") return "已取消";
  if (span.status === "rejected") return "已拒绝";
  if (span.status === "waiting_approval") return "待审批";
  return span.status ?? "终态未知";
}

function spanQualityLabel(quality: string | null) {
  if (quality === "observed") return "完整";
  if (quality === "partial") return "部分";
  return "未知";
}

function spanBarClass(
  span: AgentObservabilitySpan,
  styles: Record<string, string>,
) {
  let stateClass = styles.spanBar;
  if (!span.ended_at) stateClass = styles.spanBarOpen;
  else if (span.status === "succeeded") stateClass = styles.spanBarSuccess;
  else if (span.status === "failed" || span.status === "rejected") {
    stateClass = styles.spanBarError;
  } else if (span.status === "waiting_approval") {
    stateClass = styles.spanBarWaiting;
  }
  return `${styles.spanBar} ${stateClass}`;
}

function formatUtc(value: string | null) {
  if (!value) return "未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "未知";
  const fraction = value.match(/\.(\d+)/)?.[1] ?? "";
  return `${date.toISOString().slice(0, 19).replace("T", " ")}.${fraction
    .padEnd(6, "0")
    .slice(0, 6)} UTC`;
}

function utcMicros(value: string) {
  const millis = Date.parse(value);
  if (!Number.isFinite(millis)) return null;
  const fraction = value.match(/\.(\d+)/)?.[1] ?? "";
  return millis * 1000 + Number(fraction.padEnd(6, "0").slice(3, 6));
}

function spanTiming(span: AgentObservabilitySpan, observedAt: string) {
  const started = utcMicros(span.started_at);
  const ended = utcMicros(span.ended_at ?? observedAt);
  const wallInterval =
    started == null || ended == null ? null : ended - started;
  const difference =
    span.ended_at && wallInterval != null && span.duration_us != null
      ? wallInterval - span.duration_us
      : null;
  return { wallInterval, difference };
}

function spanHierarchy(
  span: AgentObservabilitySpan,
  spansById: Map<string, AgentObservabilitySpan>,
) {
  const visited = new Set([span.span_id]);
  let current = span;
  let depth = 0;
  let missingParent = false;
  let cycle = false;
  while (current.parent_span_id) {
    if (visited.has(current.parent_span_id)) {
      cycle = true;
      break;
    }
    visited.add(current.parent_span_id);
    const parent = spansById.get(current.parent_span_id);
    if (!parent) {
      missingParent = true;
      break;
    }
    depth += 1;
    current = parent;
  }
  return {
    depth: Math.min(missingParent ? Math.max(1, depth) : depth, 4),
    missingParent,
    cycle,
  };
}

export default function AgentObservabilityPage() {
  const isAdmin = useIframeStore((state) => state.isSuperManager);
  const isManager = useIframeStore((state) => state.manager);
  const source = useIframeStore((state) => state.source);
  const [sourceText, setSourceText] = useState("");
  const [sources, setSources] = useState<string[] | undefined>();
  const [page, setPage] = useState<AgentObservabilityRunPage | null>(null);
  const [pageScope, setPageScope] = useState("");
  const [cursor, setCursor] = useState<string | undefined>();
  const [history, setHistory] = useState<(string | undefined)[]>([undefined]);
  const windowRef = useRef<{ start: string; end: string } | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [capabilities, setCapabilities] =
    useState<AgentObservabilityCapabilities | null>(null);
  const [capabilityError, setCapabilityError] = useState<string | null>(null);
  const [health, setHealth] = useState<AgentObservabilityHealth | null>(null);
  const [selectedRun, setSelectedRun] = useState<AgentObservabilityRun | null>(
    null,
  );
  const [selectedAttemptId, setSelectedAttemptId] = useState<string | null>(
    null,
  );
  const [detail, setDetail] = useState<AgentObservabilityRunDetail | null>(
    null,
  );
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [spansLoading, setSpansLoading] = useState(false);
  const [events, setEvents] = useState<AgentObservabilityEvent[]>([]);
  const [eventCursor, setEventCursor] = useState<string | null>(null);
  const [eventSpanId, setEventSpanId] = useState<string | undefined>();
  const [eventsLoading, setEventsLoading] = useState(false);
  const eventRequestRef = useRef<AbortController | null>(null);
  const detailRequestRef = useRef<AbortController | null>(null);
  const activeScope = `${isAdmin ? "admin" : "manager"}:${source ?? ""}:${(
    sources ?? []
  ).join(",")}`;
  const visiblePage = pageScope === activeScope ? page : null;

  const load = useCallback(
    async (nextCursor?: string) => {
      requestRef.current?.abort();
      const controller = new AbortController();
      requestRef.current = controller;
      setLoading(true);
      setError(null);
      try {
        const result = await listAgentObservabilityRuns(
          {
            sources,
            cursor: nextCursor,
            limit: 50,
            start: windowRef.current?.start,
            end: windowRef.current?.end,
          },
          controller.signal,
        );
        setPage(result);
        setPageScope(activeScope);
        setCursor(nextCursor);
        windowRef.current = {
          start: result.window_start,
          end: result.window_end,
        };
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "查询执行列表失败");
        }
      } finally {
        setLoading(false);
      }
    },
    [activeScope, sources],
  );

  useEffect(() => {
    if (!isAdmin && !isManager) return;
    const controller = new AbortController();
    setCapabilities(null);
    setCapabilityError(null);
    setHealth(null);
    void getAgentObservabilityCapabilities(controller.signal)
      .then(setCapabilities)
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setCapabilityError(
            cause instanceof Error ? cause.message : "读取能力状态失败",
          );
        }
      });
    if (isAdmin) {
      void getAgentObservabilityHealth(controller.signal)
        .then(setHealth)
        .catch(() => {
          if (!controller.signal.aborted) setHealth(null);
        });
    }
    setPage(null);
    setCursor(undefined);
    setHistory([undefined]);
    eventRequestRef.current?.abort();
    detailRequestRef.current?.abort();
    setSelectedRun(null);
    setSelectedAttemptId(null);
    setDetail(null);
    setSelectedSpanId(null);
    setDetailLoading(false);
    setSpansLoading(false);
    setEvents([]);
    setEventCursor(null);
    setEventSpanId(undefined);
    windowRef.current = null;
    void load();
    return () => {
      controller.abort();
      requestRef.current?.abort();
      eventRequestRef.current?.abort();
      detailRequestRef.current?.abort();
    };
  }, [isAdmin, isManager, load, source]);

  const applySources = () => {
    const next = sourceText.trim()
      ? [
          ...new Set(
            sourceText
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
          ),
        ]
      : undefined;
    setSources(next);
  };

  const openRun = async (run: AgentObservabilityRun) => {
    eventRequestRef.current?.abort();
    detailRequestRef.current?.abort();
    setSelectedRun(run);
    setSelectedAttemptId(null);
    setDetail(null);
    setSelectedSpanId(null);
    setSpansLoading(false);
    setEvents([]);
    setEventCursor(null);
    setEventSpanId(undefined);
    setDetailLoading(true);
    const controller = new AbortController();
    detailRequestRef.current = controller;
    void loadEvents(run.run_id);
    try {
      setDetail(
        await getAgentObservabilityRunDetail(run.run_id, {}, controller.signal),
      );
    } catch {
      if (!controller.signal.aborted) setDetail(null);
    } finally {
      if (!controller.signal.aborted) setDetailLoading(false);
      if (detailRequestRef.current === controller) {
        detailRequestRef.current = null;
      }
    }
  };

  const selectAttempt = async (attemptId: string) => {
    if (!selectedRun) return;
    const nextAttemptId = attemptId === "all" ? null : attemptId;
    detailRequestRef.current?.abort();
    const controller = new AbortController();
    detailRequestRef.current = controller;
    setSelectedAttemptId(nextAttemptId);
    setSelectedSpanId(null);
    setSpansLoading(false);
    setDetailLoading(true);
    try {
      setDetail(
        await getAgentObservabilityRunDetail(
          selectedRun.run_id,
          { attemptId: nextAttemptId ?? undefined },
          controller.signal,
        ),
      );
    } catch {
      if (!controller.signal.aborted) setDetail(null);
    } finally {
      if (!controller.signal.aborted) setDetailLoading(false);
      if (detailRequestRef.current === controller) {
        detailRequestRef.current = null;
      }
    }
  };

  const loadEvents = async (
    runId: string,
    options: { spanId?: string; cursor?: string; append?: boolean } = {},
  ) => {
    eventRequestRef.current?.abort();
    const controller = new AbortController();
    eventRequestRef.current = controller;
    setEventsLoading(true);
    try {
      const result = await getAgentObservabilityRunEvents(
        runId,
        { spanId: options.spanId, cursor: options.cursor, limit: 100 },
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setEvents((current) =>
        options.append ? [...current, ...result.items] : result.items,
      );
      setEventCursor(result.next_cursor);
      setEventSpanId(options.spanId);
    } catch {
      if (!controller.signal.aborted) {
        setEvents([]);
        setEventCursor(null);
      }
    } finally {
      if (!controller.signal.aborted) setEventsLoading(false);
    }
  };

  const loadMoreSpans = async () => {
    if (!selectedRun || !detail?.spans_next_cursor || spansLoading) return;
    detailRequestRef.current?.abort();
    const controller = new AbortController();
    detailRequestRef.current = controller;
    setSpansLoading(true);
    try {
      const next = await getAgentObservabilityRunDetail(
        selectedRun.run_id,
        {
          attemptId: selectedAttemptId ?? undefined,
          spanLimit: 200,
          spanCursor: detail.spans_next_cursor,
        },
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setDetail((current) => {
        if (!current || current.run.run_id !== next.run.run_id) return current;
        const seen = new Set(current.spans.map((span) => span.span_id));
        const appended = next.spans.filter((span) => !seen.has(span.span_id));
        return {
          ...current,
          spans: [...current.spans, ...appended],
          spans_has_more: next.spans_has_more,
          spans_next_cursor: next.spans_next_cursor,
        };
      });
    } catch {
      // Keep already loaded nodes available if a later page cannot be read.
    } finally {
      if (!controller.signal.aborted) setSpansLoading(false);
      if (detailRequestRef.current === controller) {
        detailRequestRef.current = null;
      }
    }
  };

  const refreshRunDetail = useCallback(async () => {
    if (
      !selectedRun ||
      detailLoading ||
      spansLoading ||
      detailRequestRef.current ||
      document.visibilityState !== "visible"
    ) {
      return;
    }
    const controller = new AbortController();
    detailRequestRef.current = controller;
    try {
      const refreshed = await getAgentObservabilityRunDetail(
        selectedRun.run_id,
        { attemptId: selectedAttemptId ?? undefined },
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setDetail((current) => {
        if (!current || current.run.run_id !== refreshed.run.run_id) {
          return current;
        }
        const refreshedSpanIds = new Set(
          refreshed.spans.map((span) => span.span_id),
        );
        const hasLoadedLaterPages = current.spans.some(
          (span) => !refreshedSpanIds.has(span.span_id),
        );
        const spans = new Map(
          current.spans.map((span) => [span.span_id, span]),
        );
        for (const span of refreshed.spans) spans.set(span.span_id, span);
        return {
          ...current,
          run: refreshed.run,
          attempts: refreshed.attempts,
          spans: [...spans.values()].sort(
            (left, right) =>
              left.started_at.localeCompare(right.started_at) ||
              left.span_id.localeCompare(right.span_id),
          ),
          spans_has_more: current.spans_has_more || refreshed.spans_has_more,
          spans_next_cursor: hasLoadedLaterPages
            ? current.spans_next_cursor
            : refreshed.spans_next_cursor,
        };
      });
    } catch {
      // A missed refresh does not invalidate already loaded detail.
    } finally {
      if (detailRequestRef.current === controller) {
        detailRequestRef.current = null;
      }
    }
  }, [detailLoading, selectedAttemptId, selectedRun, spansLoading]);

  const rootStatus = detail?.run.status ?? selectedRun?.status;
  const hasKnownActiveExecution = Boolean(
    selectedRun &&
      (isActiveStatus(rootStatus) ||
        detail?.attempts.some(
          (attempt) => !attempt.ended_at && isActiveStatus(attempt.status),
        ) ||
        detail?.spans.some(
          (span) => !span.ended_at && isActiveStatus(span.status),
        )),
  );

  useEffect(() => {
    if (!selectedRun || !hasKnownActiveExecution) return;
    const timer = window.setInterval(() => {
      void refreshRunDetail();
    }, 5000);
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void refreshRunDetail();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [hasKnownActiveExecution, refreshRunDetail, selectedRun]);

  const columns: ColumnsType<AgentObservabilityRun> = [
    {
      title: "开始时间",
      dataIndex: "started_at",
      width: 176,
      render: (value: string) => new Date(value).toLocaleString(),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 132,
      render: (value: string | null) => {
        const displayStatus = value ?? "unknown";
        return <Tag color={statusColor(value)}>{displayStatus}</Tag>;
      },
    },
    { title: "Source", dataIndex: "source_key", width: 156, ellipsis: true },
    { title: "Agent", dataIndex: "agent_key", width: 136, ellipsis: true },
    { title: "Chat", dataIndex: "chat_key", width: 180, ellipsis: true },
    {
      title: "问题 ID",
      dataIndex: "root_question_key",
      width: 190,
      ellipsis: true,
    },
    {
      title: "耗时",
      dataIndex: "duration_us",
      width: 96,
      align: "right",
      render: (value: number | null) =>
        value == null ? "-" : `${(value / 1000).toFixed(0)} ms`,
    },
    {
      title: "模型调用",
      dataIndex: "llm_calls",
      width: 96,
      align: "right",
      render: valueOrDash,
    },
    {
      title: "工具调用",
      dataIndex: "tool_calls",
      width: 96,
      align: "right",
      render: valueOrDash,
    },
    {
      title: "Span",
      dataIndex: "span_count",
      width: 72,
      align: "right",
      render: valueOrDash,
    },
    {
      title: "数据质量",
      dataIndex: "quality",
      width: 110,
      render: (value: string) => <Tag>{value}</Tag>,
    },
  ];

  const goNext = () => {
    if (!visiblePage?.next_cursor) return;
    const next = [...history, visiblePage.next_cursor];
    setHistory(next);
    void load(visiblePage.next_cursor);
  };
  const goPrevious = () => {
    if (history.length < 2) return;
    const next = history.slice(0, -1);
    setHistory(next);
    void load(next[next.length - 1]);
  };

  const spansById = new Map(
    (detail?.spans ?? []).map((span) => [span.span_id, span]),
  );
  const timelinePoints = (detail?.spans ?? []).flatMap((span) => {
    const start = Date.parse(span.started_at);
    const end = Date.parse(span.ended_at ?? detail?.generated_at ?? "");
    return Number.isFinite(start)
      ? [start, ...(Number.isFinite(end) ? [end] : [])]
      : [];
  });
  const timelineStart = timelinePoints.length ? Math.min(...timelinePoints) : 0;
  const timelineEnd = timelinePoints.length
    ? Math.max(...timelinePoints)
    : timelineStart + 1;
  const timelineDuration = Math.max(1, timelineEnd - timelineStart);

  return !isAdmin && !isManager ? (
    <main className={styles.page}>
      <h1>403</h1>
      <Text type="secondary">仅管理员和运营人员可访问 Agent 执行。</Text>
    </main>
  ) : (
    <main className={styles.page}>
      <div className={styles.heading}>
        <div>
          <h1>Agent 执行</h1>
          <Text type="secondary">Run 列表 · 最近 24 小时</Text>
        </div>
        <Button
          icon={<RefreshCw size={15} />}
          onClick={() => void load(cursor)}
          loading={loading}
        >
          刷新
        </Button>
      </div>
      {isAdmin && (
        <div className={styles.filters}>
          <label htmlFor="observability-sources">Source 范围</label>
          <Input
            id="observability-sources"
            value={sourceText}
            onChange={(event) => setSourceText(event.target.value)}
            placeholder={`当前 Source：${
              source || "默认"
            }；多个 Source 用逗号分隔`}
            onPressEnter={applySources}
          />
          <Button onClick={applySources}>应用</Button>
        </div>
      )}
      {capabilityError && (
        <Alert
          type="warning"
          showIcon
          message="采集能力状态不可用"
          description={capabilityError}
        />
      )}
      {capabilities && (
        <Alert
          type={
            capabilities.capture_enabled && capabilities.storage_ready
              ? "success"
              : "warning"
          }
          showIcon
          message={`采集${
            capabilities.capture_enabled ? "已开启" : "已关闭"
          } · 元数据存储${
            capabilities.storage_ready
              ? "就绪"
              : capabilities.storage_configured
              ? "未就绪"
              : "未配置"
          } · 投影器${capabilities.projector_running ? "运行中" : "未运行"}`}
          description={`事件队列上限 ${
            capabilities.queue_events
          } 条 / ${Math.round(
            capabilities.queue_bytes / 1024 / 1024,
          )} MiB；单事件上限 ${Math.round(
            capabilities.max_event_bytes / 1024,
          )} KiB${
            health?.dropped_events == null
              ? ""
              : `；进程累计丢弃 ${health.dropped_events} 条`
          }`}
        />
      )}
      {error && (
        <Alert
          type="error"
          showIcon
          message="执行列表不可用"
          description={error}
        />
      )}
      <section className={styles.tableRegion} aria-busy={loading}>
        <Spin spinning={loading}>
          <Table<AgentObservabilityRun>
            rowKey="run_id"
            columns={columns}
            dataSource={visiblePage?.items ?? []}
            onRow={(record) => ({ onClick: () => void openRun(record) })}
            pagination={false}
            size="small"
            scroll={{ x: 1380 }}
            locale={{
              emptyText: error ? (
                <Empty description="暂时无法读取" />
              ) : (
                <Empty description="当前时间范围没有已投影的 Run" />
              ),
            }}
          />
        </Spin>
      </section>
      <footer className={styles.footer}>
        <Text type="secondary">
          查询时间：
          {visiblePage?.generated_at
            ? new Date(visiblePage.generated_at).toLocaleString()
            : "-"}
        </Text>
        <div>
          <Button disabled={history.length < 2 || loading} onClick={goPrevious}>
            上一页
          </Button>
          <Button
            type="primary"
            disabled={!visiblePage?.next_cursor || loading}
            onClick={goNext}
          >
            下一页
          </Button>
        </div>
      </footer>
      <Drawer
        title={
          selectedRun ? (
            <div className={styles.drawerTitle}>
              <span>Run {selectedRun.run_id}</span>
              <Button
                size="small"
                icon={<RefreshCw size={14} />}
                aria-label="刷新 Run 详情"
                title="刷新 Run 详情"
                loading={detailLoading}
                onClick={(event) => {
                  event.stopPropagation();
                  void openRun(selectedRun);
                }}
              />
            </div>
          ) : (
            "Run Inspector"
          )
        }
        open={selectedRun !== null}
        onClose={() => {
          eventRequestRef.current?.abort();
          detailRequestRef.current?.abort();
          setSelectedRun(null);
          setSelectedAttemptId(null);
          setSelectedSpanId(null);
        }}
        width={Math.min(760, window.innerWidth - 24)}
      >
        <Spin spinning={detailLoading}>
          {detail ? (
            <div className={styles.inspector}>
              <div className={styles.attempts}>
                <Text strong>Attempt</Text>
                <Select
                  aria-label="按 Attempt 查看操作"
                  value={selectedAttemptId ?? "all"}
                  onChange={(value) => void selectAttempt(value)}
                  options={[
                    { value: "all", label: "全部 Attempts" },
                    ...detail.attempts.map((attempt) => ({
                      value: attempt.attempt_id,
                      label: `#${attempt.attempt_index} · ${
                        attempt.status ?? "unknown"
                      }`,
                    })),
                  ]}
                />
              </div>
              <div className={styles.waterfallHeader}>
                <Text strong>Agent 操作树 · 瀑布</Text>
                <Text type="secondary">
                  截至 {formatUtc(detail.generated_at)}
                </Text>
              </div>
              <div className={styles.waterfallScale} aria-label="相对时间范围">
                <div className={styles.spanTimeScale}>
                  <span>0 ms</span>
                  <span>{(timelineDuration / 1000).toFixed(0)} ms</span>
                </div>
              </div>
              <div
                className={styles.spanList}
                role="tree"
                aria-label="Agent 操作树"
              >
                {detail.spans.map((span) => {
                  const hierarchy = spanHierarchy(span, spansById);
                  return (
                    <div
                      className={`${styles.spanRow} ${
                        selectedSpanId === span.span_id
                          ? styles.spanRowSelected
                          : ""
                      }`}
                      key={span.span_id}
                      role="treeitem"
                      aria-level={hierarchy.depth + 1}
                      aria-selected={selectedSpanId === span.span_id}
                    >
                      <button
                        type="button"
                        className={styles.spanSelect}
                        style={{
                          paddingLeft: `${hierarchy.depth * 16}px`,
                        }}
                        aria-pressed={selectedSpanId === span.span_id}
                        title={
                          hierarchy.missingParent
                            ? "父 Span 未加载"
                            : hierarchy.cycle
                            ? "检测到循环父关系"
                            : span.span_id
                        }
                        onClick={() => setSelectedSpanId(span.span_id)}
                      >
                        <span className={styles.spanName}>
                          {span.name || "unknown"}
                        </span>
                        <span className={styles.spanDescriptor}>
                          {hierarchy.missingParent
                            ? "父节点未加载 · "
                            : hierarchy.cycle
                            ? "循环父关系 · "
                            : ""}
                          {span.operation} · {span.span_type}
                        </span>
                      </button>
                      <div
                        className={styles.spanTimeline}
                        aria-label={`${formatUtc(
                          span.started_at,
                        )} 至 ${formatUtc(span.ended_at)}`}
                      >
                        <span
                          className={spanBarClass(span, styles)}
                          style={{
                            left: `${Math.max(
                              0,
                              ((Date.parse(span.started_at) - timelineStart) /
                                timelineDuration) *
                                100,
                            )}%`,
                            width: `${Math.max(
                              1,
                              ((Date.parse(
                                span.ended_at ?? detail.generated_at,
                              ) -
                                Date.parse(span.started_at)) /
                                timelineDuration) *
                                100,
                            )}%`,
                          }}
                        />
                      </div>
                      <div className={styles.spanMeta}>
                        <Tag
                          color={statusColor(
                            span.ended_at ? span.status : null,
                          )}
                        >
                          {spanRowStatusLabel(span)}
                        </Tag>
                        <Text
                          type="secondary"
                          title={`Span 质量：${span.quality ?? "unknown"}`}
                        >
                          {spanQualityLabel(span.quality)}
                        </Text>
                        <Button
                          size="small"
                          type={
                            eventSpanId === span.span_id ? "primary" : "default"
                          }
                          onClick={() =>
                            selectedRun &&
                            void loadEvents(selectedRun.run_id, {
                              spanId: span.span_id,
                            })
                          }
                        >
                          事件
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
              {selectedSpanId &&
                spansById.has(selectedSpanId) &&
                (() => {
                  const span = spansById.get(selectedSpanId)!;
                  const timing = spanTiming(span, detail.generated_at);
                  return (
                    <section
                      className={styles.spanInspector}
                      aria-label="Span Inspector"
                    >
                      <Text strong>{span.name || "unknown"} · Inspector</Text>
                      <dl>
                        <div>
                          <dt>类型 / 操作</dt>
                          <dd>
                            {span.span_type} · {span.operation} · {span.kind}
                          </dd>
                        </div>
                        <div>
                          <dt>业务状态</dt>
                          <dd>{spanStatusLabel(span)}</dd>
                        </div>
                        <div>
                          <dt>技术状态</dt>
                          <dd>
                            {span.technical_status ?? "未知"}
                            {span.has_error == null
                              ? " · 错误标志未知"
                              : span.has_error
                              ? " · 有技术错误"
                              : " · 无技术错误"}
                          </dd>
                        </div>
                        <div>
                          <dt>观测质量</dt>
                          <dd>{span.quality ?? "unknown"}</dd>
                        </div>
                        <div>
                          <dt>开始 / 结束（UTC）</dt>
                          <dd>
                            {formatUtc(span.started_at)} →{" "}
                            {formatUtc(span.ended_at)}
                          </dd>
                        </div>
                        <div>
                          <dt>单调耗时 / 墙钟区间</dt>
                          <dd>
                            {span.duration_us == null
                              ? "单调耗时未知"
                              : `${(span.duration_us / 1000).toFixed(
                                  1,
                                )} ms 单调`}
                            {" · "}
                            {timing.wallInterval == null
                              ? "墙钟区间未知"
                              : `${(timing.wallInterval / 1000).toFixed(
                                  1,
                                )} ms 墙钟`}
                            {timing.difference != null &&
                              Math.abs(timing.difference) >= 1000 && (
                                <Text type="warning">
                                  {` · 区间相差 ${(
                                    Math.abs(timing.difference) / 1000
                                  ).toFixed(1)} ms`}
                                </Text>
                              )}
                          </dd>
                        </div>
                        <div>
                          <dt>Span ID</dt>
                          <dd>{span.span_id}</dd>
                        </div>
                        <div>
                          <dt>父 Span</dt>
                          <dd>{span.parent_span_id ?? "无"}</dd>
                        </div>
                        <div>
                          <dt>Attempt</dt>
                          <dd>{span.attempt_id ?? "未关联"}</dd>
                        </div>
                        {span.span_type === "LLM" && (
                          <>
                            <div>
                              <dt>Provider / 请求模型</dt>
                              <dd>
                                {span.provider_key ?? "未知"} ·{" "}
                                {span.request_model_key ?? "未知"}
                              </dd>
                            </div>
                            <div>
                              <dt>响应模型 / 来源</dt>
                              <dd>
                                {span.response_model_key ??
                                  span.model_key ??
                                  "未知"}{" "}
                                · {span.model_key_source ?? "未知"}
                              </dd>
                            </div>
                            <div>
                              <dt>Usage</dt>
                              <dd>
                                输入 {span.input_tokens ?? "未知"} · 输出{" "}
                                {span.output_tokens ?? "未知"}
                              </dd>
                            </div>
                            <div>
                              <dt>首输出</dt>
                              <dd>
                                有效内容{" "}
                                {span.time_to_first_chunk_us == null
                                  ? "未知"
                                  : `${(
                                      span.time_to_first_chunk_us / 1000
                                    ).toFixed(1)} ms`}{" "}
                                · 文本{" "}
                                {span.time_to_first_visible_text_us == null
                                  ? "未知"
                                  : `${(
                                      span.time_to_first_visible_text_us / 1000
                                    ).toFixed(1)} ms`}
                              </dd>
                            </div>
                          </>
                        )}
                      </dl>
                    </section>
                  );
                })()}
              {detail.spans_has_more && (
                <Button
                  size="small"
                  loading={spansLoading}
                  onClick={() => void loadMoreSpans()}
                >
                  加载更多 Span
                </Button>
              )}
              <div className={styles.eventHeader}>
                <Text strong>{eventSpanId ? "Span 事件" : "Run 事件"}</Text>
                {eventSpanId && (
                  <Button
                    size="small"
                    onClick={() =>
                      selectedRun && void loadEvents(selectedRun.run_id)
                    }
                  >
                    全部事件
                  </Button>
                )}
              </div>
              <Spin spinning={eventsLoading}>
                <div className={styles.eventList}>
                  {events.map((event) => (
                    <div className={styles.eventRow} key={event.event_id}>
                      <div>
                        <Text strong>
                          {String(
                            event.metadata.event_kind ?? event.event_name,
                          )}
                        </Text>
                        <Text type="secondary">
                          {" "}
                          · {event.phase_key} · {event.local_seq}
                        </Text>
                      </div>
                      <Text type="secondary">
                        {new Date(event.occurred_at).toLocaleString()}
                      </Text>
                    </div>
                  ))}
                  {!eventsLoading && events.length === 0 && (
                    <Text type="secondary">没有已投影的事件</Text>
                  )}
                </div>
              </Spin>
              {eventCursor && selectedRun && (
                <Button
                  size="small"
                  loading={eventsLoading}
                  onClick={() =>
                    void loadEvents(selectedRun.run_id, {
                      spanId: eventSpanId,
                      cursor: eventCursor,
                      append: true,
                    })
                  }
                >
                  加载更多事件
                </Button>
              )}
            </div>
          ) : (
            <Empty description="暂无可用执行详情" />
          )}
        </Spin>
      </Drawer>
    </main>
  );
}
