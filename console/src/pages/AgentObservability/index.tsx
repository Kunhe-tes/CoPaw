import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Button, Empty, Input, Spin, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { RefreshCw } from "lucide-react";
import {
  listAgentObservabilityRuns,
  type AgentObservabilityRun,
  type AgentObservabilityRunPage,
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
    setPage(null);
    setCursor(undefined);
    setHistory([undefined]);
    windowRef.current = null;
    void load();
    return () => requestRef.current?.abort();
  }, [isAdmin, isManager, load, source]);

  const applySources = () => {
    const next = sourceText.trim()
      ? [...new Set(sourceText.split(",").map((item) => item.trim()).filter(Boolean))]
      : undefined;
    setSources(next);
  };

  const columns: ColumnsType<AgentObservabilityRun> = [
    {
      title: "开始时间",
      dataIndex: "started_at",
      width: 176,
      render: (value: string) => new Date(value).toLocaleString(),
    },
    { title: "状态", dataIndex: "status", width: 132, render: (value: string | null) => (
      <Tag color={statusColor(value)}>{valueOrDash(value)}</Tag>
    ) },
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
      {error && <Alert type="error" showIcon message="执行列表不可用" description={error} />}
      <section className={styles.tableRegion} aria-busy={loading}>
        <Spin spinning={loading}>
          <Table<AgentObservabilityRun>
            rowKey="run_id"
            columns={columns}
            dataSource={visiblePage?.items ?? []}
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
    </main>
  );
}
