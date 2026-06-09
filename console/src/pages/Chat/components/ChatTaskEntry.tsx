import type { CronJobSpecOutput } from "@/api/types";
import { TasksIconSmall } from "./ChatSidebar/CollapsedToolbar/icons";
import { formatTaskBadgeCount, getTaskAggregateMeta } from "../taskDisplay";

export interface ChatTaskEntryProps {
  tasks: CronJobSpecOutput[];
  open: boolean;
  onToggle: () => void;
}

function buildSummary(tasks: CronJobSpecOutput[]): string {
  const summary = getTaskAggregateMeta(tasks);
  if (summary.total === 0) {
    return "暂无任务";
  }

  const parts: string[] = [];
  if (summary.runningCount > 0) {
    parts.push(`运行中 ${summary.runningCount}`);
  }
  if (summary.unreadCount > 0) {
    parts.push(`未读 ${summary.unreadCount}`);
  }
  if (summary.pausedCount > 0) {
    parts.push(`暂停 ${summary.pausedCount}`);
  }

  return parts.length ? parts.join(" · ") : "全部任务正常";
}

export default function ChatTaskEntry({
  tasks,
  open,
  onToggle,
}: ChatTaskEntryProps) {
  const summary = getTaskAggregateMeta(tasks);
  const summaryText = buildSummary(tasks);

  return (
    <div className="chat-task-entry">
      <button
        type="button"
        className={`chat-task-entry-card${
          open ? " chat-task-entry-card--open" : ""
        }`}
        onClick={onToggle}
        aria-expanded={open}
        aria-label={`我的任务，${summary.total} 个，${summaryText}`}
      >
        <span className="chat-task-entry-leading">
          <span className="chat-task-entry-icon">
            <TasksIconSmall active={open} />
          </span>
          <span className="chat-task-entry-copy">
            <span className="chat-task-entry-title-row">
              <span className="chat-task-entry-title">我的任务</span>
              <span className="chat-task-entry-count">
                {summary.total}
              </span>
            </span>
            <span className="chat-task-entry-summary">{summaryText}</span>
          </span>
        </span>
        <span className="chat-task-entry-trailing">
          {summary.unreadCount > 0 && (
            <span className="chat-task-entry-badge">
              {formatTaskBadgeCount(summary.unreadCount)}
            </span>
          )}
          <span
            className={`chat-task-entry-chevron${
              open ? " chat-task-entry-chevron--open" : ""
            }`}
            aria-hidden="true"
          >
            ›
          </span>
        </span>
      </button>
    </div>
  );
}
