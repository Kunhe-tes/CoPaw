import { useEffect, useRef, useState } from "react";
import { Alert, Button, Empty, Input, Select, Skeleton, Tooltip } from "antd";
import { PencilLine, RotateCw, Search } from "lucide-react";
import {
  fetchInsuranceTracking,
  saveInsuranceChange,
  InsuranceApiUnavailableError,
  INTENTION_LABELS,
  EDIT_LABELS,
  type ContactRecord,
  type FollowUpRecord,
  type EditKind,
  type InsuranceEditorChange,
  type InsuranceCustomer,
  type InsuranceList,
  type Intention,
} from "./api";
import { InsuranceEditor } from "./Editor";
import { RecordCell } from "./RecordCell";
import { RemoveTracking } from "./RemoveTracking";
import { TableHeading } from "./TableHeading";
import { orderCustomers, type ListSort, type SortKey } from "./listOrder";
import { Icon } from "../../components/Icon";
import workbenchStyles from "../../index.module.less";
import styles from "./index.module.less";

const EMPTY_DATA: InsuranceList = {
  customers: [],
  counts: { customers: 0, highIntention: 0, tracking: 0 },
};

const EDIT_FIELDS = {
  insurancePlan: "insurancePlan",
  contactPlan: "contactPlans",
  followUp: "followUps",
} as const;

interface FailedEdit {
  customer: InsuranceCustomer;
  change: InsuranceEditorChange;
  reason: string;
}

function editTarget(change: InsuranceEditorChange) {
  return change.kind === "insurancePlan"
    ? change.kind
    : `${change.kind}-${change.recordId ?? "new"}`;
}

function sortRecords<T extends { id: string; date: string }>(entries: T[]) {
  return [...entries].sort((a, b) =>
    b.date.replace(" ", "T").localeCompare(a.date.replace(" ", "T")),
  );
}

