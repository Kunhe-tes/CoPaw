import type { CronJobSpecOutput } from "@/api/types";
import {
  getTaskNextRunText,
  getTaskSidebarMeta,
  TASK_COMPLETED_STATUS_TEXT,
  type TaskSidebarMeta,
} from "./taskJobs";
import { formatListTime } from "./listTimeFormat";

export interface TaskDisplayMeta {
  title: string;
  sidebarMeta: TaskSidebarMeta;
  nextRunText: string | null;
  completionText: string | null;
  statusText: string | null;
  stateLabel: string;
  hasActions: boolean;
}

export interface TaskAggregateMeta {
  total: number;
  unreadCount: number;
  runningCount: number;
  pausedCount: number;
}

export function getTaskDisplayMeta(task: CronJobSpecOutput): TaskDisplayMeta {
  const sidebarMeta = getTaskSidebarMeta(task);
  const nextRunText = getTaskNextRunText(task);
  const lastRunAt = task.task?.last_scheduled_run_at;
  const completionText =
    task.task?.latest_scheduled_preview || lastRunAt
      ? `${lastRunAt ? `${formatListTime(lastRunAt)} ` : ""}${TASK_COMPLETED_STATUS_TEXT}`
      : null;
  const statusText =
    sidebarMeta.state === "auto-paused"
      ? `已自动暂停 · 连续 ${sidebarMeta.unreadCount} 次未读`
      : sidebarMeta.state === "manual-paused"
        ? "已手动暂停"
        : sidebarMeta.state === "running"
          ? "运行中"
          : null;
  const stateLabel =
    sidebarMeta.state === "auto-paused"
      ? "自动暂停"
      : sidebarMeta.state === "manual-paused"
        ? "已暂停"
        : sidebarMeta.state === "running"
          ? "运行中"
          : "进行中";

  return {
    title: task.name || task.id,
    sidebarMeta,
    nextRunText,
    completionText,
    statusText,
    stateLabel,
    hasActions:
      sidebarMeta.canPause ||
      sidebarMeta.canRun ||
      sidebarMeta.canResume ||
      sidebarMeta.canDelete,
  };
}

export function getTaskAggregateMeta(
  tasks: CronJobSpecOutput[],
): TaskAggregateMeta {
  return tasks.reduce<TaskAggregateMeta>(
    (summary, task) => {
      const meta = getTaskSidebarMeta(task);
      summary.total += 1;
      summary.unreadCount += meta.unreadCount;
      if (meta.state === "running") {
        summary.runningCount += 1;
      }
      if (meta.state === "manual-paused" || meta.state === "auto-paused") {
        summary.pausedCount += 1;
      }
      return summary;
    },
    {
      total: 0,
      unreadCount: 0,
      runningCount: 0,
      pausedCount: 0,
    },
  );
}

export function formatTaskBadgeCount(count: number): string {
  return count > 99 ? "99+" : String(count);
}
