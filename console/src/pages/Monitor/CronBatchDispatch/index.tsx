import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  DatePicker,
  Empty,
  Input,
  Pagination,
  Progress,
  Segmented,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Tooltip,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  RefreshCw,
  ShieldCheck,
  TimerReset,
} from "lucide-react";
import {
  monitorApi,
  type CronDispatchBatchDetailResponse,
  type CronDispatchBatchItem,
  type CronDispatchCapacityItem,
  type CronDispatchDateFilters,
  type CronDispatchEventItem,
  type CronDispatchIntentItem,
  type CronDispatchPolicyItem,
  type CronDispatchWorkersResponse,
} from "../../../api/modules/monitor";
import { DEFAULT_SOURCE_ID } from "../../../constants/identity";
import { useIframeStore } from "../../../stores/iframeStore";
import styles from "./index.module.less";

const { RangePicker } = DatePicker;

type DateShortcutKey = "today" | "last24h" | "last7" | "custom";

const DATE_SHORTCUTS: Array<{ label: string; value: DateShortcutKey }> = [
  { label: "今天", value: "today" },
  { label: "近24h", value: "last24h" },
  { label: "近7天", value: "last7" },
];

const STATUS_OPTIONS = [
  { label: "全部状态", value: "all" },
  { label: "已接收", value: "received" },
  { label: "等待中", value: "pending" },
  { label: "运行中", value: "running" },
  { label: "已完成", value: "completed" },
  { label: "失败", value: "failed" },
];

const INTENT_ROLE_OPTIONS = [
  { label: "全部角色", value: "all" },
  { label: "父任务", value: "parent" },
  { label: "子任务", value: "child" },
];

const INTENT_STATUS_OPTIONS = [
  { label: "全部状态", value: "all" },
  { label: "等待中", value: "pending" },
  { label: "已领取", value: "claimed" },
  { label: "已分发", value: "dispatched" },
  { label: "已完成", value: "completed" },
  { label: "失败", value: "failed" },
  { label: "已取消", value: "cancelled" },
];

const statusColor: Record<string, string> = {
  received: "default",
  pending: "processing",
  running: "blue",
  completed: "success",
  failed: "error",
  cancelled: "warning",
  claimed: "processing",
  acknowledged: "geekblue",
  dispatched: "blue",
};

const statusLabel: Record<string, string> = {
  received: "已接收",
  pending: "等待中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  claimed: "已领取",
  acknowledged: "已确认",
  dispatched: "已分发",
};

function formatDateTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function formatNumber(value: number | undefined | null) {
  return Number(value || 0).toLocaleString("en-US");
}

function formatPercent(numerator: number, denominator: number) {
  if (!denominator) return "0.0%";
  return `${((numerator / denominator) * 100).toFixed(1)}%`;
}

function renderStatus(status: string) {
  return (
    <Tag color={statusColor[status] || "default"}>
      {statusLabel[status] || status}
    </Tag>
  );
}

function shortBatchId(batchId: string) {
  return batchId.startsWith("cron:") ? batchId.slice(5) : batchId;
}

function matchesQuery(
  query: string,
  values: Array<string | number | null | undefined>,
) {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (!normalizedQuery) return true;
  return values.some((value) =>
    String(value ?? "")
      .toLocaleLowerCase()
      .includes(normalizedQuery),
  );
}

function buildRange(shortcut: DateShortcutKey): [Dayjs, Dayjs] {
  const now = dayjs();
  if (shortcut === "today") {
    return [now.startOf("day"), now.endOf("day")];
  }
  if (shortcut === "last24h") {
    return [now.subtract(24, "hour"), now];
  }
  return [now.subtract(6, "day").startOf("day"), now.endOf("day")];
}

function buildDateFilters(
  dateRange: [Dayjs, Dayjs],
  status: string,
): CronDispatchDateFilters {
  return {
    start_time: dateRange[0].format("YYYY-MM-DDTHH:mm:ss"),
    end_time: dateRange[1].format("YYYY-MM-DDTHH:mm:ss"),
    status: status === "all" ? undefined : status,
  };
}

function jsonText(value: unknown, pretty = false) {
  if (value === null || value === undefined) return "-";
  try {
    return JSON.stringify(value, null, pretty ? 2 : undefined) || "-";
  } catch {
    return String(value);
  }
}

function jsonSummary(value: unknown) {
  const text = jsonText(value);
  return text.length > 96 ? `${text.slice(0, 96)}...` : text;
}