export function InsuranceTracking({
  refreshKey,
  onExecute,
  onShowScheme,
  onBusyChange,
  onViewInsuranceTasks,
}: {
  refreshKey: number;
  onBusyChange?: (busy: boolean) => void;
  onViewInsuranceTasks?: () => void;
  onShowScheme: (customer: InsuranceCustomer) => void;
  onExecute: (
    kind: "dial" | "insight",
    customer: InsuranceCustomer,
  ) => Promise<void>;
}) {
  const [data, setData] = useState<InsuranceList>(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [unavailable, setUnavailable] = useState(false);
  const [notice, setNotice] = useState("");
  const [retry, setRetry] = useState(0);
  const [failedEdits, setFailedEdits] = useState<FailedEdit[]>([]);
  const [search, setSearch] = useState("");
  const [intentionFilter, setIntentionFilter] = useState<Intention | "all">(
    "all",
  );
  const [sort, setSort] = useState<ListSort>(null);
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [removing, setRemoving] = useState<InsuranceCustomer | null>(null);
  const locks = useRef(new Set<string>());
  const generation = useRef(0);
  const [editor, setEditor] = useState<{
    customer: InsuranceCustomer;
    kind: EditKind;
    draft?: InsuranceEditorChange;
    record?: ContactRecord | FollowUpRecord;
  } | null>(null);

  useEffect(() => {
    onBusyChange?.(loading || pending.size > 0 || !!editor || !!removing);
    return () => onBusyChange?.(false);
  }, [loading, pending.size, editor, removing, onBusyChange]);

  useEffect(() => {
    // 正在保存时保留本次编辑，防止刷新响应覆盖乐观更新。
    if (locks.current.size) return;
    const controller = new AbortController();
    const version = ++generation.current;
    setLoading(true);
    setError("");
    setNotice("");
    setUnavailable(false);
    void fetchInsuranceTracking(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted && version === generation.current) {
          setData(result);
        }
      })
      .catch((cause) => {
        if (!controller.signal.aborted && version === generation.current) {
          setError(cause instanceof Error ? cause.message : "加载失败，请重试");
          setUnavailable(cause instanceof InsuranceApiUnavailableError);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted && version === generation.current)
          setLoading(false);
      });
    return () => controller.abort();
  }, [refreshKey, retry]);

  const lock = (id: string, value: boolean) => {
    if (value) locks.current.add(id);
    else locks.current.delete(id);
    setPending(new Set(locks.current));
  };

  const changeIntention = async (
    customer: InsuranceCustomer,
    value: Intention,
  ) => {
    if (locks.current.has(customer.id) || customer.intention === value) return;
    const delta = Number(value === 3) - Number(customer.intention === 3);
    lock(customer.id, true);
    setNotice("");
    const apply = (intention: Intention, countDelta: number) =>
      setData((current) => ({
        ...current,
        customers: current.customers.map((row) =>
          row.id === customer.id ? { ...row, intention } : row,
        ),
        counts: {
          ...current.counts,
          highIntention: current.counts.highIntention + countDelta,
        },
      }));
    apply(value, delta);
    try {
      await saveInsuranceChange(customer, { kind: "intention", value });
    } catch {
      apply(customer.intention, -delta);
      setNotice(`${customer.name}的意向度保存失败，已恢复原值，请重试`);
    } finally {
      lock(customer.id, false);
    }
  };

  const openEditor = (
    customer: InsuranceCustomer,
    kind: EditKind,
    record?: ContactRecord | FollowUpRecord,
    draft?: InsuranceEditorChange,
  ) => {
    if (locks.current.has(customer.id)) return;
    const row =
      data.customers.find((item) => item.id === customer.id) ?? customer;
    const failed = failedEdits.find(
      (item) =>
        item.customer.id === customer.id &&
        item.change.kind === kind &&
        (item.change.kind === "insurancePlan" ||
          item.change.recordId === record?.id),
    );
    setEditor({ customer: row, kind, record, draft: draft ?? failed?.change });
  };

  const startEditSave = (
    customer: InsuranceCustomer,
    change: InsuranceEditorChange,
  ) => {
    if (locks.current.has(customer.id)) return;
    const row =
      data.customers.find((item) => item.id === customer.id) ?? customer;
    const field = EDIT_FIELDS[change.kind];
    const previous = row[field];
    const clearFailure = (items: FailedEdit[]) =>
      items.filter(
        (item) =>
          item.customer.id !== customer.id ||
          editTarget(item.change) !== editTarget(change),
      );
    const apply = (
      value: string | (ContactRecord | FollowUpRecord)[] | undefined,
    ) =>
      setData((current) => ({
        ...current,
        customers: current.customers.map((item) =>
          item.id === customer.id ? { ...item, [field]: value } : item,
        ),
      }));
    lock(customer.id, true);
    setFailedEdits(clearFailure);
    const optimisticId =
      change.kind === "insurancePlan"
        ? ""
        : change.recordId ?? `pending-${change.requestId}`;
    const optimisticValue =
      change.kind === "insurancePlan"
        ? change.value
        : sortRecords([
            ...(
              (row[field] ?? []) as (ContactRecord | FollowUpRecord)[]
            ).filter((entry) => entry.id !== optimisticId),
            { ...change.value, id: optimisticId },
          ]);
    apply(optimisticValue);
    setEditor(null);
    // 只保存本次字段的旧值；失败时不撤回其他客户或其他字段的修改。
    void saveInsuranceChange(row, change)
      .then((record) => {
        if (!record || change.kind === "insurancePlan") return;
        setData((current) => ({
          ...current,
          customers: current.customers.map((item) =>
            item.id === customer.id
              ? {
                  ...item,
                  [field]: sortRecords([
                    ...(
                      (item[field] ?? []) as (ContactRecord | FollowUpRecord)[]
                    ).filter((entry) => entry.id !== optimisticId),
                    record,
                  ]),
                }
              : item,
          ),
        }));
      })
      .catch((cause) => {
        apply(previous);
        setFailedEdits((items) => [
          ...clearFailure(items),
          {
            customer: row,
            change,
            reason: cause instanceof Error ? cause.message : "保存失败，请重试",
          },
        ]);
      })
      .finally(() => lock(customer.id, false));
  };

  const saveEditor = (change: InsuranceEditorChange) => {
    if (editor) startEditSave(editor.customer, change);
  };

  const query = search.trim().toLocaleLowerCase();
  const filtered = data.customers.filter(
    (row) =>
      (intentionFilter === "all" || row.intention === intentionFilter) &&
      [
        row.name,
        row.branchName,
        row.insurancePlan,
        ...(row.contactPlans ?? []).map((entry) => entry.content),
        ...(row.followUps ?? []).map((entry) => entry.content),
      ].some((value) => value?.toLocaleLowerCase().includes(query)),
  );
  const rows = orderCustomers(filtered, sort);
  const toggleSort = (key: SortKey) => {
    setSort((current) =>
      current?.key !== key
        ? { key, direction: "asc" }
        : current.direction === "asc"
        ? { key, direction: "desc" }
        : null,
    );
  };

  return (
    <div className={styles.root}>
      <div
        className={workbenchStyles.taskSummary}
        aria-label="保险跟踪统计"
        aria-busy={loading}
      >
        <div className={workbenchStyles.bubble}>
          <Icon name="list" />
        </div>
        <div>
          <h3 className={workbenchStyles.taskSummaryTitle}>
            持续跟踪客户保险需求
          </h3>
          <div className={workbenchStyles.summaryMetrics} aria-live="polite">
            <span>
              跟踪客户 <b>{loading || error ? "—" : data.counts.tracking}</b> 人
            </span>
            <span>
              高意向客户{" "}
              <b className={styles.high}>
                {loading || error ? "—" : data.counts.highIntention}
              </b>{" "}
              人
            </span>
          </div>
        </div>
      </div>
      <div className={`${workbenchStyles.tableToolbar} ${styles.toolbar}`}>
        <span>来自保险初筛识别任务的跟踪客户</span>
        <div className={styles.tools}>
          <Input
            aria-label="搜索保险跟踪客户"
            placeholder="搜索客户、计划或跟进记录"
            prefix={<Search size={15} aria-hidden />}
            value={search}
            disabled={loading || !!error}
            allowClear
            onChange={(event) => {
              setSearch(event.target.value);
            }}
          />
          <Button
            aria-label="刷新保险跟踪"
            icon={<RotateCw size={15} aria-hidden />}
            disabled={loading || pending.size > 0 || !!editor || !!removing}
            onClick={() => setRetry((value) => value + 1)}
          />
        </div>
      </div>
      {notice && (
        <Alert
          type="error"
          showIcon
          message={notice}
          role="alert"
          closable
          onClose={() => setNotice("")}
        />
      )}
      {failedEdits.map((failed) => (
        <Alert
          key={`${failed.customer.id}-${editTarget(failed.change)}`}
          className={styles.saveFailure}
          type="error"
          showIcon
          role="alert"
          message={
            <div className={styles.failureRow}>
              <Tooltip
                trigger={["hover", "focus"]}
                title={`${failed.customer.name}的${
                  EDIT_LABELS[failed.change.kind]
                }保存失败，已恢复原值。${
                  failed.reason
                }。填写内容已保留，可重试保存或修改后重试。`}
              >
                <span className={styles.failureText} tabIndex={0}>
                  {failed.customer.name}的{EDIT_LABELS[failed.change.kind]}
                  保存失败，已恢复原值，填写内容已保留 · {failed.reason}
                </span>
              </Tooltip>
              <div className={styles.retryActions}>
                <button
                  type="button"
                  className={workbenchStyles.link}
                  aria-label={`重试保存${failed.customer.name}的${
                    EDIT_LABELS[failed.change.kind]
                  }`}
                  disabled={
                    loading ||
                    !!error ||
                    pending.has(failed.customer.id) ||
                    !!editor
                  }
                  onClick={() => startEditSave(failed.customer, failed.change)}
                >
                  重试保存
                </button>
                <button
                  type="button"
                  className={workbenchStyles.link}
                  aria-label={`修改${failed.customer.name}的${
                    EDIT_LABELS[failed.change.kind]
                  }后重试`}
                  disabled={
                    loading ||
                    !!error ||
                    pending.has(failed.customer.id) ||
                    !!editor
                  }
                  onClick={() =>
                    openEditor(
                      failed.customer,
                      failed.change.kind,
                      undefined,
                      failed.change,
                    )
                  }
                >
                  修改后重试
                </button>
              </div>
            </div>
          }
        />
      ))}
      {loading ? (
        <div
          className={styles.loading}
          role="status"
          aria-label="正在加载保险跟踪"
        >
          <Skeleton active paragraph={{ rows: 5 }} />
        </div>
      ) : error ? (
        <div className={styles.error} role="alert">
          <strong>{error}</strong>
          <p>
            {unavailable
              ? "服务接入后，可在此查看客户保险计划、安排接触并记录跟进。"
              : "请检查网络连接后重试。"}
          </p>
          <Button onClick={() => setRetry((value) => value + 1)}>
            重新加载
          </Button>
        </div>
      ) : !data.customers.length ? (
        <div className={styles.initialEmpty} role="status">
          <h3>暂未添加跟踪客户</h3>
          <p>
            {onViewInsuranceTasks
              ? "在保险任务中点击“加入跟踪”，客户将显示在这里。"
              : "当前暂无保险任务，添加跟踪客户后将在这里展示。"}
          </p>
          {onViewInsuranceTasks && (
            <button
              type="button"
              className={`${workbenchStyles.btn} ${workbenchStyles.primary}`}
              onClick={onViewInsuranceTasks}
            >
              查看保险任务
            </button>
          )}
        </div>
      ) : (
        <>
          <div
            className={`${workbenchStyles.tableWrap} ${styles.tableScroll}`}
            tabIndex={0}
            role="region"
            aria-label="保险核心跟踪客户表，可横向滚动"
          >
            <table
              className={`${workbenchStyles.customerTable} ${styles.table}`}
            >
              <colgroup>
                {[120, 120, 210, 200, 220, 130, 120, 240].map(
                  (width, index) => (
                    <col key={index} style={{ width }} />
                  ),
                )}
              </colgroup>
              <thead>
                <tr>
                  {[
                    "客户姓名",
                    "资产",
                    "保险计划",
                    "接触计划",
                    "最后跟进记录",
                    "客户意向度",
                    "经营方案",
                    "执行",
                  ].map((label) => (
                    <TableHeading
                      key={label}
                      label={label}
                      sort={sort}
                      onSort={toggleSort}
                      intention={intentionFilter}
                      onIntention={setIntentionFilter}
                    />
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((customer) => (
                  <tr key={customer.id}>
                    <td className={workbenchStyles.name}>{customer.name}</td>
                    <td>
                      <strong>
                        {customer.assets === "" ? "—" : customer.assets ?? "—"}
                      </strong>
                      <small>{customer.assetsDescription || ""}</small>
                    </td>
                    <td>
                      <div className={styles.planCell}>
                        <Tooltip
                          title={customer.insurancePlan}
                          trigger={["hover", "focus"]}
                        >
                          <p
                            className={styles.preview}
                            tabIndex={customer.insurancePlan ? 0 : undefined}
                          >
                            {customer.insurancePlan || "暂无保险计划"}
                          </p>
                        </Tooltip>
                        <Tooltip title="编辑" trigger={["hover", "focus"]}>
                          <button
                            type="button"
                            className={`${workbenchStyles.btn} ${styles.edit}`}
                            disabled={pending.has(customer.id)}
                            aria-label={`编辑${customer.name}的保险计划`}
                            onClick={() =>
                              openEditor(customer, "insurancePlan")
                            }
                          >
                            <PencilLine size={14} aria-hidden />
                          </button>
                        </Tooltip>
                      </div>
                    </td>
                    <td>
                      <RecordCell
                        entries={customer.contactPlans ?? []}
                        kind="contactPlan"
                        customerName={customer.name}
                        disabled={pending.has(customer.id)}
                        onEdit={(record) =>
                          openEditor(customer, "contactPlan", record)
                        }
                        onAdd={() => openEditor(customer, "contactPlan")}
                      />
                    </td>
                    <td>
                      <RecordCell
                        entries={customer.followUps ?? []}
                        kind="followUp"
                        customerName={customer.name}
                        disabled={pending.has(customer.id)}
                        onEdit={(record) =>
                          openEditor(customer, "followUp", record)
                        }
                        onAdd={() => openEditor(customer, "followUp")}
                      />
                    </td>
                    <td>
                      <Select
                        aria-label={`${customer.name}的客户意向度`}
                        value={customer.intention}
                        loading={pending.has(customer.id)}
                        disabled={pending.has(customer.id)}
                        className={styles.intention}
                        onChange={(value: Intention) => {
                          void changeIntention(customer, value);
                        }}
                        options={Object.entries(INTENTION_LABELS).map(
                          ([value, label]) => ({
                            value: Number(value) as Intention,
                            label,
                          }),
                        )}
                      />
                    </td>
                    <td className={styles.scheme}>
                      <button
                        type="button"
                        className={workbenchStyles.link}
                        onClick={() => onShowScheme(customer)}
                      >
                        查看经营方案
                      </button>
                    </td>
                    <td>
                      <div className={workbenchStyles.contactActions}>
                        <button
                          type="button"
                          className={`${workbenchStyles.btn} ${workbenchStyles.primary}`}
                          disabled={!customer.custUid}
                          onClick={() => {
                            void onExecute("dial", customer);
                          }}
                        >
                          <Icon name="phone" />
                          电访
                        </button>
                        <button
                          type="button"
                          className={workbenchStyles.btn}
                          disabled={!customer.custUid}
                          onClick={() => {
                            void onExecute("insight", customer);
                          }}
                        >
                          <Icon name="user" />
                          客户洞察
                        </button>
                      </div>
                      <button
                        type="button"
                        className={`${workbenchStyles.link} ${styles.remove}`}
                        aria-label={`移除${customer.name}的跟踪`}
                        disabled={pending.has(customer.id)}
                        onClick={() => setRemoving(customer)}
                      >
                        移除跟踪
                      </button>
                      {pending.has(customer.id) && (
                        <span className={styles.saving} role="status">
                          保存中…
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!rows.length && (
              <Empty
                className={styles.empty}
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="未找到匹配的客户，请调整搜索条件"
              />
            )}
          </div>
          <div className={workbenchStyles.pagination}>
            <span className={workbenchStyles.total}>
              共 {filtered.length} 条记录
            </span>
          </div>
        </>
      )}
      {removing && (
        <RemoveTracking
          customer={removing}
          onClose={() => setRemoving(null)}
          onRemoved={() => {
            setData((current) => ({
              ...current,
              customers: current.customers.filter(
                (row) => row.id !== removing.id,
              ),
              counts: {
                customers: current.counts.customers - 1,
                tracking: current.counts.tracking - 1,
                highIntention:
                  current.counts.highIntention -
                  Number(removing.intention === 3),
              },
            }));
            setFailedEdits((items) =>
              items.filter((item) => item.customer.id !== removing.id),
            );
            setRemoving(null);
          }}
        />
      )}
      {editor && (
        <InsuranceEditor
          key={`${editor.customer.id}-${editor.kind}-${
            editor.record?.id ?? "new"
          }`}
          {...editor}
          onSave={saveEditor}
          onClose={() => setEditor(null)}
        />
      )}
    </div>
  );
}
