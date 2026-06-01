import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  DatePicker,
  Drawer,
  Empty,
  Input,
  Select,
  Space,
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
  AlertTriangle,
  Archive,
  BarChart3,
  Clock3,
  Database,
  FileText,
  HardDriveDownload,
  RefreshCw,
  Search,
  ShieldCheck,
  Timer,
  UserCheck,
  Users,
  UserX,
} from "lucide-react";
import { dreamLogsApi } from "../../../api/modules/dreamLogs";
import type {
  ArchiveAdminAuditRecord,
  ArchiveItem,
  ArchiveReportResponse,
  DreamLogReportBbkBucket,
  DreamLogReportParams,
  DreamLogReportRecord,
  DreamLogReportResponse,
  DreamLogReportStatusBucket,
  DreamLogReportTrendPoint,
  DreamLogReportUserRow,
  ProtectedFileInfo,
} from "../../../api/types/dreamLogs";
import { BBK_ID_MAP, getBbkDisplayName } from "../../../constants/bbk";
import styles from "./index.module.less";

const { RangePicker } = DatePicker;

type DateRange = [Dayjs, Dayjs] | null;
type ActiveTab = "governance" | "files";

interface FilterDraft {
  dateRange: DateRange;
  bbk_id?: string;
  user_search?: string;
  status?: string;
  trigger?: string;
  agent_id?: string;
}

interface KpiConfig {
  key: string;
  label: string;
  value: string;
  accent: string;
  icon: typeof Users;
}

const STATUS_COLORS: Record<string, string> = {
  success: "green",
  failed: "red",
  rollback: "gold",
  unknown: "default",
};

const STATUS_TEXT: Record<string, string> = {
  success: "成功",
  failed: "失败",
  rollback: "已回退",
  unknown: "未知",
};

const TRIGGER_TEXT: Record<string, string> = {
  manual: "手动",
  cron: "定时",
};

const AUDIT_OPERATION_TEXT: Record<string, string> = {
  purge_archive: "手动清理",
  auto_purge_archive: "自动清理",
};

const AUDIT_STATUS_COLORS: Record<string, string> = {
  success: "green",
  failed: "red",
  partial_success: "gold",
};

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value || 0);
}

function formatBytes(value: number): string {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(2)} MB`;
}

function formatDuration(value: number): string {
  if (!value) return "0ms";
  if (value < 1000) return `${value}ms`;
  if (value < 60000) return `${(value / 1000).toFixed(1)}s`;
  return `${(value / 60000).toFixed(1)}min`;
}

function formatPercent(value: number): string {
  const rounded = Number(value || 0);
  return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(2)}%`;
}

function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  const parsed = dayjs(value);
  return parsed.isValid() ? parsed.format("YYYY-MM-DD HH:mm") : value;
}

function buildParams(
  draft: FilterDraft,
  page: number,
  pageSize: number,
): DreamLogReportParams {
  return {
    start_time: draft.dateRange?.[0]?.format("YYYY-MM-DD"),
    end_time: draft.dateRange?.[1]?.format("YYYY-MM-DD"),
    bbk_id: draft.bbk_id,
    user_search: draft.user_search?.trim() || undefined,
    status: draft.status,
    trigger: draft.trigger,
    agent_id: draft.agent_id?.trim() || undefined,
    page,
    page_size: pageSize,
  };
}

function KpiCard({ item }: { item: KpiConfig }) {
  const Icon = item.icon;
  return (
    <div
      className={styles.kpiCard}
      style={{ borderTopColor: item.accent }}
      data-testid={`governance-kpi-${item.key}`}
    >
      <div className={styles.kpiHeader}>
        <span className={styles.kpiIcon} style={{ color: item.accent }}>
          <Icon size={18} />
        </span>
        <span className={styles.kpiLabel}>{item.label}</span>
      </div>
      <div className={styles.kpiValue}>{item.value}</div>
    </div>
  );
}

