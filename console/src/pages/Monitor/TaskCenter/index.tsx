import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Drawer,
  Empty,
  Input,
  Pagination,
  Select,
  Spin,
  Table,
  Tag,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { RefreshCw, Search } from "lucide-react";
import {
  monitorApi,
  type AsyncTaskDetailRecord,
  type AsyncTaskRecord,
} from "../../../api/modules/monitor";
import styles from "./index.module.less";

const SERVICE_OPTIONS = [
  { label: "全部服务", value: "" },
  { label: "SWE", value: "swe" },
  { label: "Market", value: "market" },
];

const STATUS_OPTIONS = [
  { label: "全部状态", value: "" },
  { label: "排队中", value: "queued" },
  { label: "运行中", value: "running" },
  { label: "已成功", value: "succeeded" },
  { label: "部分失败", value: "partial_failed" },
  { label: "失败", value: "failed" },
];

const STATUS_COLOR: Record<string, string> = {
  queued: "default",
  running: "processing",
  succeeded: "success",
  partial_failed: "warning",
  failed: "error",
};

function formatDateTime(value?: string | null) {
  return value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";
}

function formatCount(done: number, total: number, failed: number) {
  return `${done}/${total} · 失败 ${failed}`;
}

function jsonSummary(value: unknown) {
  if (value === null || value === undefined) {
    return "-";
  }
  try {
    const text = JSON.stringify(value, null, 2);
    return text.length > 240 ? `${text.slice(0, 240)}...` : text;
  } catch {
    const text = String(value);
    return text.length > 240 ? `${text.slice(0, 240)}...` : text;
  }
}

function StatusTag({ status }: { status: string }) {
  return <Tag color={STATUS_COLOR[status] || "default"}>{status}</Tag>;
}

