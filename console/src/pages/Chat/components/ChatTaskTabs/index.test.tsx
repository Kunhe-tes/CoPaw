import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CronJobSpecOutput } from "@/api/types";
import ChatTaskTabs from ".";

function taskJob(
  overrides: Partial<CronJobSpecOutput> = {},
): CronJobSpecOutput {
  return {
    id: "job-1",
    name: "每日巡检",
    enabled: true,
    schedule: {
      type: "cron",
      cron: "0 9 * * *",
      timezone: "Asia/Shanghai",
    },
    task_type: "agent",
    request: {
      input: [{ role: "user", content: "ping" }],
    },
    dispatch: {
      type: "channel",
      channel: "console",
      target: {
        user_id: "user-1",
        session_id: "session-1",
      },
    },
    task: {
      visible_in_my_tasks: true,
      has_scheduled_result: false,
      latest_scheduled_preview: "",
      unread_execution_count: 0,
      is_running: false,
      is_paused: false,
      pause_reason: null,
    },
    ...overrides,
  };
}

describe("ChatTaskTabs", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders selected, unread, paused, and running task states", () => {
    render(
      <ChatTaskTabs
        visible
        selectedTaskId="job-1"
        tasks={[
          taskJob({
            id: "job-1",
            name: "每日巡检",
            task: {
              visible_in_my_tasks: true,
              has_scheduled_result: true,
              latest_scheduled_preview: "result",
              unread_execution_count: 5,
              is_running: false,
              is_paused: false,
              pause_reason: null,
            },
          }),
          taskJob({
            id: "job-paused",
            name: "内容跟进",
            task: {
              visible_in_my_tasks: true,
              has_scheduled_result: false,
              latest_scheduled_preview: "",
              unread_execution_count: 0,
              is_running: false,
              is_paused: true,
              pause_reason: "manual",
            },
          }),
          taskJob({
            id: "job-running",
            name: "线索日报",
            task: {
              visible_in_my_tasks: true,
              has_scheduled_result: false,
              latest_scheduled_preview: "",
              unread_execution_count: 0,
              is_running: true,
              is_paused: false,
              pause_reason: null,
            },
          }),
        ]}
      />,
    );

    expect(screen.getByRole("tab", { name: /每日巡检/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("已暂停")).toBeInTheDocument();
    expect(screen.getByText("运行中")).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: /每日巡检/ }),
    ).toHaveAttribute("title", expect.stringContaining("已完成"));
  });

  it("calls task click when a tab is selected by mouse or keyboard", () => {
    const onTaskClick = vi.fn();
    const task = taskJob();

    render(
      <ChatTaskTabs visible tasks={[task]} onTaskClick={onTaskClick} />,
    );

    const tab = screen.getByRole("tab", { name: /每日巡检/ });
    fireEvent.click(tab);
    fireEvent.keyDown(tab, { key: "Enter" });

    expect(onTaskClick).toHaveBeenCalledTimes(2);
    expect(onTaskClick).toHaveBeenCalledWith(task);
  });

  it("runs task action without triggering tab navigation", async () => {
    const onTaskClick = vi.fn();
    const onTaskRun = vi.fn();
    const task = taskJob();

    render(
      <ChatTaskTabs
        visible
        tasks={[task]}
        onTaskClick={onTaskClick}
        onTaskRun={onTaskRun}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "更多任务操作：每日巡检" }),
    );
    fireEvent.click(await screen.findByText("执行"));

    await waitFor(() => {
      expect(onTaskRun).toHaveBeenCalledWith(task);
    });
    expect(onTaskClick).not.toHaveBeenCalled();
  });

  it("shows an empty state when visible without tasks", () => {
    render(<ChatTaskTabs visible tasks={[]} />);

    expect(screen.getByText("暂无任务")).toBeInTheDocument();
  });

  it("does not render tabs when hidden", () => {
    render(<ChatTaskTabs visible={false} tasks={[taskJob()]} />);

    expect(screen.queryByRole("tab")).toBeNull();
  });
});