function TrendChart({ data }: { data: DreamLogReportTrendPoint[] }) {
  const maxValue = Math.max(...data.map((item) => item.executions), 1);
  if (!data.length) {
    return (
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无趋势数据" />
    );
  }
  return (
    <div className={styles.trendChart}>
      {data.map((item) => (
        <Tooltip
          key={item.date}
          title={`执行 ${item.executions} 次，成功 ${item.success_count} 次`}
        >
          <div className={styles.trendItem}>
            <div className={styles.trendTrack}>
              <div
                className={styles.trendBar}
                style={{
                  height: `${Math.max((item.executions / maxValue) * 100, 8)}%`,
                }}
              />
            </div>
            <span className={styles.trendLabel}>
              {dayjs(item.date).format("MM-DD")}
            </span>
          </div>
        </Tooltip>
      ))}
    </div>
  );
}

function StatusChart({ data }: { data: DreamLogReportStatusBucket[] }) {
  const total = Math.max(
    data.reduce((sum, item) => sum + item.count, 0),
    1,
  );
  if (!data.length) {
    return (
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无状态数据" />
    );
  }
  return (
    <div className={styles.distributionList}>
      {data.map((item) => (
        <div key={item.status} className={styles.distributionRow}>
          <span className={styles.distributionName}>
            {STATUS_TEXT[item.status] || item.status}
          </span>
          <div className={styles.distributionTrack}>
            <div
              className={styles.distributionBar}
              style={{ width: `${(item.count / total) * 100}%` }}
            />
          </div>
          <span className={styles.distributionValue}>{item.count}</span>
        </div>
      ))}
    </div>
  );
}

function BbkChart({ data }: { data: DreamLogReportBbkBucket[] }) {
  const maxValue = Math.max(...data.map((item) => item.executions), 1);
  if (!data.length) {
    return (
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无机构数据" />
    );
  }
  return (
    <div className={styles.distributionList}>
      {data.map((item) => (
        <div key={item.bbk_id} className={styles.distributionRow}>
          <span className={styles.distributionName}>
            {getBbkDisplayName(item.bbk_id)}
          </span>
          <div className={styles.distributionTrack}>
            <div
              className={styles.bbkBar}
              style={{ width: `${(item.executions / maxValue) * 100}%` }}
            />
          </div>
          <span className={styles.distributionValue}>{item.executions}</span>
        </div>
      ))}
    </div>
  );
}