export default function TaskCenterPage() {
  const [items, setItems] = useState<AsyncTaskRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [service, setService] = useState("");
  const [status, setStatus] = useState("");
  const [taskType, setTaskType] = useState("");
  const [searchText, setSearchText] = useState("");
  const [submittedKeyword, setSubmittedKeyword] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedTask, setSelectedTask] =
    useState<AsyncTaskDetailRecord | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const fetchTasks = useCallback(
    async (nextPage: number, nextPageSize: number) => {
      setLoading(true);
      try {
        const response = await monitorApi.getAsyncTasks({
          service: service || undefined,
          status: status || undefined,
          task_type: taskType.trim() || undefined,
          keyword: submittedKeyword || undefined,
          page: nextPage,
          page_size: nextPageSize,
        });
        setItems(response.items);
        setTotal(response.total);
        setPage(response.page);
        setPageSize(response.page_size);
      } finally {
        setLoading(false);
      }
    },
    [service, status, taskType, submittedKeyword],
  );

  useEffect(() => {
    void fetchTasks(1, pageSize);
  }, [fetchTasks, pageSize]);

  const openTaskDetail = async (taskId: string) => {
    setDetailLoading(true);
    try {
      setSelectedTask(await monitorApi.getAsyncTaskDetail(taskId));
    } finally {
      setDetailLoading(false);
    }
  };

  const columns: ColumnsType<AsyncTaskRecord> = [
    {
      title: "任务标题",
      dataIndex: "title",
      key: "title",
      render: (_value, record) => (
        <button
          type="button"
          className={styles.linkButton}
          onClick={() => {
            void openTaskDetail(record.task_id);
          }}
        >
          <span>{record.title}</span>
          <small>{record.summary || record.task_id}</small>
        </button>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 120,
      render: (value) => <StatusTag status={String(value)} />,
    },
    {
      title: "服务 / 类型",
      key: "service",
      width: 220,
      render: (_, record) => (
        <div className={styles.metaCell}>
          <strong>{record.service}</strong>
          <span>{record.task_type}</span>
        </div>
      ),
    },
    {
      title: "进度",
      key: "progress",
      width: 150,
      render: (_, record) => (
        <span>
          {formatCount(
            record.done_count,
            record.target_count,
            record.failed_count,
          )}
        </span>
      ),
    },
    {
      title: "来源",
      dataIndex: "source_id",
      key: "source_id",
      width: 120,
      render: (value) => value || "-",
    },
    {
      title: "租户",
      dataIndex: "tenant_id",
      key: "tenant_id",
      width: 160,
      render: (value) => value || "-",
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      key: "created_at",
      width: 180,
      render: (value) => formatDateTime(value),
    },
    {
      title: "完成时间",
      dataIndex: "finished_at",
      key: "finished_at",
      width: 180,
      render: (value) => formatDateTime(value),
    },
  ];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>异步任务中心</h1>
          <p>SWE、Market 与内部初始化任务的运行记录。</p>
        </div>
        <Button
          icon={<RefreshCw size={16} />}
          onClick={() => {
            void fetchTasks(page, pageSize);
          }}
        >
          刷新
        </Button>
      </header>

      <section className={styles.toolbar}>
        <Select
          className={styles.select}
          options={SERVICE_OPTIONS}
          value={service}
          onChange={setService}
        />
        <Select
          className={styles.select}
          options={STATUS_OPTIONS}
          value={status}
          onChange={setStatus}
        />
        <Input
          className={styles.taskTypeInput}
          placeholder="任务类型"
          value={taskType}
          onChange={(event) => setTaskType(event.target.value)}
          allowClear
        />
        <Input
          className={styles.searchInput}
          prefix={<Search size={14} />}
          placeholder="按标题、摘要、任务ID搜索"
          value={searchText}
          onChange={(event) => setSearchText(event.target.value)}
          allowClear
        />
        <Button
          type="primary"
          icon={<Search size={16} />}
          onClick={() => {
            const nextKeyword = searchText.trim();
            if (nextKeyword === submittedKeyword) {
              void fetchTasks(1, pageSize);
              return;
            }
            setSubmittedKeyword(nextKeyword);
          }}
        >
          查询
        </Button>
      </section>

      <section className={styles.tableSection}>
        <Spin spinning={loading}>
          <Table<AsyncTaskRecord>
            rowKey="task_id"
            columns={columns}
            dataSource={items}
            pagination={false}
            locale={{
              emptyText: <Empty description="暂无任务" />,
            }}
            size="middle"
          />
        </Spin>
      </section>

      <div className={styles.footer}>
        <Pagination
          current={page}
          pageSize={pageSize}
          total={total}
          showSizeChanger
          showTotal={(count) => `共 ${count} 条`}
          onChange={(nextPage, nextPageSize) => {
            void fetchTasks(nextPage, nextPageSize);
          }}
        />
      </div>

      <Drawer
        title={selectedTask?.title || "任务详情"}
        open={selectedTask !== null}
        onClose={() => setSelectedTask(null)}
        width={720}
        destroyOnClose
      >
        <Spin spinning={detailLoading}>
          {selectedTask ? (
            <div className={styles.detail}>
              <section className={styles.detailGrid}>
                <div>
                  <span>任务ID</span>
                  <strong>{selectedTask.task_id}</strong>
                </div>
                <div>
                  <span>状态</span>
                  <strong>
                    <StatusTag status={selectedTask.status} />
                  </strong>
                </div>
                <div>
                  <span>服务</span>
                  <strong>{selectedTask.service}</strong>
                </div>
                <div>
                  <span>类型</span>
                  <strong>{selectedTask.task_type}</strong>
                </div>
                <div>
                  <span>进度</span>
                  <strong>
                    {formatCount(
                      selectedTask.done_count,
                      selectedTask.target_count,
                      selectedTask.failed_count,
                    )}
                  </strong>
                </div>
                <div>
                  <span>时间</span>
                  <strong>{formatDateTime(selectedTask.created_at)}</strong>
                </div>
              </section>

              <section className={styles.detailBlock}>
                <h3>摘要</h3>
                <p>{selectedTask.summary || "-"}</p>
              </section>

              <section className={styles.detailBlock}>
                <h3>结果</h3>
                <pre className={styles.jsonBox}>
                  {jsonSummary(selectedTask.result_json)}
                </pre>
              </section>

              <section className={styles.detailBlock}>
                <h3>目标明细</h3>
                <Table
                  rowKey="target_id"
                  size="small"
                  pagination={false}
                  dataSource={selectedTask.items}
                  columns={[
                    {
                      title: "目标",
                      dataIndex: "target_id",
                      key: "target_id",
                      render: (value, record) => (
                        <div className={styles.metaCell}>
                          <strong>{value}</strong>
                          <span>{record.target_name || "-"}</span>
                        </div>
                      ),
                    },
                    {
                      title: "状态",
                      dataIndex: "status",
                      key: "status",
                      width: 120,
                      render: (value) => <StatusTag status={String(value)} />,
                    },
                    {
                      title: "错误信息",
                      dataIndex: "error_message",
                      key: "error_message",
                      render: (value) => value || "-",
                    },
                  ]}
                />
              </section>
            </div>
          ) : null}
        </Spin>
      </Drawer>
    </div>
  );
}
