import dayjs from "dayjs";
import type {
  CronDispatchCapacityItem,
  CronDispatchWorkersResponse,
} from "../../../api/modules/monitor";

export function workerSampleRows(record: CronDispatchCapacityItem) {
  const {
    success_count: success,
    failure_count: failure,
    subtask_success_count: subtaskSuccess,
    subtask_failure_count: subtaskFailure,
  } = record;
  const hasBreakdown = subtaskSuccess != null && subtaskFailure != null;
  return [
    [
      "主任务 成功 / 失败",
      hasBreakdown
        ? `${success - subtaskSuccess} / ${failure - subtaskFailure}`
        : "—",
    ],
    [
      "子任务 成功 / 失败",
      hasBreakdown ? `${subtaskSuccess} / ${subtaskFailure}` : "—",
    ],
    ["合计 成功 / 失败", `${success} / ${failure}`],
  ];
}

export async function loadWorkerHistory(
  loadPage: (cursor?: string) => Promise<CronDispatchWorkersResponse>,
  isCurrent: () => boolean,
  onProgress: (count: number) => void = () => {},
): Promise<CronDispatchWorkersResponse | null> {
  let first: CronDispatchWorkersResponse | undefined;
  let cursor: string | undefined;
  const seen = new Set<string>();
  const records = new Map<number, CronDispatchCapacityItem>();
  do {
    if (!isCurrent()) return null;
    const page = await loadPage(cursor);
    if (!isCurrent()) return null;
    first ??= page;
    if (page.source_id !== first.source_id)
      throw new Error("Worker 历史渠道不一致，请刷新");
    for (const row of page.capacity_events) records.set(row.id, row);
    onProgress(records.size);
    cursor = page.capacity_events_next_cursor || undefined;
    if (cursor && seen.has(cursor))
      throw new Error("Worker 历史分页未推进，请刷新");
    if (cursor) seen.add(cursor);
  } while (cursor);
  return {
    ...first!,
    capacity_events: [...records.values()],
    capacity_events_next_cursor: null,
  };
}

export interface WorkerPoint {
  value: [number, number | null];
  record: CronDispatchCapacityItem;
}

const baselineDecisions = new Set([
  "initial_capacity",
  "idle_reset",
  "baseline_start",
]);

export function sampledOccupancy(record: CronDispatchCapacityItem) {
  const { claimed_count, running_count, decision_reason } = record;
  if (
    baselineDecisions.has(decision_reason) ||
    !Number.isInteger(claimed_count) ||
    !Number.isInteger(running_count) ||
    claimed_count < 0 ||
    running_count < 0
  )
    return null;
  return claimed_count + running_count;
}

export function buildWorkerSeries(
  items: CronDispatchCapacityItem[],
  showOccupancy = false,
) {
  const groups = new Map<string, { name: string; data: WorkerPoint[] }>();
  for (const record of items) {
    const time = record.created_at ? dayjs(record.created_at).valueOf() : NaN;
    if (!Number.isFinite(time) || !Number.isFinite(record.effective_workers))
      continue;
    const key = JSON.stringify([record.provider_id, record.model_id]);
    const group = groups.get(key) || {
      name: `${record.provider_id} / ${record.model_id}`,
      data: [],
    };
    group.data.push({ value: [time, record.effective_workers], record });
    groups.set(key, group);
  }
  return [...groups]
    .sort(([a], [b]) => a.localeCompare(b))
    .flatMap(([id, group]) => {
      const data = group.data.sort(
        (a, b) => a.value[0] - b.value[0] || a.record.id - b.record.id,
      );
      const capacity = {
        id,
        name: showOccupancy ? "有效 Worker" : group.name,
        type: "line" as const,
        step: "end" as const,
        showSymbol: data.length <= 30,
        data,
      };
      if (!showOccupancy) return [capacity];
      return [
        capacity,
        {
          ...capacity,
          id: `${id}:occupied`,
          name: "占用 Worker",
          step: undefined,
          connectNulls: false,
          lineStyle: { type: "dashed" as const },
          data: data.map(
            (point): WorkerPoint => ({
              ...point,
              value: [point.value[0], sampledOccupancy(point.record)],
            }),
          ),
        },
      ];
    });
}
