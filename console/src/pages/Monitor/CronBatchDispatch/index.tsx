import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Alert,
  Button,
  DatePicker,
  Empty,
  Progress,
  Segmented,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";
import {
  Activity,
  CheckCircle2,
  Clock3,
  Database,
  RefreshCw,
  ServerCog,
  ShieldCheck,
  TimerReset,
  Workflow,
  XCircle,
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
  return <Tag color={statusColor[status] || "default"}>{statusLabel[status] || status}</Tag>;
}

function shortBatchId(batchId: string) {
  return batchId.startsWith("cron:") ? batchId.slice(5) : batchId;
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

function jsonSummary(value: Record<string, unknown> | null) {
  if (!value) return "-";
  const text = JSON.stringify(value);
  return text.length > 96 ? `${text.slice(0, 96)}...` : text;
}

function SummaryCard({
  title,
  value,
  hint,
  tone,
  icon,
}: {
  title: string;
  value: string;
  hint: string;
  tone: "blue" | "green" | "orange" | "red" | "slate";
  icon: ReactNode;
}) {
  return (
    <article className={`${styles.summaryCard} ${styles[tone]}`}>
      <div className={styles.summaryIcon}>{icon}</div>
      <div>
        <span>{title}</span>
        <strong>{value}</strong>
        <em>{hint}</em>
      </div>
    </article>
  );
}

function PolicyCard({ policy }: { policy: CronDispatchPolicyItem }) {
  const strategy = policy.strategy || {};
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
          {String(strategy.min_workers ?? "-")} / {String(strategy.baseline_workers ?? "-")} /{" "}
          {String(strategy.max_workers ?? "-")}
        </strong>
        <span>调整间隔</span>
        <strong>{String(strategy.adjust_interval_seconds ?? "-")}s</strong>
        <span>反馈窗口</span>
        <strong>{String(strategy.feedback_window_seconds ?? "-")}s</strong>
      </div>
      <Tooltip title={jsonSummary(policy.strategy_schedule)} placement="topLeft">
        <div className={styles.policyJson}>schedule={jsonSummary(policy.strategy_schedule)}</div>
      </Tooltip>
      <Tooltip title={jsonSummary((strategy.error_rate_rules as Record<string, unknown>) || null)} placement="topLeft">
        <div className={styles.policyJson}>
          rules={jsonSummary((strategy.error_rate_rules as Record<string, unknown>) || null)}
        </div>
      </Tooltip>
    </article>
  );
}