function SummaryMetric({
  title,
  value,
  hint,
  danger = false,
}: {
  title: string;
  value: string;
  hint: string;
  danger?: boolean;
}) {
  return (
    <div
      className={`${styles.summaryMetric} ${danger ? styles.metricDanger : ""}`}
    >
      <span>{title}</span>
      <strong>{value}</strong>
      <em>{hint}</em>
    </div>
  );
}

function PolicyCard({ policy }: { policy: CronDispatchPolicyItem }) {
  const strategy = policy.strategy || {};
  const rules = strategy.error_rate_rules ?? null;
  return (
    <article className={styles.policyCard}>
      <div className={styles.policyHead}>
        <div>
          <h3>{policy.provider_id}</h3>
          <p>{policy.model_id}</p>
        </div>
        <Tag color={policy.enabled ? "success" : "default"}>
          {policy.enabled ? "启用" : "停用"}
        </Tag>
      </div>
      <div className={styles.policyGrid}>
        <span>默认策略</span>
        <strong>{policy.default_strategy_id || "-"}</strong>
        <span>最小/基线/最大</span>
        <strong>
          {String(strategy.min_workers ?? "-")} /{" "}
          {String(strategy.baseline_workers ?? "-")} /{" "}
          {String(strategy.max_workers ?? "-")}
        </strong>
        <span>调整间隔</span>
        <strong>{String(strategy.adjust_interval_seconds ?? "-")}s</strong>
        <span>反馈窗口</span>
        <strong>{String(strategy.feedback_window_seconds ?? "-")}s</strong>
      </div>
      <Tooltip
        title={
          <pre className={styles.jsonTooltip}>
            {jsonText(policy.strategy_schedule, true)}
          </pre>
        }
        placement="topLeft"
        overlayStyle={{ maxWidth: 560 }}
      >
        <div className={styles.policyJson}>
          schedule={jsonSummary(policy.strategy_schedule)}
        </div>
      </Tooltip>
      <Tooltip
        title={
          <pre className={styles.jsonTooltip}>{jsonText(rules, true)}</pre>
        }
        placement="topLeft"
        overlayStyle={{ maxWidth: 560 }}
      >
        <div className={styles.policyJson}>rules={jsonSummary(rules)}</div>
      </Tooltip>
    </article>
  );
}

function CapacityRow({ item }: { item: CronDispatchCapacityItem }) {
  const denominator = Math.max(
    item.max_workers || item.effective_workers || 1,
    1,
  );
  const percent = Math.min(
    100,
    Math.round((item.effective_workers / denominator) * 100),
  );
  return (
    <div className={styles.capacityRow}>
      <div className={styles.capacityMeta}>
        <strong>{item.model_id}</strong>
        <span>{item.provider_id}</span>
      </div>
      <Progress percent={percent} showInfo={false} size="small" />
      <div className={styles.capacityValue}>
        <strong>{item.effective_workers}</strong>
        <span>{item.decision_reason || "-"}</span>
      </div>
    </div>
  );
}

function CapacityEventRow({ item }: { item: CronDispatchCapacityItem }) {
  return (
    <details className={styles.workerEvent}>
      <summary
        className={styles.workerEventSummary}
        aria-label={`查看调整记录 ${item.id}`}
      >
        <strong>{item.decision_reason || "-"}</strong>
        <span>
          {item.provider_id}/{item.model_id} · {item.previous_workers} →{" "}
          {item.effective_workers}
        </span>
        <em>{formatDateTime(item.created_at)}</em>
        <ChevronDown
          size={15}
          className={styles.workerEventChevron}
          aria-hidden="true"
        />
      </summary>
      <dl className={styles.workerEventDetails}>
        <div>
          <dt>记录 ID</dt>
          <dd>{item.id}</dd>
        </div>
        <div className={styles.workerEventIdentity}>
          <dt>Worker ID</dt>
          <dd>{item.worker_id || "-"}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>{item.source_id || "-"}</dd>
        </div>
        <div>
          <dt>策略</dt>
          <dd>{item.strategy_id || "-"}</dd>
        </div>
        <div>
          <dt>最小 / 基线 / 最大</dt>
          <dd>
            {item.min_workers} / {item.baseline_workers} / {item.max_workers}
          </dd>
        </div>
        <div>
          <dt>调整前 / 调整后</dt>
          <dd>
            {item.previous_workers} / {item.effective_workers}
          </dd>
        </div>
        <div>
          <dt>等待 / 已领取 / 运行</dt>
          <dd>
            {item.pending_count} / {item.claimed_count} / {item.running_count}
          </dd>
        </div>
        <div>
          <dt>成功 / 失败</dt>
          <dd>
            {item.success_count} / {item.failure_count}
          </dd>
        </div>
        <div>
          <dt>失败率</dt>
          <dd>{(item.error_rate * 100).toFixed(2)}%</dd>
        </div>
        <div>
          <dt>平均耗时</dt>
          <dd>{item.avg_latency_ms} ms</dd>
        </div>
        <div>
          <dt>记录时间</dt>
          <dd>{formatDateTime(item.created_at)}</dd>
        </div>
        <div className={styles.workerEventRule}>
          <dt>命中规则</dt>
          <dd>
            <pre>{jsonText(item.matched_rule, true)}</pre>
          </dd>
        </div>
      </dl>
    </details>
  );
}

