import { useId, useLayoutEffect, useRef, useState } from "react";
import { Tooltip } from "antd";
import { ChevronDown, ChevronUp, PencilLine, Plus } from "lucide-react";
import {
  EDIT_LABELS,
  FOLLOW_UP_RESULTS,
  followUpMethodLabel,
  type ContactRecord,
  type FollowUpRecord,
  type EditKind,
} from "./api";
import workbenchStyles from "../../index.module.less";
import styles from "./index.module.less";

type RecordEntry = ContactRecord | FollowUpRecord;
type RecordKind = Exclude<EditKind, "insurancePlan">;

function RecordText({
  entry,
  full,
  onEdit,
  disabled,
  customerName,
  kind,
}: {
  entry: RecordEntry;
  full?: boolean;
  onEdit: () => void;
  disabled: boolean;
  customerName: string;
  kind: RecordKind;
}) {
  return (
    <div className={styles.record}>
      <div className={styles.recordHead}>
        {full ? (
          <p className={styles.fullContent}>{entry.content}</p>
        ) : (
          <Tooltip title={entry.content} trigger={["hover", "focus"]}>
            <p className={styles.recordPreview} tabIndex={0}>
              {entry.content || "—"}
            </p>
          </Tooltip>
        )}
        <Tooltip title="编辑" trigger={["hover", "focus"]}>
          <button
            type="button"
            className={`${workbenchStyles.btn} ${styles.edit}`}
            disabled={disabled}
            onClick={onEdit}
            aria-label={`编辑${customerName}的${EDIT_LABELS[kind]} ${entry.date}`}
          >
            <PencilLine size={14} aria-hidden />
          </button>
        </Tooltip>
      </div>
      <div className={styles.date}>
        {entry.date.replace("T", " ")} · {followUpMethodLabel(entry.method)}
        {full && "result" in entry
          ? ` · ${
              entry.result == null
                ? "触达结果未知"
                : FOLLOW_UP_RESULTS[entry.result]
            }`
          : ""}
      </div>
    </div>
  );
}

function RecordHistory({
  entries,
  kind,
  customerName,
  disabled,
  onEdit,
  onAdd,
  onClose,
}: {
  entries: RecordEntry[];
  kind: RecordKind;
  customerName: string;
  disabled: boolean;
  onEdit: (entry: RecordEntry) => void;
  onAdd: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useLayoutEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => {
      if (dialog?.open) dialog.close();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      className={`${workbenchStyles.dialog} ${styles.history}`}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className={workbenchStyles.dialogHead}>
        <h2 id={titleId}>
          {EDIT_LABELS[kind]} · {customerName}
        </h2>
      </div>
      <div className={`${workbenchStyles.dialogBody} ${styles.historyBody}`}>
        {entries.map((entry) => (
          <RecordText
            key={entry.id}
            entry={entry}
            full
            kind={kind}
            customerName={customerName}
            disabled={disabled}
            onEdit={() => {
              ref.current?.close();
              onClose();
              onEdit(entry);
            }}
          />
        ))}
      </div>
      <div className={workbenchStyles.dialogFooter}>
        <button type="button" className={workbenchStyles.btn} onClick={onClose}>
          关闭
        </button>
        <button
          type="button"
          className={`${workbenchStyles.btn} ${workbenchStyles.primary}`}
          disabled={disabled}
          onClick={() => {
            ref.current?.close();
            onClose();
            onAdd();
          }}
        >
          {kind === "contactPlan" ? "新增计划" : "新增记录"}
        </button>
      </div>
    </dialog>
  );
}

export function RecordCell({
  entries,
  kind,
  customerName,
  disabled,
  onEdit,
  onAdd,
}: {
  entries: RecordEntry[];
  kind: RecordKind;
  customerName: string;
  disabled: boolean;
  onEdit: (entry: RecordEntry) => void;
  onAdd: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [history, setHistory] = useState(false);
  return (
    <div className={styles.cell}>
      <div className={styles.records}>
        {entries.length ? (
          entries
            .slice(0, expanded ? 3 : 1)
            .map((entry) => (
              <RecordText
                key={entry.id}
                entry={entry}
                kind={kind}
                customerName={customerName}
                disabled={disabled}
                onEdit={() => onEdit(entry)}
              />
            ))
        ) : (
          <p className={styles.secondary}>
            {kind === "contactPlan" ? "暂无接触计划" : "暂无跟进记录"}
          </p>
        )}
      </div>
      <div className={styles.recordActions}>
        <button
          type="button"
          className={`${workbenchStyles.link} ${styles.add}`}
          disabled={disabled}
          aria-label={`新增${customerName}的${EDIT_LABELS[kind]}`}
          onClick={onAdd}
        >
          <Plus size={12} aria-hidden />
          {kind === "contactPlan" ? "新增计划" : "新增记录"}
        </button>
        {entries.length > 1 && (
          <div className={styles.browseActions}>
            <button
              type="button"
              className={`${workbenchStyles.link} ${styles.more}`}
              aria-expanded={expanded}
              aria-label={`${expanded ? "收起" : "展开更多"}${customerName}的${
                EDIT_LABELS[kind]
              }`}
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? "收起" : "展开更多"}
              {expanded ? (
                <ChevronUp size={12} aria-hidden />
              ) : (
                <ChevronDown size={12} aria-hidden />
              )}
            </button>
            {expanded && entries.length > 3 && (
              <button
                type="button"
                className={`${workbenchStyles.link} ${styles.more}`}
                onClick={() => setHistory(true)}
                aria-label={`查看${customerName}的全部${EDIT_LABELS[kind]}`}
              >
                全部{entries.length}条
              </button>
            )}
          </div>
        )}
      </div>
      {history && (
        <RecordHistory
          entries={entries}
          kind={kind}
          customerName={customerName}
          disabled={disabled}
          onEdit={onEdit}
          onAdd={onAdd}
          onClose={() => setHistory(false)}
        />
      )}
    </div>
  );
}