function CapacityRow({ item }: { item: CronDispatchCapacityItem }) {
  const denominator = Math.max(item.max_workers || item.effective_workers || 1, 1);
  const percent = Math.min(100, Math.round((item.effective_workers / denominator) * 100));
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

function EventList({ events }: { events: CronDispatchEventItem[] }) {
  if (!events.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无调度事件" />;
  }
  return (
    <div className={styles.eventList}>
      {events.map((event) => (
        <div key={event.id} className={styles.eventItem}>
          <span>{formatDateTime(event.created_at)}</span>
          <strong>{event.event_type}</strong>
          <p>
            worker={event.worker_id || "-"} · intent={event.intent_id || "-"} · job=
            {event.job_id || "-"}
          </p>
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
  const [workers, setWorkers] = useState<CronDispatchWorkersResponse | null>(null);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [detail, setDetail] = useState<CronDispatchBatchDetailResponse | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [workerLoading, setWorkerLoading] = useState(false);

  const filters = useMemo(
    () => buildDateFilters(dateRange, status),
    [dateRange, status],
  );

  const fetchBatches = useCallback(async () => {
    if (!canView) return;
    setBatchLoading(true);
    try {
      const response = await monitorApi.getCronDispatchBatches(
        page,
        pageSize,
        filters,
      );
      setBatches(response.items);
      setBatchTotal(response.total);
      setStats(response.stats);
      setSelectedBatchId((current) => {
        if (response.items.some((item) => item.batch_id === current)) {
          return current;
        }
        return response.items[0]?.batch_id || "";
      });
    } catch (error) {
      console.error("Failed to fetch cron dispatch batches:", error);
      message.error("批调度 batch 加载失败");
      setBatches([]);
      setBatchTotal(0);
    } finally {
      setBatchLoading(false);
    }
  }, [canView, filters, page, pageSize]);

  const fetchWorkers = useCallback(async () => {
    if (!canView) return;
    setWorkerLoading(true);
    try {
      const response = await monitorApi.getCronDispatchWorkers({
        start_time: filters.start_time,
        end_time: filters.end_time,
      });
      setWorkers(response);
    } catch (error) {
      console.error("Failed to fetch cron dispatch workers:", error);
      message.error("批调度 worker 加载失败");
      setWorkers(null);
    } finally {
      setWorkerLoading(false);
    }
  }, [canView, filters.end_time, filters.start_time]);

  const fetchDetail = useCallback(async () => {
    if (!canView || !selectedBatchId) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    try {
      const response = await monitorApi.getCronDispatchBatchDetail(selectedBatchId);
      setDetail(response);
    } catch (error) {
      console.error("Failed to fetch cron dispatch batch detail:", error);
      message.error("批调度详情加载失败");
      setDetail(null);
    } finally {
      setDetailLoading(false);
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

  const batchColumns: ColumnsType<CronDispatchBatchItem> = [
    {
      title: "Batch",
      dataIndex: "batch_id",
      width: 168,
      render: (value: string) => (
        <Tooltip title={value}>
          <span className={styles.mono}>{shortBatchId(value)}</span>
        </Tooltip>
      ),
    },
    {
      title: "父任务",
      dataIndex: "parent_job_id",
      width: 190,
      render: (_, record) => (
        <div className={styles.stackCell}>
          <strong>{record.parent_job_id}</strong>
          <span>{record.parent_external_job_id || "-"}</span>
        </div>
      ),
    },
    {
      title: "计划/回调时间",
      dataIndex: "scheduled_fire_at",
      width: 210,
      render: (_, record) => (
        <div className={styles.stackCell}>
          <strong>{formatDateTime(record.scheduled_fire_at)}</strong>
          <span>callback {formatDateTime(record.callback_received_at)}</span>
        </div>
      ),
    },
    {
      title: "模型",
      dataIndex: "model_id",
      width: 190,
      render: (_, record) => (
        <div className={styles.stackCell}>
          <strong>{record.provider_id}</strong>
          <span>{record.model_id}</span>
        </div>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 92,
      render: renderStatus,
    },
    {
      title: "进度",
      key: "progress",
      width: 180,
      render: (_, record) => {
        const done = record.completed_count + record.failed_count;
        const percent = record.total_count
          ? Math.round((done / record.total_count) * 100)
          : 0;
        return (
          <div className={styles.progressCell}>
            <span>
              {done}/{record.total_count}
            </span>
            <Progress percent={percent} size="small" />
          </div>
        );
      },
    },
    {
      title: "Owner",
      dataIndex: "lock_owner",
      width: 180,
      render: (value: string) => (
        <Tooltip title={value || "-"}>
          <span className={styles.ownerText}>{value || "-"}</span>
        </Tooltip>
      ),
    },
  ];

  const intentColumns: ColumnsType<CronDispatchIntentItem> = [
    { title: "Intent", dataIndex: "id", width: 90 },
    { title: "角色", dataIndex: "intent_role", width: 80 },
    { title: "租户", dataIndex: "tenant_id", width: 120 },
    { title: "任务", dataIndex: "job_id", width: 160 },
    {
      title: "状态",
      dataIndex: "status",
      width: 96,
      render: renderStatus,
    },
    { title: "尝试", dataIndex: "attempt_count", width: 72 },
    {
      title: "Due",
      dataIndex: "due_at",
      width: 168,
      render: formatDateTime,
    },
    {
      title: "Worker",
      dataIndex: "lock_owner",
      width: 180,
      render: (value: string) => (
        <Tooltip title={value || "-"}>
          <span className={styles.ownerText}>{value || "-"}</span>
        </Tooltip>
      ),
    },
    {
      title: "错误",
      dataIndex: "error_message",
      width: 240,
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
        <Alert
          type="warning"
          showIcon
          message="仅管理员可访问批调度监控页面"
        />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>批调度监控</h1>
          <p>按当前渠道监控 batch、intent、调度事件、模型策略和 worker 变动。</p>
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

      <section className={styles.summaryGrid}>
        <SummaryCard
          title="Batch 数"
          value={formatNumber(stats.total_batches)}
          hint={`${stats.running_batches} 个运行中`}
          tone="blue"
          icon={<Workflow size={22} />}
        />
        <SummaryCard
          title="Intent 总数"
          value={formatNumber(stats.total_intents)}
          hint={`${stats.pending_intents} 个未完成`}
          tone="slate"
          icon={<Database size={22} />}
        />
        <SummaryCard
          title="完成率"
          value={formatPercent(stats.completed_intents, stats.total_intents)}
          hint={`${stats.completed_intents}/${stats.total_intents}`}
          tone="green"
          icon={<CheckCircle2 size={22} />}
        />
        <SummaryCard
          title="失败 Intent"
          value={formatNumber(stats.failed_intents)}
          hint={`${stats.failed_batches} 个失败 batch`}
          tone={stats.failed_intents > 0 ? "red" : "green"}
          icon={<XCircle size={22} />}
        />
        <SummaryCard
          title="当前 Worker"
          value={formatNumber(
            currentCapacity.reduce((sum, item) => sum + item.effective_workers, 0),
          )}
          hint={`${policies.length} 个模型策略`}
          tone="orange"
          icon={<ServerCog size={22} />}
        />
      </section>

      <section className={styles.mainGrid}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <h2>所有 Batch</h2>
              <span>按父任务计划执行时间倒序展示</span>
            </div>
          </div>
          <Table
            rowKey="batch_id"
            loading={batchLoading}
            columns={batchColumns}
            dataSource={batches}
            size="small"
            scroll={{ x: 1180, y: 420 }}
            rowClassName={(record) =>
              record.batch_id === selectedBatchId ? styles.selectedRow : ""
            }
            onRow={(record) => ({
              onClick: () => setSelectedBatchId(record.batch_id),
            })}
            pagination={{
              current: page,
              pageSize,
              total: batchTotal,
              showSizeChanger: true,
              onChange: (nextPage, nextPageSize) => {
                setPage(nextPage);
                setPageSize(nextPageSize);
              },
              showTotal: (total) => `共 ${total} 个 batch`,
            }}
          />
        </article>

        <article className={`${styles.panel} ${styles.detailPanel}`}>
          <Spin spinning={detailLoading}>
            {detail ? (
              <>
                <div className={styles.detailHead}>
                  <div>
                    <h2>{detail.batch.parent_job_id}</h2>
                    <p>
                      <span className={styles.mono}>{detail.batch.batch_id}</span>
                      <span>{detail.batch.provider_id} / {detail.batch.model_id}</span>
                    </p>
                  </div>
                  {renderStatus(detail.batch.status)}
                </div>
                <div className={styles.detailMeta}>
                  <span>计划 {formatDateTime(detail.batch.scheduled_fire_at)}</span>
                  <span>回调 {formatDateTime(detail.batch.callback_received_at)}</span>
                  <span>owner {detail.batch.lock_owner || "-"}</span>
                  <span>intent {detail.intent_total}</span>
                </div>
                <Table
                  rowKey="id"
                  columns={intentColumns}
                  dataSource={detail.intents}
                  size="small"
                  scroll={{ x: 1160, y: 260 }}
                  pagination={false}
                />
                <div className={styles.subSectionTitle}>
                  <Activity size={16} />
                  <span>调度事件</span>
                </div>
                <EventList events={detail.events} />
              </>
            ) : (
              <Empty description="请选择一个 batch" />
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
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无模型策略" />
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
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 capacity" />
            )}
            <div className={styles.subSectionTitle}>
              <TimerReset size={16} />
              <span>最近调整记录</span>
            </div>
            <div className={styles.workerEventList}>
              {capacityEvents.slice(0, 8).map((item) => (
                <div key={item.id} className={styles.workerEvent}>
                  <strong>{item.decision_reason || "-"}</strong>
                  <span>
                    {item.provider_id}/{item.model_id} · {item.previous_workers} →{" "}
                    {item.effective_workers}
                  </span>
                  <em>{formatDateTime(item.created_at)}</em>
                </div>
              ))}
              {!capacityEvents.length ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无调整记录" />
              ) : null}
            </div>
          </Spin>
        </article>
      </section>
    </div>
  );
}
