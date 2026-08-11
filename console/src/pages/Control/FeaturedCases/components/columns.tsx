/* eslint-disable react-refresh/only-export-components */
import { useEffect, useRef, useState } from "react";
import { Button, InputNumber, Tooltip } from "antd";
import { CheckOutlined, CloseOutlined, FormOutlined } from "@ant-design/icons";
import type { ColumnType } from "antd/es/table";
import type { FeaturedCase } from "@/api/types/featuredCases";
import { BBK_ID_MAP } from "@/constants/bbk";
import styles from "../index.module.less";

interface CreateCaseColumnsOptions {
  writable: boolean;
  editingSortId: number | null;
  sortingId: number | null;
  onStartSort: (caseItem: FeaturedCase) => void;
  onFinishSort: () => void;
  onReorder: (caseItem: FeaturedCase, sortOrder: number) => Promise<void>;
  onEdit: (caseItem: FeaturedCase) => void;
  onDelete: (id: number) => void;
}

interface SortOrderCellProps {
  caseItem: FeaturedCase;
  editing: boolean;
  saving: boolean;
  disabled: boolean;
  onStart: () => void;
  onFinish: () => void;
  onSave: (sortOrder: number) => Promise<void>;
}

export class ReorderRefreshError extends Error {}

function SortOrderCell({
  caseItem,
  editing,
  saving,
  disabled,
  onStart,
  onFinish,
  onSave,
}: SortOrderCellProps) {
  const [draft, setDraft] = useState<number | null>(caseItem.sort_order);
  const [error, setError] = useState<string | null>(null);
  const submittingRef = useRef(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!editing) return;
    setDraft(caseItem.sort_order);
    setError(null);
    requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });
  }, [caseItem.sort_order, editing]);

  const cancel = () => {
    if (saving || submittingRef.current) return;
    setDraft(caseItem.sort_order);
    setError(null);
    onFinish();
  };

  const commit = async () => {
    if (saving || submittingRef.current) return;
    if (draft === caseItem.sort_order) {
      onFinish();
      return;
    }
    if (draft === null || !Number.isInteger(draft) || draft < 1) {
      setError("请输入大于等于 1 的整数");
      return;
    }

    submittingRef.current = true;
    setError(null);
    try {
      await onSave(draft);
      onFinish();
    } catch (saveError) {
      setError(
        saveError instanceof ReorderRefreshError
          ? saveError.message
          : "排序保存失败，请重试或按 Esc 取消",
      );
    } finally {
      submittingRef.current = false;
    }
  };

  if (!editing) {
    return (
      <div className={styles.sortDisplay}>
        <span>{caseItem.sort_order}</span>
        {!disabled && (
          <Tooltip title="调整排序">
            <Button
              aria-label={`编辑“${caseItem.label}”的排序`}
              className={styles.sortEditButton}
              disabled={saving}
              icon={<FormOutlined />}
              onClick={onStart}
              size="small"
              type="text"
            />
          </Tooltip>
        )}
      </div>
    );
  }

  return (
    <div className={styles.sortEditor}>
      <Tooltip open={Boolean(error)} placement="bottom" title={error}>
        <InputNumber
          aria-label={`“${caseItem.label}”的排序值`}
          className={styles.sortInput}
          controls={false}
          disabled={saving}
          min={1}
          onBlur={(event) => {
            const nextTarget = event.relatedTarget as Node | null;
            if (!event.currentTarget.parentElement?.contains(nextTarget)) {
              void commit();
            }
          }}
          onChange={(value) => setDraft(value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void commit();
            } else if (event.key === "Escape") {
              event.preventDefault();
              cancel();
            }
          }}
          ref={(instance) => {
            const nativeElement = instance?.nativeElement;
            inputRef.current =
              nativeElement instanceof HTMLInputElement
                ? nativeElement
                : nativeElement?.querySelector("input") ?? null;
          }}
          status={error ? "error" : undefined}
          step={1}
          value={draft}
        />
      </Tooltip>
      <Button
        aria-label="保存排序"
        className={`${styles.sortIconButton} ${styles.sortConfirmButton}`}
        disabled={saving}
        icon={<CheckOutlined />}
        loading={saving}
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => void commit()}
        size="small"
        type="text"
      />
      <Button
        aria-label="取消排序编辑"
        className={`${styles.sortIconButton} ${styles.sortCancelButton}`}
        disabled={saving}
        icon={<CloseOutlined />}
        onMouseDown={(event) => event.preventDefault()}
        onClick={cancel}
        size="small"
        type="text"
      />
    </div>
  );
}

export function createCaseColumns({
  writable,
  editingSortId,
  sortingId,
  onStartSort,
  onFinishSort,
  onReorder,
  onEdit,
  onDelete,
}: CreateCaseColumnsOptions): ColumnType<FeaturedCase>[] {
  return [
    {
      title: "机构",
      dataIndex: "bbk_id",
      key: "bbk_id",
      width: 120,
      render: (bbkId: string | null) => {
        const org = BBK_ID_MAP.find((item) => item.value === bbkId);
        return org
          ? org.label
          : bbkId || <span className={styles.mutedValue}>-</span>;
      },
    },
    {
      title: "标题",
      dataIndex: "label",
      key: "label",
      ellipsis: true,
    },
    {
      title: "排序",
      dataIndex: "sort_order",
      key: "sort_order",
      width: 150,
      render: (_, record) => (
        <SortOrderCell
          caseItem={record}
          disabled={
            !writable || (sortingId !== null && sortingId !== record.id)
          }
          editing={editingSortId === record.id}
          onFinish={onFinishSort}
          onSave={(sortOrder) => onReorder(record, sortOrder)}
          onStart={() => onStartSort(record)}
          saving={sortingId === record.id}
        />
      ),
    },
    {
      title: "状态",
      dataIndex: "is_active",
      key: "is_active",
      width: 80,
      render: (active: boolean) =>
        active ? (
          <span className={styles.activeStatus}>启用</span>
        ) : (
          <span className={styles.inactiveStatus}>禁用</span>
        ),
    },
    {
      title: "操作",
      key: "action",
      width: 120,
      render: (_, record) =>
        writable ? (
          <span>
            <a onClick={() => onEdit(record)} className={styles.editAction}>
              编辑
            </a>
            <a
              onClick={() => onDelete(record.id)}
              className={styles.deleteAction}
            >
              删除
            </a>
          </span>
        ) : (
          <span className={styles.readOnlyAction}>仅查看</span>
        ),
    },
  ];
}
