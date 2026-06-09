import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CronJobSpecOutput } from "@/api/types";
import ChatTaskEntry from "./ChatTaskEntry";

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

describe("ChatTaskEntry", () => {
  afterEach(() => {
    cleanup();
  });

  it("shows aggregate task count and state summary", () => {
    render(
      <ChatTaskEntry
        open={false}
        onToggle={vi.fn()}
        tasks={[
          taskJob({
            id: "job-running",
            task: {
              visible_in_my_tasks: true,
              has_scheduled_result: false,
              latest_scheduled_preview: "",
              unread_execution_count: 2,
              is_running: true,
              is_paused: false,
              pause_reason: null,
            },
          }),
          taskJob({
            id: "job-paused",
            task: {
              visible_in_my_tasks: true,
              has_scheduled_result: false,
              latest_scheduled_preview: "",
              unread_execution_count: 1,
              is_running: false,
              is_paused: true,
              pause_reason: "manual",
            },
          }),
        ]}
      />,
    );

    expect(screen.getByText("我的任务")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("运行中 1 · 未读 3 · 暂停 1")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("toggles header tabs without selecting a task", () => {
    const onToggle = vi.fn();
    render(
      <ChatTaskEntry
        open={false}
        onToggle={onToggle}
        tasks={[taskJob()]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /我的任务/ }));

    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("shows neutral empty state", () => {
    render(<ChatTaskEntry open={false} onToggle={vi.fn()} tasks={[]} />);

    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("暂无任务")).toBeInTheDocument();
  });
});