function CapacityEventHistory({
  items,
}: {
  items: CronDispatchCapacityItem[];
}) {
  const visibleItems = items.slice(0, 8);
  const eventKey = visibleItems.map((item) => item.id).join(":");
  const [navigation, setNavigation] = useState({ eventKey: "", index: 0 });

  const safeActiveIndex =
    navigation.eventKey === eventKey
      ? Math.min(navigation.index, Math.max(visibleItems.length - 1, 0))
      : 0;
  const activeItem = visibleItems[safeActiveIndex];

  return (
    <>
      <div className={styles.subSectionTitle}>
        <div className={styles.subSectionTitleLabel}>
          <TimerReset size={16} />
          <span>最近调整记录</span>
        </div>
        {activeItem ? (
          <div
            className={styles.workerEventNavigation}
            role="group"
            aria-label="调整记录翻页"
          >
            <span className={styles.workerEventPosition} aria-live="polite">
              {safeActiveIndex + 1} / {visibleItems.length}
            </span>
            <Button
              type="text"
              size="small"
              className={styles.workerEventNavButton}
              aria-label="上一条调整记录"
              icon={<ChevronLeft size={15} />}
              disabled={safeActiveIndex === 0}
              onClick={() =>
                setNavigation({
                  eventKey,
                  index: Math.max(safeActiveIndex - 1, 0),
                })
              }
            />
            <Button
              type="text"
              size="small"
              className={styles.workerEventNavButton}
              aria-label="下一条调整记录"
              icon={<ChevronRight size={15} />}
              disabled={safeActiveIndex === visibleItems.length - 1}
              onClick={() =>
                setNavigation({
                  eventKey,
                  index: Math.min(safeActiveIndex + 1, visibleItems.length - 1),
                })
              }
            />
          </div>
        ) : null}
      </div>
      <div className={styles.workerEventList}>
        {activeItem ? (
          <CapacityEventRow key={activeItem.id} item={activeItem} />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无调整记录"
          />
        )}
      </div>
    </>
  );
}

