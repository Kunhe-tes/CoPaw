import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { CronJobSpecOutput } from "@/api/types";
import Style from "./style";
import TaskActionMenu from "../TaskActionMenu";
import {
  formatTaskBadgeCount,
  getTaskDisplayMeta,
} from "../../taskDisplay";

export interface ChatTaskTabsProps {
  visible: boolean;
  tasks: CronJobSpecOutput[];
  selectedTaskId?: string;
  onTaskClick?: (task: CronJobSpecOutput) => void;
  onTaskPause?: (task: CronJobSpecOutput) => void;
  onTaskRun?: (task: CronJobSpecOutput) => void;
  onTaskResume?: (task: CronJobSpecOutput) => void;
  onTaskDelete?: (task: CronJobSpecOutput) => void;
}

function handleKeyboardActivate(
  event: KeyboardEvent<HTMLDivElement>,
  onActivate: () => void,
) {
  if (event.key !== "Enter" && event.key !== " ") {
    return;
  }
  event.preventDefault();
  onActivate();
}

function buildTabTitle(meta: ReturnType<typeof getTaskDisplayMeta>): string {
  return [
    meta.title,
    meta.statusText,
    meta.completionText,
    meta.nextRunText,
  ]
    .filter(Boolean)
    .join("\n");
}

export default function ChatTaskTabs({
  visible,
  tasks,
  selectedTaskId,
  onTaskClick,
  onTaskPause,
  onTaskRun,
  onTaskResume,
  onTaskDelete,
}: ChatTaskTabsProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [overflowState, setOverflowState] = useState({
    canScrollLeft: false,
    canScrollRight: false,
  });

  const updateOverflowState = useCallback(() => {
    const node = scrollRef.current;
    if (!node) {
      setOverflowState({ canScrollLeft: false, canScrollRight: false });
      return;
    }

    const maxScrollLeft = node.scrollWidth - node.clientWidth;
    setOverflowState({
      canScrollLeft: node.scrollLeft > 1,
      canScrollRight: node.scrollLeft < maxScrollLeft - 1,
    });
  }, []);

  useEffect(() => {
    if (!visible) return;

    const node = scrollRef.current;
    if (!node) return;

    updateOverflowState();
    const resizeObserver =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(updateOverflowState);
    resizeObserver?.observe(node);
    window.addEventListener("resize", updateOverflowState);

    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener("resize", updateOverflowState);
    };
  }, [tasks.length, updateOverflowState, visible]);

  const handleScrollBy = useCallback((direction: "left" | "right") => {
    const node = scrollRef.current;
    if (!node) return;

    node.scrollBy({
      left: direction === "left" ? -260 : 260,
      behavior: "smooth",
    });
  }, []);

  if (!visible) {
    return <Style />;
  }
  const hasSelectedTask = tasks.some((task) => task.id === selectedTaskId);

  return (
    <>
      <Style />
      <div
        className={`chat-task-tabs-shell${
          hasSelectedTask ? " chat-task-tabs--has-selection" : " chat-task-tabs--idle"
        }`}
      >
        <div className="chat-task-tabs-label" aria-hidden="true">
          我的任务
        </div>
        <div
          className={`chat-task-tabs-viewport${
            overflowState.canScrollLeft ? " chat-task-tabs-viewport--left" : ""
          }${
            overflowState.canScrollRight ? " chat-task-tabs-viewport--right" : ""
          }`}
        >
          {overflowState.canScrollLeft && (
            <button
              type="button"
              className="chat-task-tabs-scroll chat-task-tabs-scroll--left"
              onClick={() => handleScrollBy("left")}
              aria-label="向左滚动任务标签"
            >
              <ChevronLeft size={15} strokeWidth={2.2} />
            </button>
          )}
          <div
            ref={scrollRef}
            className="chat-task-tabs"
            role="tablist"
            aria-label="我的任务"
            onScroll={updateOverflowState}
          >
            {tasks.length === 0 ? (
              <div className="chat-task-tabs-empty">暂无任务</div>
            ) : (
              tasks.map((task) => {
                const meta = getTaskDisplayMeta(task);
                const selected = task.id === selectedTaskId;
                const canShowActions = meta.hasActions;
                const openTask = () => onTaskClick?.(task);

                return (
                  <div
                    key={task.id}
                    className={`chat-task-tab chat-task-tab--${meta.sidebarMeta.state}${
                      selected ? " chat-task-tab--selected" : ""
                    }`}
                    role="tab"
                    aria-selected={selected}
                    tabIndex={0}
                    title={buildTabTitle(meta)}
                    aria-label={`任务：${meta.title}，${meta.stateLabel}`}
                    onClick={openTask}
                    onKeyDown={(event) => handleKeyboardActivate(event, openTask)}
                    data-testid="chat-task-tab"
                  >
                    <span className="chat-task-tab-state" aria-hidden="true" />
                    <span className="chat-task-tab-title">{meta.title}</span>
                    {meta.sidebarMeta.unreadCount > 0 && (
                      <span className="chat-task-tab-badge">
                        {formatTaskBadgeCount(meta.sidebarMeta.unreadCount)}
                      </span>
                    )}
                    {(meta.sidebarMeta.state === "running" ||
                      meta.sidebarMeta.state === "manual-paused" ||
                      meta.sidebarMeta.state === "auto-paused") && (
                      <span className="chat-task-tab-status">
                        {meta.stateLabel}
                      </span>
                    )}
                    {canShowActions && (
                      <span
                        className="chat-task-tab-actions"
                        onClick={(event) => event.stopPropagation()}
                        onKeyDown={(event) => event.stopPropagation()}
                      >
                        <TaskActionMenu
                          task={task}
                          sidebarMeta={meta.sidebarMeta}
                          classNamePrefix="chat-task-tab"
                          onTaskPause={onTaskPause}
                          onTaskRun={onTaskRun}
                          onTaskResume={onTaskResume}
                          onTaskDelete={onTaskDelete}
                        />
                      </span>
                    )}
                  </div>
                );
              })
            )}
          </div>
          {overflowState.canScrollRight && (
            <button
              type="button"
              className="chat-task-tabs-scroll chat-task-tabs-scroll--right"
              onClick={() => handleScrollBy("right")}
              aria-label="向右滚动任务标签"
            >
              <ChevronRight size={15} strokeWidth={2.2} />
            </button>
          )}
        </div>
      </div>
    </>
  );
}
