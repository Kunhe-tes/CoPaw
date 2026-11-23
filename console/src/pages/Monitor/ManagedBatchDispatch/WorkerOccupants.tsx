import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Pagination, Select, Table, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  managedBatchBoard,
  type ManagedWorkerOccupant,
  type ManagedWorkerPool,
} from "@/api/modules/managedBatchBoard";
import styles from "../CronBatchDispatch/index.module.less";
import workerStyles from "./workers.module.less";
import { labels, timeText } from "./format";
import { useBoardResource } from "./useBoardResource";

const PAGE_SIZE = 10;
const typeLabels: Record<string, string> = {
  daily_failure_retry: "整点补跑",
  batch_auto_retry: "批自动重试",
  batch_manual_retry: "批人工重跑",
  batch_retry: "批重跑",
  batch: "批首次执行",
  ordinary: "普通定时执行",
  manual: "手动执行",
  legacy_batch: "旧版批执行",
};

const columns: ColumnsType<ManagedWorkerOccupant> = [
  {
    title: "人员",
    width: 105,
    render: (_, row) => (
      <div className={styles.stackCell}>
        <strong title={row.tenant_name ?? undefined}>
          {row.tenant_name || "—"}
        </strong>
        <span title={row.tenant_id}>{row.tenant_id}</span>
      </div>
    ),
  },
  {
    title: "定时任务",
    width: 190,
    render: (_, row) => (
      <div className={styles.stackCell}>
        <strong title={row.job_name ?? undefined}>{row.job_name || "—"}</strong>
        <Tooltip title={row.job_id} trigger={["hover", "focus"]}>
          <span tabIndex={0}>{row.job_id}</span>
        </Tooltip>
      </div>
    ),
  },
  {
    title: "开始时间",
    width: 138,
    render: (_, row) =>
      row.started_at ? timeText(row.started_at) : "尚未开始",
  },
  {
    title: "类型 / 状态",
    width: 110,
    render: (_, row) => (
      <div className={styles.stackCell}>
        <strong>{typeLabels[row.execution_type] ?? row.execution_type}</strong>
        <span>
          {row.status === "waiting_subtasks"
            ? "等待子任务"
            : labels[row.status] ?? row.status}
        </span>
      </div>
    ),
  },
];

const poolKey = (pool: ManagedWorkerPool) =>
  JSON.stringify([pool.provider_id, pool.model_id]);

export default function WorkerOccupants({
  source,
  refresh,
  pools,
}: {
  source: string;
  refresh: number;
  pools: ManagedWorkerPool[];
}) {
  const [pool, setPool] = useState<ManagedWorkerPool>();
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const load = useCallback(
    (signal: AbortSignal) => {
      void refresh;
      void revision;
      return managedBatchBoard.workerOccupants(
        source,
        { ...pool, page, page_size: PAGE_SIZE },
        signal,
      );
    },
    [source, pool, page, refresh, revision],
  );
  const { value, loading, error } = useBoardResource(load);
  const total = value?.total;
  useEffect(() => {
    if (total === undefined) return;
    setPage((current) =>
      Math.min(current, Math.max(1, Math.ceil(total / PAGE_SIZE))),
    );
  }, [total]);
  const poolOptions = new Map(pools.map((item) => [poolKey(item), item]));
  if (pool) poolOptions.set(poolKey(pool), pool);

  return (
    <article className={`${styles.panel} ${workerStyles.occupants}`}>
      <div className={styles.panelHeader}>
        <div>
          <h2>当前 Worker 占用{total === undefined ? "" : `（${total}）`}</h2>
          {value && <span>查询时间 {timeText(value.sampled_at)}</span>}
        </div>
        <Button
          size="small"
          loading={loading}
          onClick={() => {
            setPage(1);
            setRevision((current) => current + 1);
          }}
        >
          刷新占用
        </Button>
      </div>
      <Select
        aria-label="筛选占用模型池"
        placeholder="全部模型池"
        allowClear
        size="small"
        className={workerStyles.poolFilter}
        value={pool ? poolKey(pool) : undefined}
        options={[...poolOptions].map(([key, item]) => ({
          value: key,
          label: `${item.provider_id} / ${item.model_id}`,
        }))}
        onChange={(key) => {
          setPool(poolOptions.get(key));
          setPage(1);
        }}
      />
      <div className={workerStyles.occupantsBody}>
        {error ? (
          <Alert type="error" message="Worker 占用查询失败，请刷新重试" />
        ) : (
          <Table
            size="small"
            rowKey="id"
            dataSource={value?.items ?? []}
            columns={columns}
            loading={loading}
            pagination={false}
            scroll={{ x: 543 }}
            locale={{ emptyText: loading ? "查询中" : "当前无 Worker 占用" }}
          />
        )}
      </div>
      <Pagination
        aria-label="Worker 占用分页"
        size="small"
        current={page}
        pageSize={PAGE_SIZE}
        total={total}
        onChange={setPage}
        showSizeChanger={false}
        hideOnSinglePage
      />
    </article>
  );
}
