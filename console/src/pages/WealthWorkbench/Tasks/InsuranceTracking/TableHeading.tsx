import { Dropdown } from "antd";
import { ArrowDown, ArrowUp, ArrowUpDown, Filter } from "lucide-react";
import { INTENTION_LABELS, type Intention } from "./api";
import type { ListSort, SortKey } from "./listOrder";
import workbenchStyles from "../../index.module.less";
import styles from "./index.module.less";

export function TableHeading({
  label,
  sort,
  onSort,
  intention,
  onIntention,
}: {
  label: string;
  sort: ListSort;
  onSort: (key: SortKey) => void;
  intention: Intention | "all";
  onIntention: (value: Intention | "all") => void;
}) {
  const key =
    label === "资产" ? "assets" : label === "接触计划" ? "contactPlan" : null;
  if (key) {
    const direction = sort?.key === key ? sort.direction : null;
    const SortIcon =
      direction === "asc"
        ? ArrowUp
        : direction === "desc"
        ? ArrowDown
        : ArrowUpDown;
    return (
      <th
        scope="col"
        aria-sort={
          direction === "asc"
            ? "ascending"
            : direction === "desc"
            ? "descending"
            : "none"
        }
      >
        <button
          type="button"
          className={styles.sortTrigger}
          title={
            key === "assets" ? "按资产金额排序" : "按最新一条接触计划的日期排序"
          }
          aria-label={`${label}排序，当前${
            direction === "asc"
              ? "升序"
              : direction === "desc"
              ? "降序"
              : "默认顺序"
          }`}
          onClick={() => onSort(key)}
        >
          {label}
          <SortIcon size={14} aria-hidden />
        </button>
      </th>
    );
  }
  if (label !== "客户意向度") return <th scope="col">{label}</th>;
  return (
    <th scope="col">
      <Dropdown
        trigger={["click"]}
        menu={{
          selectable: true,
          selectedKeys: [String(intention)],
          items: [
            { key: "all", label: "全部意向度" },
            ...Object.entries(INTENTION_LABELS).map(([key, value]) => ({
              key,
              label: value,
            })),
          ],
          onClick: ({ key }) =>
            onIntention(key === "all" ? "all" : (Number(key) as Intention)),
        }}
      >
        <button
          type="button"
          className={`${workbenchStyles.tagFilterTrigger} ${
            intention !== "all" ? workbenchStyles.filtered : ""
          }`}
          aria-label="筛选客户意向度"
        >
          {label}
          <Filter size={14} aria-hidden />
        </button>
      </Dropdown>
      {intention !== "all" && (
        <div className={workbenchStyles.tagFilterApplied}>
          <span>{INTENTION_LABELS[intention]}</span>
          <button
            type="button"
            aria-label="清除客户意向度筛选"
            onClick={() => onIntention("all")}
          >
            ×
          </button>
        </div>
      )}
    </th>
  );
}