function EventList({ events }: { events: CronDispatchEventItem[] }) {
  if (!events.length) {
    return (
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无调度事件" />
    );
  }
  return (
    <div className={styles.eventList}>
      {events.map((event) => (
        <div key={event.id} className={styles.eventItem}>
          <time>{formatDateTime(event.created_at)}</time>
          <Tooltip title={event.event_type} placement="topLeft">
            <strong>{event.event_type}</strong>
          </Tooltip>
          <Tooltip
            title={`worker=${event.worker_id || "-"} · intent=${
              event.intent_id || "-"
            } · job=${event.job_id || "-"}`}
            placement="topLeft"
          >
            <p>
              worker={event.worker_id || "-"} · intent={event.intent_id || "-"}{" "}
              · job=
              {event.job_id || "-"}
            </p>
          </Tooltip>
          {event.details ? (
            <Tooltip title={jsonSummary(event.details)} placement="topLeft">
              <em>{jsonSummary(event.details)}</em>
            </Tooltip>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export default function CronBatchDispatchPage() {
  const sourceId = useIframeStore((state) => state.source) || DEFAULT_SOURCE_ID;
  const isSuperManager = useIframeStore((state) => state.isSuperManager);
  const manager = useIframeStore((state) => state.manager);
  const canView = isSuperManager || manager;
  const [shortcut, setShortcut] = useState<DateShortcutKey>("today");
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>(() =>
    buildRange("today"),
  );
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [batches, setBatches] = useState<CronDispatchBatchItem[]>([]);
  const [batchTotal, setBatchTotal] = useState(0);
  const [stats, setStats] = useState({
    total_batches: 0,
    running_batches: 0,
    completed_batches: 0,
    failed_batches: 0,
    total_intents: 0,
    completed_intents: 0,
    failed_intents: 0,
    pending_intents: 0,
  });
  const [workers, setWorkers] = useState<CronDispatchWorkersResponse | null>(
    null,
  );
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [detail, setDetail] = useState<CronDispatchBatchDetailResponse | null>(
    null,
  );
  const [batchLoading, setBatchLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [workerLoading, setWorkerLoading] = useState(false);
  const [batchQuery, setBatchQuery] = useState("");
  const [intentQuery, setIntentQuery] = useState("");
  const [intentRole, setIntentRole] = useState("all");
  const [intentStatus, setIntentStatus] = useState("all");
  const [detailTab, setDetailTab] = useState("intents");
  const batchRequestId = useRef(0);
  const detailRequestId = useRef(0);
  const workerRequestId = useRef(0);

  const filters = useMemo(
    () => buildDateFilters(dateRange, status),
    [dateRange, status],
  );

  const filteredBatches = useMemo(
    () =>
      batches.filter((batch) =>
        matchesQuery(batchQuery, [
          batch.batch_id,
          batch.parent_job_id,
          batch.parent_external_job_id,
          batch.tenant_id,
          batch.provider_id,
          batch.model_id,
          batch.agent_id,
        ]),
      ),
    [batchQuery, batches],
  );

  const selectedDetail =
    detail?.batch.batch_id === selectedBatchId ? detail : null;

  const filteredIntents = useMemo(() => {
    const intents = selectedDetail?.intents || [];
    return intents.filter(
      (intent) =>
        matchesQuery(intentQuery, [
          intent.id,
          intent.tenant_id,
          intent.job_id,
          intent.parent_job_id,
          intent.agent_id,
          intent.provider_id,
          intent.model_id,
          intent.error_message,
        ]) &&
        (intentRole === "all" || intent.intent_role === intentRole) &&
        (intentStatus === "all" || intent.status === intentStatus),
    );
  }, [selectedDetail?.intents, intentQuery, intentRole, intentStatus]);

  const fetchBatches = useCallback(async () => {
    const requestId = ++batchRequestId.current;
    if (!canView) return;
    setBatchLoading(true);
    try {
      const response = await monitorApi.getCronDispatchBatches(
        page,
        pageSize,
        filters,
      );
      if (requestId === batchRequestId.current) {
        setBatches(response.items);
        setBatchTotal(response.total);
        setStats(response.stats);
        setSelectedBatchId((current) => {
          if (response.items.some((item) => item.batch_id === current)) {
            return current;
          }
          return response.items[0]?.batch_id || "";
        });
      }
    } catch (error) {
      if (requestId !== batchRequestId.current) return;
      console.error("Failed to fetch cron dispatch batches:", error);
      message.error("批调度 batch 加载失败");
      setBatches([]);
      setBatchTotal(0);
    } finally {
      if (requestId === batchRequestId.current) {
        setBatchLoading(false);
      }
    }
  }, [canView, filters, page, pageSize]);

  const fetchWorkers = useCallback(async () => {
    const requestId = ++workerRequestId.current;
    if (!canView) return;
    setWorkerLoading(true);
    try {
      const response = await monitorApi.getCronDispatchWorkers({
        start_time: filters.start_time,
        end_time: filters.end_time,
      });
      if (requestId === workerRequestId.current) {
        setWorkers(response);
      }
    } catch (error) {
      if (requestId !== workerRequestId.current) return;
      console.error("Failed to fetch cron dispatch workers:", error);
      message.error("批调度 worker 加载失败");
      setWorkers(null);
    } finally {
      if (requestId === workerRequestId.current) {
        setWorkerLoading(false);
      }
    }
  }, [canView, filters.end_time, filters.start_time]);

  const fetchDetail = useCallback(async () => {
    const requestId = ++detailRequestId.current;
    if (!canView || !selectedBatchId) {
      setDetail(null);
      setDetailLoading(false);
      return;
    }
    setDetailLoading(true);
    try {
      const response = await monitorApi.getCronDispatchBatchDetail(
        selectedBatchId,
        { intent_limit: "500", event_limit: "500" },
      );
      if (requestId === detailRequestId.current) {
        setDetail(response);
      }
    } catch (error) {
      if (requestId !== detailRequestId.current) return;
      console.error("Failed to fetch cron dispatch batch detail:", error);
      message.error("批调度详情加载失败");
      setDetail(null);
    } finally {
      if (requestId === detailRequestId.current) {
        setDetailLoading(false);
      }
    }
  }, [canView, selectedBatchId]);

  useEffect(() => {
    fetchBatches();
  }, [fetchBatches]);

  useEffect(() => {
    fetchWorkers();
  }, [fetchWorkers]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  useEffect(() => {
    if (!filteredBatches.length) {
      setSelectedBatchId("");
      return;
    }
    if (!filteredBatches.some((batch) => batch.batch_id === selectedBatchId)) {
      setSelectedBatchId(filteredBatches[0].batch_id);
    }
  }, [filteredBatches, selectedBatchId]);

  const handleShortcutChange = (value: DateShortcutKey) => {
    setShortcut(value);
    setDateRange(buildRange(value));
    setPage(1);
  };

  const handleDateRangeChange = (next: null | [Dayjs | null, Dayjs | null]) => {
    if (!next?.[0] || !next?.[1]) return;
    setShortcut("custom");
    setDateRange([next[0], next[1]]);
    setPage(1);
  };

  const handleRefresh = () => {
    fetchBatches();
    fetchWorkers();
    fetchDetail();
  };

  const intentColumns: ColumnsType<CronDispatchIntentItem> = [
    { title: "Intent", dataIndex: "id", width: 76 },
    { title: "角色", dataIndex: "intent_role", width: 72 },
    {
      title: "租户 / 任务",
      dataIndex: "job_id",
      width: 210,
      render: (_, record) => (
        <div className={styles.stackCell}>
          <strong>{record.tenant_id || "-"}</strong>
          <Tooltip title={record.job_id || "-"} placement="topLeft">
            <span>{record.job_id || "-"}</span>
          </Tooltip>
        </div>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 88,
      render: renderStatus,
    },
    { title: "尝试", dataIndex: "attempt_count", width: 64 },
    {
      title: "Due",
      dataIndex: "due_at",
      width: 148,
      render: formatDateTime,
    },
    {
      title: "结果 / 错误",
      dataIndex: "error_message",
      width: 200,
      render: (value: string) => (
        <Tooltip title={value || "-"}>
          <span className={styles.errorText}>{value || "-"}</span>
        </Tooltip>
      ),
    },
  ];

  const currentCapacity = workers?.current_capacity || [];
  const capacityEvents = workers?.capacity_events || [];
  const policies = workers?.policies || [];

  if (!canView) {
    return (
      <div className={styles.page}>
        <Alert type="warning" showIcon message="仅管理员可访问批调度监控页面" />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>批调度监控</h1>
          <p>
            按当前渠道监控 batch、intent、调度事件、模型策略和 worker 变动。
          </p>
        </div>
        <Space wrap>
          <Tag color="blue" className={styles.sourceTag}>
            当前渠道 {sourceId}
          </Tag>
          <Button icon={<RefreshCw size={16} />} onClick={handleRefresh}>
            刷新
          </Button>
        </Space>
      </header>

      <section className={styles.toolbar}>
        <Segmented
          value={shortcut}
          options={DATE_SHORTCUTS}
          onChange={(value) => handleShortcutChange(value as DateShortcutKey)}
        />
        <RangePicker
          showTime
          allowClear={false}
          value={dateRange}
          onChange={handleDateRangeChange}
          className={styles.rangePicker}
        />
        <Select
          value={status}
          options={STATUS_OPTIONS}
          className={styles.statusSelect}
          onChange={(value) => {
            setStatus(value);
            setPage(1);
          }}
        />
      </section>

      <section className={styles.summaryStrip} aria-label="批调度概览">
        <SummaryMetric
          title="Batch 总数"
          value={formatNumber(stats.total_batches)}
          hint={`${stats.running_batches} 个运行中`}
        />
        <SummaryMetric
          title="Intent 总数"
          value={formatNumber(stats.total_intents)}
          hint={`${stats.pending_intents} 个等待中`}
        />
        <SummaryMetric
          title="运行中 Batch"
          value={formatNumber(stats.running_batches)}
          hint="当前时间范围"
        />
        <SummaryMetric
          title="Intent 完成率"
          value={formatPercent(stats.completed_intents, stats.total_intents)}
          hint={`${stats.completed_intents}/${stats.total_intents}`}
        />
        <SummaryMetric
          title="失败 Intent"
          value={formatNumber(stats.failed_intents)}
          hint={`${stats.failed_batches} 个失败 Batch`}
          danger={stats.failed_intents > 0}
        />
        <SummaryMetric
          title="有效 Worker"
          value={formatNumber(
            currentCapacity.reduce(
              (sum, item) => sum + item.effective_workers,
              0,
            ),
          )}
          hint={`${policies.length} 个模型策略`}
        />
      </section>

      <section className={styles.workspace}>
        <article className={styles.batchPane}>
          <div className={styles.paneHeader}>
            <div>
              <h2>所有 Batch</h2>
              <span>按计划执行时间倒序展示</span>
            </div>
            <strong>
              {filteredBatches.length} / {batches.length} 当前页
            </strong>
          </div>
          <Input
            allowClear
            aria-label="筛选当前页 Batch"
            placeholder="筛选当前页任务、Batch ID、父任务或模型"
            value={batchQuery}
            onChange={(event) => setBatchQuery(event.target.value)}
          />
          <div className={styles.batchListHeader} aria-hidden="true">
            <span>任务 / Batch</span>
            <span>计划 / 回调</span>
            <span>状态 / 进度</span>
          </div>
          <Spin spinning={batchLoading} wrapperClassName={styles.batchListSpin}>
            <div
              className={styles.batchList}
              role="region"
              aria-label="Batch 列表"
              tabIndex={0}
            >
              {filteredBatches.map((batch) => {
                const total = Math.max(batch.total_count, 1);
                const finished = batch.completed_count + batch.failed_count;
                return (
                  <button
                    type="button"
                    key={batch.batch_id}
                    className={`${styles.batchRow} ${
                      batch.batch_id === selectedBatchId
                        ? styles.batchRowSelected
                        : ""
                    }`}
                    onClick={() => setSelectedBatchId(batch.batch_id)}
                  >
                    <span className={styles.batchIdentity}>
                      <strong>
                        {batch.parent_external_job_id || batch.parent_job_id}
                      </strong>
                      <Tooltip title={batch.batch_id} placement="topLeft">
                        <em>{shortBatchId(batch.batch_id)}</em>
                      </Tooltip>
                      <small>{batch.parent_job_id}</small>
                    </span>
                    <span className={styles.batchTiming}>
                      <strong>{formatDateTime(batch.scheduled_fire_at)}</strong>
                      <em>回调 {formatDateTime(batch.callback_received_at)}</em>
                      <small>
                        {batch.provider_id} / {batch.model_id}
                      </small>
                    </span>
                    <span className={styles.batchProgress}>
                      {renderStatus(batch.status)}
                      <strong>
                        {finished}/{batch.total_count}
                      </strong>
                      <Progress
                        percent={Math.min(
                          100,
                          Math.round((finished / total) * 100),
                        )}
                        showInfo={false}
                        size="small"
                        status={batch.failed_count > 0 ? "exception" : "normal"}
                      />
                    </span>
                  </button>
                );
              })}
              {!batchLoading && !filteredBatches.length ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="当前页无匹配 Batch"
                />
              ) : null}
            </div>
          </Spin>
          <div className={styles.batchPagination}>
            <Pagination
              current={page}
              pageSize={pageSize}
              total={batchTotal}
              showSizeChanger
              showLessItems
              size="small"
              onChange={(nextPage, nextPageSize) => {
                setPage(nextPage);
                setPageSize(nextPageSize);
              }}
              showTotal={(total) => `共 ${total} 个`}
            />
          </div>
        </article>

        <article className={styles.detailPane}>
          <Spin spinning={detailLoading} wrapperClassName={styles.detailSpin}>
            {selectedDetail ? (
              <div className={styles.detailContent}>
                <div className={styles.detailHead}>
                  <div>
                    <h2>
                      {selectedDetail.batch.parent_external_job_id ||
                        selectedDetail.batch.parent_job_id}
                    </h2>
                    <p>
                      <Tooltip
                        title={selectedDetail.batch.batch_id}
                        placement="topLeft"
                      >
                        <span className={styles.mono}>
                          {shortBatchId(selectedDetail.batch.batch_id)}
                        </span>
                      </Tooltip>
                      <span>
                        {selectedDetail.batch.provider_id} /{" "}
                        {selectedDetail.batch.model_id}
                      </span>
                    </p>
                  </div>
                  {renderStatus(selectedDetail.batch.status)}
                </div>
                <div className={styles.detailMeta}>
                  <span>父任务 {selectedDetail.batch.parent_job_id}</span>
                  <span>
                    计划{" "}
                    {formatDateTime(selectedDetail.batch.scheduled_fire_at)}
                  </span>
                  <span>
                    回调{" "}
                    {formatDateTime(selectedDetail.batch.callback_received_at)}
                  </span>
                  <Tooltip title={selectedDetail.batch.lock_owner || "-"}>
                    <span>Owner {selectedDetail.batch.lock_owner || "-"}</span>
                  </Tooltip>
                </div>
                <Tabs
                  activeKey={detailTab}
                  onChange={setDetailTab}
                  destroyOnHidden
                  className={styles.detailTabs}
                  items={[
                    {
                      key: "intents",
                      label: `Intent (${selectedDetail.intent_total})`,
                      children: (
                        <div className={styles.intentTab}>
                          <div className={styles.intentFilters}>
                            <Input
                              allowClear
                              aria-label="筛选 Intent"
                              placeholder="筛选 Intent、租户、任务或错误"
                              value={intentQuery}
                              onChange={(event) =>
                                setIntentQuery(event.target.value)
                              }
                            />
                            <div className={styles.selectFilter}>
                              <label htmlFor="intent-role-filter">
                                Intent 角色
                              </label>
                              <Select
                                id="intent-role-filter"
                                value={intentRole}
                                options={INTENT_ROLE_OPTIONS}
                                onChange={setIntentRole}
                              />
                            </div>
                            <div className={styles.selectFilter}>
                              <label htmlFor="intent-status-filter">
                                Intent 状态
                              </label>
                              <Select
                                id="intent-status-filter"
                                value={intentStatus}
                                options={INTENT_STATUS_OPTIONS}
                                onChange={setIntentStatus}
                              />
                            </div>
                            <strong>
                              {filteredIntents.length} /{" "}
                              {selectedDetail.intents.length} 条
                            </strong>
                            {selectedDetail.intent_total >
                            selectedDetail.intents.length ? (
                              <span className={styles.truncatedNotice}>
                                已加载前 {selectedDetail.intents.length} 条，共{" "}
                                {selectedDetail.intent_total} 条
                              </span>
                            ) : null}
                          </div>
                          <Table
                            rowKey="id"
                            columns={intentColumns}
                            dataSource={filteredIntents}
                            size="small"
                            tableLayout="fixed"
                            scroll={{ x: 858, y: 292 }}
                            pagination={false}
                          />
                        </div>
                      ),
                    },
                    {
                      key: "events",
                      label: `调度事件 (${selectedDetail.events.length})`,
                      children: <EventList events={selectedDetail.events} />,
                    },
                  ]}
                />
              </div>
            ) : (
              <div className={styles.detailEmpty}>
                <Empty description="请选择一个 Batch" />
              </div>
            )}
          </Spin>
        </article>
      </section>

      <section className={styles.strategyGrid}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <h2>Source 维度模型策略</h2>
              <span>当前渠道下所有 provider/model 的策略配置</span>
            </div>
            <ShieldCheck size={18} />
          </div>
          <Spin spinning={workerLoading}>
            {policies.length ? (
              <div className={styles.policyGridList}>
                {policies.map((policy) => (
                  <PolicyCard
                    key={`${policy.source_id}:${policy.provider_id}:${policy.model_id}`}
                    policy={policy}
                  />
                ))}
              </div>
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无模型策略"
              />
            )}
          </Spin>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <h2>Worker 变动</h2>
              <span>最近 capacity 快照与当前有效 worker</span>
            </div>
            <Clock3 size={18} />
          </div>
          <Spin spinning={workerLoading}>
            {currentCapacity.length ? (
              <div className={styles.capacityList}>
                {currentCapacity.map((item) => (
                  <CapacityRow key={item.id} item={item} />
                ))}
              </div>
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无 capacity"
              />
            )}
            <CapacityEventHistory items={capacityEvents} />
          </Spin>
        </article>
      </section>
    </div>
  );
}
