import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Button, Drawer, Empty, Input, Spin, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { RefreshCw } from "lucide-react";
import {
  getAgentObservabilityCapabilities,
  getAgentObservabilityHealth,
  getAgentObservabilityRunDetail,
  listAgentObservabilityRuns,
  type AgentObservabilityCapabilities,
  type AgentObservabilityHealth,
  type AgentObservabilityRun,
  type AgentObservabilityRunPage,
  type AgentObservabilityRunDetail,
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
  const [capabilities, setCapabilities] = useState<AgentObservabilityCapabilities | null>(null);
  const [capabilityError, setCapabilityError] = useState<string | null>(null);
  const [health, setHealth] = useState<AgentObservabilityHealth | null>(null);
  const [selectedRun, setSelectedRun] = useState<AgentObservabilityRun | null>(null);
  const [detail, setDetail] = useState<AgentObservabilityRunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const activeScope = `${isAdmin ? "admin" : "manager"}:${source ?? ""}:${(sources ?? []).join(",")}`;
  const visiblePage = pageScope === activeScope ? page : null;

  const load = useCallback(async (nextCursor?: string) => {
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
      windowRef.current = { start: result.window_start, end: result.window_end };
    } catch (cause) {
      if (!controller.signal.aborted) {
        setError(cause instanceof Error ? cause.message : "查询执行列表失败");
      }
    } finally {
      setLoading(false);
    }
  }, [activeScope, sources]);

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
          setCapabilityError(cause instanceof Error ? cause.message : "读取能力状态失败");
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
    windowRef.current = null;
    void load();
    return () => {
      controller.abort();
      requestRef.current?.abort();
    };
  }, [isAdmin, isManager, load, source]);

  const applySources = () => {
    const next = sourceText.trim()
      ? [...new Set(sourceText.split(",").map((item) => item.trim()).filter(Boolean))]
      : undefined;
    setSources(next);
  };

  const openRun = async (run: AgentObservabilityRun) => {
    setSelectedRun(run);
    setDetail(null);
    setDetailLoading(true);
    try {
      setDetail(await getAgentObservabilityRunDetail(run.run_id));
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const columns: ColumnsType<AgentObservabilityRun> = [
    {
      title: "开始时间",
      dataIndex: "started_at",
      width: 176,
      render: (value: string) => new Date(value).toLocaleString(),
    },
    { title: "状态", dataIndex: "status", width: 132, render: (value: string | null) => {
      const displayStatus = value ?? "unknown";
      return <Tag color={statusColor(value)}>{displayStatus}</Tag>;
    } },
    { title: "Source", dataIndex: "source_key", width: 156, ellipsis: true },
    { title: "Agent", dataIndex: "agent_key", width: 136, ellipsis: true },
    { title: "Chat", dataIndex: "chat_key", width: 180, ellipsis: true },
    { title: "问题 ID", dataIndex: "root_question_key", width: 190, ellipsis: true },
    {
      title: "耗时",
      dataIndex: "duration_us",
      width: 96,
      align: "right",
      render: (value: number | null) => value == null ? "-" : `${(value / 1000).toFixed(0)} ms`,
    },
    { title: "模型调用", dataIndex: "llm_calls", width: 96, align: "right", render: valueOrDash },
    { title: "工具调用", dataIndex: "tool_calls", width: 96, align: "right", render: valueOrDash },
    { title: "Span", dataIndex: "span_count", width: 72, align: "right", render: valueOrDash },
    { title: "数据质量", dataIndex: "quality", width: 110, render: (value: string) => <Tag>{value}</Tag> },
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

  return (
    !isAdmin && !isManager ? (
      <main className={styles.page}>
        <h1>403</h1>
        <Text type="secondary">仅管理员和运营人员可访问 Agent 执行。</Text>
      </main>
    ) :
    <main className={styles.page}>
      <div className={styles.heading}>
        <div>
          <h1>Agent 执行</h1>
          <Text type="secondary">Run 列表 · 最近 24 小时</Text>
        </div>
        <Button icon={<RefreshCw size={15} />} onClick={() => void load(cursor)} loading={loading}>
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
            placeholder={`当前 Source：${source || "默认"}；多个 Source 用逗号分隔`}
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
          type={capabilities.capture_enabled && capabilities.storage_ready ? "success" : "warning"}
          showIcon
          message={`采集${capabilities.capture_enabled ? "已开启" : "已关闭"} · 元数据存储${capabilities.storage_ready ? "就绪" : capabilities.storage_configured ? "未就绪" : "未配置"} · 投影器${capabilities.projector_running ? "运行中" : "未运行"}`}
          description={`事件队列上限 ${capabilities.queue_events} 条 / ${Math.round(capabilities.queue_bytes / 1024 / 1024)} MiB；单事件上限 ${Math.round(capabilities.max_event_bytes / 1024)} KiB${health?.dropped_events == null ? "" : `；进程累计丢弃 ${health.dropped_events} 条`}`}
        />
      )}
      {error && <Alert type="error" showIcon message="执行列表不可用" description={error} />}
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
            locale={{ emptyText: error ? <Empty description="暂时无法读取" /> : <Empty description="当前时间范围没有已投影的 Run" /> }}
          />
        </Spin>
      </section>
      <footer className={styles.footer}>
        <Text type="secondary">查询时间：{visiblePage?.generated_at ? new Date(visiblePage.generated_at).toLocaleString() : "-"}</Text>
        <div>
          <Button disabled={history.length < 2 || loading} onClick={goPrevious}>上一页</Button>
          <Button type="primary" disabled={!visiblePage?.next_cursor || loading} onClick={goNext}>下一页</Button>
        </div>
      </footer>
      <Drawer
        title={selectedRun ? `Run ${selectedRun.run_id}` : "Run Inspector"}
        open={selectedRun !== null}
        onClose={() => setSelectedRun(null)}
        width={Math.min(760, window.innerWidth - 24)}
      >
        <Spin spinning={detailLoading}>
          {detail ? (
            <div className={styles.inspector}>
              <div className={styles.attempts}>
                <Text strong>Attempts</Text>
                {detail.attempts.map((attempt) => (
                  <div className={styles.attempt} key={attempt.attempt_id}>
                    <Tag color={statusColor(attempt.status)}>
                      #{attempt.attempt_index} {attempt.status ?? "unknown"}
                    </Tag>
                    <Text type="secondary">{attempt.attempt_id}</Text>
                  </div>
                ))}
              </div>
              <Text strong>Agent 操作树 · 瀑布</Text>
              <div className={styles.spanList}>
                {detail.spans.map((span) => (
                  <div
                    className={styles.spanRow}
                    key={span.span_id}
                    style={{ paddingLeft: `${Math.min(32, span.parent_span_id ? 20 : 0)}px` }}
                  >
                    <div>
                      <Text strong>{span.name || "unknown"}</Text>
                      <Text type="secondary"> · {span.operation} · {span.span_type}</Text>
                    </div>
                    <div className={styles.spanMeta}>
                      <Tag color={statusColor(span.status)}>{span.status ?? "unknown"}</Tag>
                      <Text type="secondary">
                        {span.duration_us == null ? "进行中/未知" : `${Math.round(span.duration_us / 1000)} ms`}
                      </Text>
                    </div>
                  </div>
                ))}
              </div>
              {detail.spans_has_more && (
                <Text type="secondary">已加载部分 Span；更多节点需要分页加载。</Text>
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
