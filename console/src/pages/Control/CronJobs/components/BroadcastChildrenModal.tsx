import { useEffect, useMemo, useState } from "react";
import type { Key } from "react";
import { Alert, Space, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Button, Modal, Table } from "@agentscope-ai/design";
import api from "../../../../api";
import type {
  CronBroadcastChildItem,
  CronBroadcastChildOperationResult,
  CronJobSpecOutput,
} from "../../../../api/types";

type CronJob = CronJobSpecOutput;

interface BroadcastChildrenModalProps {
  open: boolean;
  job: CronJob | null;
  onClose: () => void;
}

function rowKey(item: CronBroadcastChildItem): string {
  return `${item.tenant_id}:${item.job_id}`;
}

function resultLine(item: CronBroadcastChildOperationResult): string {
  const base = `${item.tenant_id} / ${item.job_id}`;
  if (item.status === "skipped") {
    return `${base}: 已暂停，未执行`;
  }
  if (item.success) {
    return `${base}: ${item.status}`;
  }
  return `${base}: ${item.message || "failed"}`;
}

export function BroadcastChildrenModal({
  open,
  job,
  onClose,
}: BroadcastChildrenModalProps) {
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [children, setChildren] = useState<CronBroadcastChildItem[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [operationResults, setOperationResults] = useState<
    CronBroadcastChildOperationResult[]
  >([]);

  const selectedItems = useMemo(() => {
    const selected = new Set(selectedRowKeys.map(String));
    return children.filter((item) => selected.has(rowKey(item)));
  }, [children, selectedRowKeys]);
  const hasFailedResults = operationResults.some((result) => !result.success);

  const loadChildren = async () => {
    if (!job) return;
    setLoading(true);
    try {
      const response = await api.listCronBroadcastChildren(job.id);
      setChildren(response.items || []);
      setSelectedRowKeys([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!open) {
      setChildren([]);
      setSelectedRowKeys([]);
      setOperationResults([]);
      return;
    }
    void loadChildren();
  }, [open, job?.id]);

  const batchRefs = selectedItems.map((item) => ({
    tenant_id: item.tenant_id,
    job_id: item.job_id,
  }));

  const handleDelete = async () => {
    if (!job || batchRefs.length === 0) return;
    setSubmitting(true);
    try {
      const response = await api.deleteCronBroadcastChildren(job.id, batchRefs);
      setOperationResults(response.results || []);
      await loadChildren();
    } finally {
      setSubmitting(false);
    }
  };

  const handleRun = async () => {
    if (!job || batchRefs.length === 0) return;
    setSubmitting(true);
    try {
      const response = await api.runCronBroadcastChildren(job.id, batchRefs);
      setOperationResults(response.results || []);
      await loadChildren();
    } finally {
      setSubmitting(false);
    }
  };

  const columns: ColumnsType<CronBroadcastChildItem> = [
    {
      title: "用户",
      key: "tenant",
      width: 220,
      render: (_: unknown, record) =>
        record.tenant_name
          ? `${record.tenant_name} (${record.tenant_id})`
          : record.tenant_id,
    },
    {
      title: "机构",
      dataIndex: "bbk_id",
      key: "bbk_id",
      width: 120,
      render: (value?: string | null) => value || "-",
    },
    {
      title: "子任务ID",
      dataIndex: "job_id",
      key: "job_id",
      width: 220,
    },
    {
      title: "状态",
      key: "enabled",
      width: 110,
      render: (_: unknown, record) =>
        record.enabled ? (
          <Tag color="green">启用</Tag>
        ) : (
          <Tag color="default">已暂停</Tag>
        ),
    },
    {
      title: "Cron",
      dataIndex: "cron",
      key: "cron",
      width: 160,
    },
    {
      title: "时区",
      dataIndex: "timezone",
      key: "timezone",
      width: 140,
    },
    {
      title: "错峰",
      dataIndex: "offset_minutes",
      key: "offset_minutes",
      width: 100,
      render: (value: number) => `${value || 0} 分钟`,
    },
    {
      title: "最近状态",
      dataIndex: "last_status",
      key: "last_status",
      width: 120,
      render: (value?: string | null) => value || "-",
    },
  ];

  return (
    <Modal
      open={open}
      title={job ? `分发用户 / 子任务：${job.name}` : "分发用户 / 子任务"}
      onCancel={submitting ? undefined : onClose}
      footer={null}
      width={960}
    >
      <div style={{ display: "grid", gap: 12 }}>
        <Alert
          type="info"
          showIcon
          message="这里展示该源定时任务已经分发出去的子定时任务。没有分发过时列表为空。"
        />

        <Space>
          <Button onClick={loadChildren} loading={loading}>
            刷新
          </Button>
          <Button
            danger
            disabled={selectedItems.length === 0}
            loading={submitting}
            onClick={() => {
              Modal.confirm({
                title: "删除选中的子定时任务？",
                content: "只会删除子定时任务，不影响当前源任务。",
                okText: "删除",
                okButtonProps: { danger: true },
                cancelText: "取消",
                onOk: handleDelete,
              });
            }}
          >
            批量删除
          </Button>
          <Button
            disabled={selectedItems.length === 0}
            loading={submitting}
            onClick={handleRun}
          >
            批量重跑
          </Button>
        </Space>

        {operationResults.length > 0 && (
          <Alert
            type={hasFailedResults ? "warning" : "success"}
            showIcon
            message="批量操作结果"
            description={
              <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                {operationResults.map(resultLine).join("\n")}
              </pre>
            }
          />
        )}

        <Table
          rowKey={rowKey}
          columns={columns}
          dataSource={children}
          loading={loading}
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
          }}
          pagination={{ pageSize: 8 }}
          locale={{ emptyText: "当前任务尚未分发给任何用户" }}
          scroll={{ x: 1170 }}
        />
      </div>
    </Modal>
  );
}