export default function ContinuousGovernancePage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("governance");
  const [draft, setDraft] = useState<FilterDraft>({
    dateRange: [dayjs().subtract(30, "day"), dayjs()],
  });
  const [query, setQuery] = useState<DreamLogReportParams>(() =>
    buildParams(
      {
        dateRange: [dayjs().subtract(30, "day"), dayjs()],
      },
      1,
      20,
    ),
  );
  const [report, setReport] = useState<DreamLogReportResponse | null>(null);
  const [archiveReport, setArchiveReport] =
    useState<ArchiveReportResponse | null>(null);
  const [archiveItems, setArchiveItems] = useState<ArchiveItem[]>([]);
  const [archiveTotal, setArchiveTotal] = useState(0);
  const [protectedFiles, setProtectedFiles] = useState<ProtectedFileInfo[]>([]);
  const [protectedTotal, setProtectedTotal] = useState(0);
  const [adminAudits, setAdminAudits] = useState<ArchiveAdminAuditRecord[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [archiveLoaded, setArchiveLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedUser, setSelectedUser] =
    useState<DreamLogReportUserRow | null>(null);
  const [recordLoading, setRecordLoading] = useState(false);
  const [records, setRecords] = useState<DreamLogReportRecord[]>([]);
  const [recordsTotal, setRecordsTotal] = useState(0);
  const [recordsPage, setRecordsPage] = useState(1);
  const [recordsPageSize, setRecordsPageSize] = useState(10);

  const fetchReport = useCallback(async (params: DreamLogReportParams) => {
    setLoading(true);
    try {
      const data = await dreamLogsApi.report(params);
      setReport(data);
    } catch (error) {
      console.error("Failed to fetch continuous governance report:", error);
      message.error("持续治理分析加载失败");
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchArchiveData = useCallback(async () => {
    setArchiveLoading(true);
    try {
      const [reportData, itemsData, protectedData, auditsData] =
        await Promise.all([
          dreamLogsApi.archiveReport(),
          dreamLogsApi.listArchiveItems({ page_size: 100 }),
          dreamLogsApi.listProtectedFiles({ page_size: 100 }),
          dreamLogsApi.listArchiveAdminAudits({ page_size: 100 }),
        ]);
      setArchiveReport(reportData);
      setArchiveItems(itemsData.items || []);
      setArchiveTotal(itemsData.total || 0);
      setProtectedFiles(protectedData.items || []);
      setProtectedTotal(protectedData.total || 0);
      setAdminAudits(auditsData.items || []);
      setAuditTotal(auditsData.total || 0);
      setArchiveLoaded(true);
    } catch (error) {
      console.error("Failed to fetch file governance report:", error);
      message.error("文件清理与归档加载失败");
      setArchiveReport(null);
      setArchiveItems([]);
      setArchiveTotal(0);
      setProtectedFiles([]);
      setProtectedTotal(0);
      setAdminAudits([]);
      setAuditTotal(0);
    } finally {
      setArchiveLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchReport(query);
  }, [fetchReport, query]);

  useEffect(() => {
    if (activeTab === "files" && !archiveLoaded) {
      void fetchArchiveData();
    }
  }, [activeTab, archiveLoaded, fetchArchiveData]);

  const loadUserRecords = useCallback(
    async (user: DreamLogReportUserRow, page: number, pageSize: number) => {
      setRecordLoading(true);
      try {
        const data = await dreamLogsApi.reportUserRecords(user.user_id, {
          ...query,
          page,
          page_size: pageSize,
        });
        setRecords(data.records || []);
        setRecordsTotal(data.total || 0);
        setRecordsPage(data.page || page);
        setRecordsPageSize(data.page_size || pageSize);
      } catch (error) {
        console.error("Failed to fetch governance records:", error);
        message.error("用户治理记录加载失败");
      } finally {
        setRecordLoading(false);
      }
    },
    [query],
  );

  const kpis = useMemo<KpiConfig[]>(() => {
    const summary = report?.summary;
    return [
      {
        key: "covered_users",
        label: "覆盖用户",
        value: formatNumber(summary?.covered_users ?? 0),
        accent: "#2563eb",
        icon: Users,
      },
      {
        key: "governed_users",
        label: "已治理用户",
        value: formatNumber(summary?.governed_users ?? 0),
        accent: "#16a34a",
        icon: UserCheck,
      },
      {
        key: "ungoverned_users",
        label: "未治理用户",
        value: formatNumber(summary?.ungoverned_users ?? 0),
        accent: "#f97316",
        icon: UserX,
      },
      {
        key: "total_executions",
        label: "总执行次数",
        value: formatNumber(summary?.total_executions ?? 0),
        accent: "#0f766e",
        icon: Database,
      },
      {
        key: "success_rate",
        label: "成功率",
        value: formatPercent(summary?.success_rate ?? 0),
        accent: "#0891b2",
        icon: BarChart3,
      },
      {
        key: "failed_count",
        label: "失败次数",
        value: formatNumber(summary?.failed_count ?? 0),
        accent: "#dc2626",
        icon: AlertTriangle,
      },
      {
        key: "total_files_changed",
        label: "变更文件数",
        value: formatNumber(summary?.total_files_changed ?? 0),
        accent: "#7c3aed",
        icon: FileText,
      },
      {
        key: "total_size_saved",
        label: "节省空间",
        value: formatBytes(summary?.total_size_saved ?? 0),
        accent: "#4f46e5",
        icon: HardDriveDownload,
      },
      {
        key: "avg_duration_ms",
        label: "平均耗时",
        value: formatDuration(summary?.avg_duration_ms ?? 0),
        accent: "#ca8a04",
        icon: Timer,
      },
      {
        key: "last_execution",
        label: "最近治理时间",
        value: formatDateTime(summary?.last_execution),
        accent: "#334155",
        icon: Clock3,
      },
    ];
  }, [report]);

  const archiveKpis = useMemo<KpiConfig[]>(() => {
    const summary = archiveReport?.summary;
    return [
      {
        key: "archive_files",
        label: "归档文件",
        value: formatNumber(summary?.archived_files ?? 0),
        accent: "#0d9488",
        icon: Archive,
      },
      {
        key: "protected_files",
        label: "保护文件",
        value: formatNumber(summary?.protected_files ?? 0),
        accent: "#0284c7",
        icon: ShieldCheck,
      },
      {
        key: "pending_purge_files",
        label: "待清理归档",
        value: formatNumber(summary?.pending_purge_files ?? 0),
        accent: "#ea580c",
        icon: AlertTriangle,
      },
      {
        key: "purged_size_bytes",
        label: "归档释放空间",
        value: formatBytes(summary?.purged_size_bytes ?? 0),
        accent: "#059669",
        icon: HardDriveDownload,
      },
    ];
  }, [archiveReport]);

  const userColumns: ColumnsType<DreamLogReportUserRow> = [
    {
      title: "用户 ID",
      dataIndex: "user_id",
      key: "user_id",
      fixed: "left",
      width: 160,
    },
    {
      title: "姓名",
      dataIndex: "user_name",
      key: "user_name",
      width: 120,
      render: (value) => value || "-",
    },
    {
      title: "机构",
      dataIndex: "bbk_id",
      key: "bbk_id",
      width: 150,
      render: (value) => getBbkDisplayName(value),
    },
    {
      title: "Agent",
      dataIndex: "agents",
      key: "agents",
      width: 150,
      render: (agents: string[]) => (agents.length ? agents.join(", ") : "-"),
    },
    {
      title: "执行次数",
      dataIndex: "executions",
      key: "executions",
      width: 100,
    },
    {
      title: "成功率",
      dataIndex: "success_rate",
      key: "success_rate",
      width: 100,
      render: (value: number) => formatPercent(value),
    },
    {
      title: "失败次数",
      dataIndex: "failed_count",
      key: "failed_count",
      width: 100,
    },
    {
      title: "文件数",
      dataIndex: "total_files_changed",
      key: "total_files_changed",
      width: 100,
    },
    {
      title: "节省空间",
      dataIndex: "total_size_saved",
      key: "total_size_saved",
      width: 110,
      render: (value: number) => formatBytes(value),
    },
    {
      title: "最近治理",
      dataIndex: "last_execution",
      key: "last_execution",
      width: 160,
      render: (value) => formatDateTime(value),
    },
    {
      title: "最新异常",
      dataIndex: "latest_error",
      key: "latest_error",
      width: 180,
      ellipsis: true,
      render: (value) =>
        value ? (
          <Tooltip title={value}>
            <span className={styles.errorText}>{value}</span>
          </Tooltip>
        ) : (
          "-"
        ),
    },
    {
      title: "操作",
      key: "actions",
      fixed: "right",
      width: 90,
      render: (_, record) => (
        <Button
          type="link"
          size="small"
          aria-label={`查看 ${record.user_id}`}
          onClick={() => {
            setSelectedUser(record);
            setDrawerOpen(true);
            setRecords([]);
            void loadUserRecords(record, 1, 10);
          }}
        >
          查看
        </Button>
      ),
    },
  ];

  const recordColumns: ColumnsType<DreamLogReportRecord> = [
    {
      title: "任务 ID",
      dataIndex: "id",
      key: "id",
      width: 160,
    },
    {
      title: "时间",
      dataIndex: "timestamp",
      key: "timestamp",
      width: 160,
      render: (value) => formatDateTime(value),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 90,
      render: (value: string) => (
        <Tag color={STATUS_COLORS[value] || "default"}>
          {STATUS_TEXT[value] || value}
        </Tag>
      ),
    },
    {
      title: "触发方式",
      dataIndex: "trigger",
      key: "trigger",
      width: 100,
      render: (value: string) => TRIGGER_TEXT[value] || value || "-",
    },
    {
      title: "Agent",
      dataIndex: "agent_id",
      key: "agent_id",
      width: 110,
    },
    {
      title: "文件数",
      dataIndex: "total_files_changed",
      key: "total_files_changed",
      width: 90,
    },
    {
      title: "节省空间",
      dataIndex: "total_size_saved",
      key: "total_size_saved",
      width: 110,
      render: (value: number) => formatBytes(value),
    },
    {
      title: "耗时",
      dataIndex: "duration_ms",
      key: "duration_ms",
      width: 100,
      render: (value: number) => formatDuration(value),
    },
    {
      title: "异常",
      dataIndex: "error",
      key: "error",
      width: 180,
      render: (value) =>
        value ? <span className={styles.errorText}>{value}</span> : "-",
    },
  ];

  const archiveColumns: ColumnsType<ArchiveItem> = [
    {
      title: "目标用户",
      dataIndex: "target_user_id",
      key: "target_user_id",
      width: 120,
      render: (value) => value || "-",
    },
    {
      title: "Agent",
      dataIndex: "target_agent_id",
      key: "target_agent_id",
      width: 100,
      render: (value) => value || "-",
    },
    {
      title: "原路径",
      dataIndex: "original_path",
      key: "original_path",
      width: 260,
      render: (value) => <span className={styles.pathText}>{value}</span>,
    },
    {
      title: "大小",
      dataIndex: "size_bytes",
      key: "size_bytes",
      width: 110,
      render: (value: number) => formatBytes(value),
    },
    {
      title: "归档时间",
      dataIndex: "archived_at",
      key: "archived_at",
      width: 160,
      render: (value) => formatDateTime(value),
    },
    {
      title: "归档人",
      dataIndex: "archived_by",
      key: "archived_by",
      width: 120,
      render: (value) => value || "-",
    },
    {
      title: "状态",
      dataIndex: "expired",
      key: "expired",
      width: 100,
      render: (expired: boolean) =>
        expired ? <Tag color="orange">待清理</Tag> : <Tag color="green">可恢复</Tag>,
    },
  ];

  const protectedColumns: ColumnsType<ProtectedFileInfo> = [
    {
      title: "目标用户",
      dataIndex: "target_user_id",
      key: "target_user_id",
      width: 120,
    },
    {
      title: "Agent",
      dataIndex: "target_agent_id",
      key: "target_agent_id",
      width: 100,
    },
    {
      title: "路径",
      dataIndex: "path",
      key: "path",
      width: 280,
      render: (value) => <span className={styles.pathText}>{value}</span>,
    },
    {
      title: "保护时间",
      dataIndex: "protected_at",
      key: "protected_at",
      width: 160,
      render: (value) => formatDateTime(value),
    },
    {
      title: "保护人",
      dataIndex: "protected_by",
      key: "protected_by",
      width: 120,
      render: (value) => value || "-",
    },
    {
      title: "原因",
      dataIndex: "reason",
      key: "reason",
      width: 160,
      render: (value) => value || "-",
    },
    {
      title: "存在状态",
      dataIndex: "exists",
      key: "exists",
      width: 110,
      render: (exists: boolean) =>
        exists ? <Tag color="green">存在</Tag> : <Tag color="orange">缺失</Tag>,
    },
    {
      title: "大小",
      dataIndex: "size_bytes",
      key: "size_bytes",
      width: 110,
      render: (value?: number | null) => (value ? formatBytes(value) : "-"),
    },
  ];

  const auditColumns: ColumnsType<ArchiveAdminAuditRecord> = [
    {
      title: "事件 ID",
      dataIndex: "event_id",
      key: "event_id",
      width: 160,
      render: (value) => <span className={styles.pathText}>{value}</span>,
    },
    {
      title: "操作时间",
      dataIndex: "timestamp",
      key: "timestamp",
      width: 160,
      render: (value) => formatDateTime(value),
    },
    {
      title: "管理员",
      dataIndex: "actor_user_id",
      key: "actor_user_id",
      width: 120,
    },
    {
      title: "目标用户",
      dataIndex: "target_user_id",
      key: "target_user_id",
      width: 120,
    },
    {
      title: "Agent",
      dataIndex: "target_agent_id",
      key: "target_agent_id",
      width: 100,
    },
    {
      title: "类型",
      dataIndex: "operation",
      key: "operation",
      width: 120,
      render: (value: string) => AUDIT_OPERATION_TEXT[value] || value,
    },
    {
      title: "文件数",
      dataIndex: "files_count",
      key: "files_count",
      width: 90,
    },
    {
      title: "释放空间",
      dataIndex: "total_size_bytes",
      key: "total_size_bytes",
      width: 110,
      render: (value: number) => formatBytes(value),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (value: string) => (
        <Tag color={AUDIT_STATUS_COLORS[value] || "default"}>{value}</Tag>
      ),
    },
  ];

  const applyFilters = () => {
    setQuery(buildParams(draft, 1, report?.page_size || 20));
  };

  const resetFilters = () => {
    const nextDraft: FilterDraft = {
      dateRange: [dayjs().subtract(30, "day"), dayjs()],
    };
    setDraft(nextDraft);
    setQuery(buildParams(nextDraft, 1, 20));
  };

  const refreshActiveTab = () => {
    if (activeTab === "files") {
      void fetchArchiveData();
      return;
    }
    void fetchReport(query);
  };

  const renderGovernanceTab = () => (
    <>
      <div className={styles.sectionHeader}>
        <div>
          <h3>持续治理分析</h3>
          <p>当前来源内所有可管理用户的持续治理覆盖、成功率和异常情况</p>
        </div>
      </div>

      <div className={styles.filterBar}>
        <RangePicker
          value={draft.dateRange}
          onChange={(dates) => {
            setDraft((prev) => ({
              ...prev,
              dateRange: dates as DateRange,
            }));
          }}
          allowClear
        />
        <Select
          className={styles.filterControl}
          placeholder="机构 BBK"
          value={draft.bbk_id}
          options={BBK_ID_MAP}
          onChange={(value) => setDraft((prev) => ({ ...prev, bbk_id: value }))}
          allowClear
          showSearch
        />
        <Input
          className={styles.searchInput}
          placeholder="搜索用户 ID / 姓名"
          prefix={<Search size={15} />}
          value={draft.user_search}
          onChange={(event) =>
            setDraft((prev) => ({
              ...prev,
              user_search: event.target.value,
            }))
          }
          onPressEnter={applyFilters}
          allowClear
        />
        <Select
          className={styles.filterControl}
          placeholder="状态"
          value={draft.status}
          onChange={(value) => setDraft((prev) => ({ ...prev, status: value }))}
          options={[
            { value: "success", label: "成功" },
            { value: "failed", label: "失败" },
            { value: "rollback", label: "已回退" },
          ]}
          allowClear
        />
        <Select
          className={styles.filterControl}
          placeholder="触发方式"
          value={draft.trigger}
          onChange={(value) =>
            setDraft((prev) => ({ ...prev, trigger: value }))
          }
          options={[
            { value: "manual", label: "手动" },
            { value: "cron", label: "定时" },
          ]}
          allowClear
        />
        <Input
          className={styles.agentInput}
          placeholder="Agent"
          value={draft.agent_id}
          onChange={(event) =>
            setDraft((prev) => ({ ...prev, agent_id: event.target.value }))
          }
          onPressEnter={applyFilters}
          allowClear
        />
        <Space>
          <Button type="primary" onClick={applyFilters} loading={loading}>
            查询
          </Button>
          <Button onClick={resetFilters}>重置</Button>
        </Space>
      </div>

      <div className={styles.kpiGrid}>
        {kpis.map((item) => (
          <KpiCard key={item.key} item={item} />
        ))}
      </div>

      <div className={styles.chartGrid}>
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>治理趋势</span>
          </div>
          <TrendChart data={report?.trends || []} />
        </section>
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>状态分布</span>
          </div>
          <StatusChart data={report?.status_distribution || []} />
        </section>
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>机构分布</span>
          </div>
          <BbkChart data={report?.bbk_distribution || []} />
        </section>
      </div>

      <section className={styles.tablePanel}>
        <div className={styles.panelHeader}>
          <span>用户明细</span>
          <span className={styles.panelMeta}>共 {report?.total || 0} 人</span>
        </div>
        <Table
          rowKey="user_id"
          size="middle"
          loading={loading}
          columns={userColumns}
          dataSource={report?.users || []}
          scroll={{ x: 1450 }}
          pagination={{
            current: report?.page || query.page || 1,
            pageSize: report?.page_size || query.page_size || 20,
            total: report?.total || 0,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 人`,
            onChange: (page, pageSize) => {
              setQuery({ ...query, page, page_size: pageSize });
            },
          }}
        />
      </section>
    </>
  );

  const renderFileGovernanceTab = () => (
    <>
      <div className={styles.sectionHeader}>
        <div>
          <h3>文件清理与归档</h3>
          <p>当前来源内可管理用户的归档、保护文件和清理审计情况</p>
        </div>
      </div>

      <Alert
        className={styles.readonlyHint}
        type="info"
        showIcon
        message="只读分析"
        description="这里仅展示文件清理与归档状态，不提供清理、恢复、归档或取消保护操作。需要处理文件时请进入持续治理工作台。"
      />

      <div className={styles.kpiGrid}>
        {archiveKpis.map((item) => (
          <KpiCard key={item.key} item={item} />
        ))}
      </div>

      <section className={styles.tablePanel}>
        <div className={styles.panelHeader}>
          <span>归档文件</span>
          <span className={styles.panelMeta}>共 {archiveTotal} 个</span>
        </div>
        <Table
          rowKey="id"
          size="middle"
          loading={archiveLoading}
          columns={archiveColumns}
          dataSource={archiveItems}
          scroll={{ x: 970 }}
          pagination={false}
        />
      </section>

      <section className={styles.tablePanel}>
        <div className={styles.panelHeader}>
          <span>保护文件</span>
          <span className={styles.panelMeta}>共 {protectedTotal} 个</span>
        </div>
        <Table
          rowKey={(record) =>
            `${record.target_user_id}:${record.target_agent_id}:${record.path}`
          }
          size="middle"
          loading={archiveLoading}
          columns={protectedColumns}
          dataSource={protectedFiles}
          scroll={{ x: 1160 }}
          pagination={false}
        />
      </section>

      <section className={styles.tablePanel}>
        <div className={styles.panelHeader}>
          <span>清理审计</span>
          <span className={styles.panelMeta}>共 {auditTotal} 条记录</span>
        </div>
        <Table
          rowKey="event_id"
          size="middle"
          loading={archiveLoading}
          columns={auditColumns}
          dataSource={adminAudits}
          scroll={{ x: 1140 }}
          pagination={false}
        />
      </section>
    </>
  );

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h2>质量工程看板</h2>
          <p>面向当前来源的持续治理质量与文件清理归档分析</p>
        </div>
        <Button
          icon={<RefreshCw size={16} />}
          onClick={refreshActiveTab}
          loading={activeTab === "files" ? archiveLoading : loading}
        >
          刷新
        </Button>
      </div>

      <Tabs
        className={styles.tabs}
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as ActiveTab)}
        items={[
          {
            key: "governance",
            label: "持续治理分析",
            children: renderGovernanceTab(),
          },
          {
            key: "files",
            label: "文件清理与归档",
            children: renderFileGovernanceTab(),
          },
        ]}
      />

      <Drawer
        title={
          selectedUser
            ? `${selectedUser.user_name || selectedUser.user_id} 的治理记录`
            : "治理记录"
        }
        width={860}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
      >
        {selectedUser && (
          <Alert
            className={styles.drawerAlert}
            type="info"
            showIcon
            message="只读下钻"
            description="这里展示该用户近期持续治理记录和摘要，不提供批量触发或跨用户回滚操作。"
          />
        )}
        <Table
          rowKey="id"
          size="small"
          loading={recordLoading}
          columns={recordColumns}
          dataSource={records}
          scroll={{ x: 980 }}
          pagination={{
            current: recordsPage,
            pageSize: recordsPageSize,
            total: recordsTotal,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条记录`,
            onChange: (page, pageSize) => {
              if (selectedUser) {
                void loadUserRecords(selectedUser, page, pageSize);
              }
            },
          }}
        />
      </Drawer>
    </div>
  );
}
