import React from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { emitSubAgentRunsRefreshIfPresent } from "../../subAgentRunEvents";
import SubAgentRunMonitor, { SUBAGENT_RUNS_REFRESH_EVENT } from "./index";

const mocks = vi.hoisted(() => ({
  getSubAgentRuns: vi.fn(),
  cancelSubAgentRun: vi.fn(),
  messageError: vi.fn(),
}));

vi.mock("../../../../api/modules/chat", () => ({
  chatApi: {
    getSubAgentRuns: mocks.getSubAgentRuns,
    cancelSubAgentRun: mocks.cancelSubAgentRun,
  },
}));

vi.mock("../../../../hooks/useAppMessage", () => ({
  useAppMessage: () => ({
    message: {
      error: mocks.messageError,
    },
  }),
}));

function snapshot(runs: Array<Record<string, unknown>>) {
  return {
    chat_id: "chat-1",
    session_id: "session-1",
    runs,
  };
}

function run(overrides: Record<string, unknown> = {}) {
  return {
    run_id: "subagent-1",
    agent_name: "plan-researcher",
    objective: "Inspect repository",
    status: "running",
    stoppable: true,
    budget_consumption: {
      elapsed_ms: 30_000,
      timeout_ms: 120_000,
      turns_used: 2,
      max_turns: 4,
      ratio: 0.25,
    },
    created_at: "2026-07-05T00:00:00+00:00",
    started_at: "2026-07-05T00:00:01+00:00",
    finished_at: null,
    duration_ms: 30_000,
    summary_preview: null,
    error_preview: null,
    ...overrides,
  };
}

function deferredSnapshot() {
  let resolve!: (value: ReturnType<typeof snapshot>) => void;
  const promise = new Promise<ReturnType<typeof snapshot>>((next) => {
    resolve = next;
  });
  return { promise, resolve };
}

describe("SubAgentRunMonitor", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.useRealTimers();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  async function flushPromises() {
    await act(async () => {
      await Promise.resolve();
    });
  }

  it("does not render when snapshot has no runs", async () => {
    mocks.getSubAgentRuns.mockResolvedValueOnce(snapshot([]));

    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);

    await waitFor(() => {
      expect(mocks.getSubAgentRuns).toHaveBeenCalledWith(
        "chat-1",
        expect.any(AbortSignal),
      );
    });
    expect(screen.queryByRole("button", { name: /助手/i })).toBeNull();
  });

  it("polls every 10 seconds while non-terminal runs exist", async () => {
    vi.useFakeTimers();
    mocks.getSubAgentRuns.mockResolvedValue(snapshot([run()]));

    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await flushPromises();
    const trigger = screen.getByRole("button", { name: "助手运行状态" });
    expect(trigger).not.toHaveTextContent("个助手运行中");
    expect(trigger).not.toHaveTextContent("查看助手状态");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(2);
  });

  it("stops polling after all runs are terminal", async () => {
    vi.useFakeTimers();
    mocks.getSubAgentRuns.mockResolvedValue(
      snapshot([run({ status: "completed", stoppable: false })]),
    );

    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await flushPromises();
    screen.getByRole("button", { name: "助手运行状态" });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(1);
  });

  it("refreshes immediately when stream event requests refresh", async () => {
    mocks.getSubAgentRuns.mockResolvedValue(snapshot([run()]));

    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await screen.findByRole("button", { name: "助手运行状态" });

    await act(async () => {
      document.dispatchEvent(new CustomEvent(SUBAGENT_RUNS_REFRESH_EVENT));
    });

    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(2);
  });

  it("confirms an immediate stream refresh after the run record is written", async () => {
    vi.useFakeTimers();
    mocks.getSubAgentRuns.mockResolvedValue(snapshot([run()]));

    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await flushPromises();

    await act(async () => {
      document.dispatchEvent(new CustomEvent(SUBAGENT_RUNS_REFRESH_EVENT));
    });
    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(3);
  });

  it("hides only terminal runs and retains active runs across resets", async () => {
    vi.useFakeTimers();
    const completed = run({
      run_id: "old",
      agent_name: "old-agent",
      status: "completed",
    });
    const active = run({ run_id: "active", agent_name: "active-agent" });
    mocks.getSubAgentRuns.mockResolvedValue(snapshot([completed, active]));
    const { rerender } = render(
      <SubAgentRunMonitor chatId="chat-1" resetKey={0} />,
    );
    await flushPromises();
    rerender(<SubAgentRunMonitor chatId="chat-1" resetKey={1} />);
    await flushPromises();
    fireEvent.click(screen.getByRole("button", { name: "助手运行状态" }));
    expect(screen.queryByText("old-agent")).toBeNull();
    expect(screen.getByText("active-agent")).toBeInTheDocument();
    mocks.getSubAgentRuns.mockResolvedValue(
      snapshot([completed, { ...active, status: "completed" }]),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(screen.getByText("active-agent")).toBeInTheDocument();
    expect(screen.getByText("已完成")).toBeInTheDocument();
    const calls = mocks.getSubAgentRuns.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(calls);
  });

  it("accepts same-chat in-flight snapshots after a turn reset", async () => {
    const pending = deferredSnapshot();
    const oldRun = run({
      run_id: "old",
      agent_name: "old-agent",
      status: "completed",
    });
    mocks.getSubAgentRuns
      .mockResolvedValueOnce(snapshot([oldRun]))
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValue(snapshot([oldRun, run({ agent_name: "new-agent" })]));
    const { rerender } = render(
      <SubAgentRunMonitor chatId="chat-1" resetKey={0} />,
    );
    await flushPromises();
    await act(async () => {
      document.dispatchEvent(new CustomEvent(SUBAGENT_RUNS_REFRESH_EVENT));
    });
    rerender(<SubAgentRunMonitor chatId="chat-1" resetKey={1} />);
    await act(async () => {
      pending.resolve(snapshot([oldRun, run({ agent_name: "new-agent" })]));
    });
    fireEvent.click(screen.getByRole("button", { name: "助手运行状态" }));
    expect(screen.queryByText("old-agent")).toBeNull();
    expect(screen.getByText("new-agent")).toBeInTheDocument();
  });

  it.each(["pending", "running", "paused"])(
    "continues polling %s runs after reset",
    async (status) => {
      vi.useFakeTimers();
      mocks.getSubAgentRuns.mockResolvedValue(snapshot([run({ status })]));
      const { rerender } = render(
        <SubAgentRunMonitor chatId="chat-1" resetKey={0} />,
      );
      await flushPromises();
      rerender(<SubAgentRunMonitor chatId="chat-1" resetKey={1} />);
      await flushPromises();
      expect(
        screen.getByRole("button", { name: "助手运行状态" }),
      ).toBeInTheDocument();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
      });
      expect(mocks.getSubAgentRuns.mock.calls.length).toBeGreaterThanOrEqual(3);
    },
  );

  it("preserves the last status and retries after transient failure", async () => {
    vi.useFakeTimers();
    mocks.getSubAgentRuns
      .mockResolvedValueOnce(snapshot([run()]))
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValue(snapshot([run({ status: "completed" })]));
    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await flushPromises();
    fireEvent.click(screen.getByRole("button", { name: "助手运行状态" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(screen.getByText("运行中")).toBeInTheDocument();
    expect(screen.getByText("状态刷新失败，正在重试")).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(screen.getByText("已完成")).toBeInTheDocument();
    expect(screen.queryByText("状态刷新失败，正在重试")).toBeNull();
  });

  it("retries an initially failed query without a stream event", async () => {
    vi.useFakeTimers();
    mocks.getSubAgentRuns
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValue(snapshot([run()]));
    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await flushPromises();
    expect(screen.getByRole("status")).toHaveTextContent(
      "状态刷新失败，正在重试",
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(
      screen.getByRole("button", { name: "助手运行状态" }),
    ).toBeInTheDocument();
  });

  it.each([null, "chat-2"])(
    "ignores late responses after switching to %s",
    async (nextChat) => {
      const pending = deferredSnapshot();
      mocks.getSubAgentRuns
        .mockReturnValueOnce(pending.promise)
        .mockResolvedValue({
          chat_id: "chat-2",
          session_id: "session-2",
          runs: [],
        });
      const { rerender } = render(
        <SubAgentRunMonitor chatId="chat-1" resetKey={0} />,
      );
      rerender(<SubAgentRunMonitor chatId={nextChat} resetKey={0} />);
      await act(async () => {
        pending.resolve(snapshot([run()]));
      });
      expect(screen.queryByRole("button", { name: "助手运行状态" })).toBeNull();
      expect(mocks.getSubAgentRuns.mock.calls[0][1]?.aborted).toBe(true);
    },
  );

  it("coalesces stream refreshes while a query is pending", async () => {
    const pending = deferredSnapshot();
    mocks.getSubAgentRuns
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValue(snapshot([run()]));
    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await act(async () => {
      for (let i = 0; i < 5; i++)
        document.dispatchEvent(new CustomEvent(SUBAGENT_RUNS_REFRESH_EVENT));
    });
    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(1);
    await act(async () => {
      pending.resolve(snapshot([run()]));
    });
    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(2);
    expect(
      screen.getByRole("button", { name: "助手运行状态" }),
    ).toBeInTheDocument();
  });

  it("retries a hung query after aborting it on timeout", async () => {
    vi.useFakeTimers();
    mocks.getSubAgentRuns
      .mockReturnValueOnce(new Promise(() => {}))
      .mockResolvedValue(snapshot([run()]));
    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(mocks.getSubAgentRuns.mock.calls[0][1]?.aborted).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(
      screen.getByRole("button", { name: "助手运行状态" }),
    ).toBeInTheDocument();
  });

  it("discovers runs written after the 400ms confirmation", async () => {
    vi.useFakeTimers();
    mocks.getSubAgentRuns.mockResolvedValue(snapshot([]));
    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await flushPromises();
    await act(async () => {
      document.dispatchEvent(new CustomEvent(SUBAGENT_RUNS_REFRESH_EVENT));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    mocks.getSubAgentRuns.mockResolvedValue(
      snapshot([run({ status: "completed" })]),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(
      screen.getByRole("button", { name: "助手运行状态" }),
    ).toBeInTheDocument();
  });

  it("ends the discovery window if no run was created", async () => {
    vi.useFakeTimers();
    mocks.getSubAgentRuns.mockResolvedValue(snapshot([]));
    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await flushPromises();
    await act(async () => {
      document.dispatchEvent(new CustomEvent(SUBAGENT_RUNS_REFRESH_EVENT));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(40_000);
    });
    expect(mocks.getSubAgentRuns.mock.calls.length).toBeGreaterThan(3);
    const calls = mocks.getSubAgentRuns.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(40_000);
    });
    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(calls);
  });

  it("discovers a streamed tool run and polls until terminal", async () => {
    vi.useFakeTimers();
    mocks.getSubAgentRuns
      .mockResolvedValueOnce(snapshot([]))
      .mockResolvedValueOnce(snapshot([run()]))
      .mockResolvedValueOnce(snapshot([run()]))
      .mockResolvedValue(snapshot([run({ status: "completed" })]));
    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await flushPromises();
    await act(async () => {
      emitSubAgentRunsRefreshIfPresent(
        {
          object: "message",
          type: "plugin_call_output",
          content: [
            {
              object: "content",
              type: "data",
              data: { name: "start_subagent", output: "accepted" },
            },
          ],
        },
        "chat-1",
      );
    });
    fireEvent.click(screen.getByRole("button", { name: "助手运行状态" }));
    expect(screen.getByText("运行中")).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_400);
    });
    expect(screen.getByText("已完成")).toBeInTheDocument();
    const calls = mocks.getSubAgentRuns.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(calls);
  });

  it("ignores refresh events belonging to another chat", async () => {
    vi.useFakeTimers();
    mocks.getSubAgentRuns.mockResolvedValue(snapshot([]));
    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await flushPromises();
    await act(async () => {
      emitSubAgentRunsRefreshIfPresent("start_subagent", "chat-2");
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(40_000);
    });
    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(1);
  });

  it("does not open a discovery window for wait/get/cancel events", async () => {
    vi.useFakeTimers();
    mocks.getSubAgentRuns.mockResolvedValue(snapshot([]));
    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await flushPromises();
    for (const name of ["wait_subagent", "get_subagent", "cancel_subagent"]) {
      await act(async () => {
        emitSubAgentRunsRefreshIfPresent(name, "chat-1");
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(400);
      });
    }
    const calls = mocks.getSubAgentRuns.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(40_000);
    });
    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(calls);
  });

  it("rejects snapshots for a different chat and retries", async () => {
    vi.useFakeTimers();
    mocks.getSubAgentRuns
      .mockResolvedValueOnce({ ...snapshot([run()]), chat_id: "chat-2" })
      .mockResolvedValue(snapshot([run({ agent_name: "correct-chat" })]));
    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await flushPromises();
    expect(screen.queryByRole("button", { name: "助手运行状态" })).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("状态刷新失败");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    fireEvent.click(screen.getByRole("button", { name: "助手运行状态" }));
    expect(screen.getByText("correct-chat")).toBeInTheDocument();
  });

  it("ignores an old lifecycle after switching A to B to A", async () => {
    const pending = deferredSnapshot();
    mocks.getSubAgentRuns
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce({ ...snapshot([]), chat_id: "chat-2" })
      .mockResolvedValue(snapshot([run({ agent_name: "current-lifecycle" })]));
    const { rerender } = render(
      <SubAgentRunMonitor chatId="chat-1" resetKey={0} />,
    );
    rerender(<SubAgentRunMonitor chatId="chat-2" resetKey={0} />);
    await flushPromises();
    rerender(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await flushPromises();
    await act(async () => {
      pending.resolve(snapshot([run({ agent_name: "stale-lifecycle" })]));
    });
    fireEvent.click(screen.getByRole("button", { name: "助手运行状态" }));
    expect(screen.getByText("current-lifecycle")).toBeInTheDocument();
    expect(screen.queryByText("stale-lifecycle")).toBeNull();
  });

  it("aborts requests and clears retries on unmount in StrictMode", async () => {
    vi.useFakeTimers();
    mocks.getSubAgentRuns.mockReturnValue(new Promise(() => {}));
    const { unmount } = render(
      <React.StrictMode>
        <SubAgentRunMonitor chatId="chat-1" resetKey={0} />
      </React.StrictMode>,
    );
    await flushPromises();
    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(2);
    expect(mocks.getSubAgentRuns.mock.calls[0][1].aborted).toBe(true);
    unmount();
    await flushPromises();
    expect(mocks.getSubAgentRuns.mock.calls[1][1].aborted).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(40_000);
    });
    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each(["success", "failure"])(
    "ignores late cancel %s after changing chats",
    async (outcome) => {
      let resolve!: (value: { run: ReturnType<typeof run> }) => void;
      let reject!: (error: Error) => void;
      mocks.cancelSubAgentRun.mockReturnValueOnce(
        new Promise((yes, no) => {
          resolve = yes;
          reject = no;
        }),
      );
      mocks.getSubAgentRuns
        .mockResolvedValueOnce(snapshot([run()]))
        .mockResolvedValue({
          ...snapshot([run({ agent_name: "new-chat" })]),
          chat_id: "chat-2",
        });
      const { rerender } = render(
        <SubAgentRunMonitor chatId="chat-1" resetKey={0} />,
      );
      await flushPromises();
      fireEvent.click(screen.getByRole("button", { name: "助手运行状态" }));
      fireEvent.click(
        screen.getByRole("button", { name: "停止 plan-researcher" }),
      );
      rerender(<SubAgentRunMonitor chatId="chat-2" resetKey={0} />);
      await flushPromises();
      fireEvent.click(screen.getByRole("button", { name: "助手运行状态" }));
      await act(async () => {
        if (outcome === "success")
          resolve({ run: run({ status: "cancelled" }) });
        else reject(new Error("old request"));
      });
      expect(screen.getByText("new-chat")).toBeInTheDocument();
      expect(screen.getByText("运行中")).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "停止 new-chat" }),
      ).not.toBeDisabled();
      expect(mocks.messageError).not.toHaveBeenCalled();
      expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(2);
    },
  );

  it("prevents an older running query from overwriting cancellation", async () => {
    const stale = deferredSnapshot();
    const confirmation = deferredSnapshot();
    mocks.getSubAgentRuns
      .mockResolvedValueOnce(snapshot([run()]))
      .mockReturnValueOnce(stale.promise)
      .mockReturnValueOnce(confirmation.promise);
    mocks.cancelSubAgentRun.mockResolvedValueOnce({
      run: run({ status: "cancelled" }),
    });
    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await flushPromises();
    fireEvent.click(screen.getByRole("button", { name: "助手运行状态" }));
    await act(async () => {
      emitSubAgentRunsRefreshIfPresent("get_subagent", "chat-1");
    });
    fireEvent.click(
      screen.getByRole("button", { name: "停止 plan-researcher" }),
    );
    await flushPromises();
    expect(screen.getByText("已停止")).toBeInTheDocument();
    expect(mocks.getSubAgentRuns.mock.calls[1][1].aborted).toBe(true);
    await act(async () => {
      stale.resolve(snapshot([run()]));
    });
    expect(screen.getByText("已停止")).toBeInTheDocument();
    expect(screen.queryByText("运行中")).toBeNull();
    await act(async () => {
      confirmation.resolve(snapshot([run({ status: "cancelled" })]));
    });
  });

  it("retains an in-flight stop across a turn reset", async () => {
    let finish!: (value: { run: ReturnType<typeof run> }) => void;
    mocks.cancelSubAgentRun.mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    mocks.getSubAgentRuns.mockResolvedValue(snapshot([run()]));
    const { rerender } = render(
      <SubAgentRunMonitor chatId="chat-1" resetKey={0} />,
    );
    await flushPromises();
    fireEvent.click(screen.getByRole("button", { name: "助手运行状态" }));
    fireEvent.click(
      screen.getByRole("button", { name: "停止 plan-researcher" }),
    );
    rerender(<SubAgentRunMonitor chatId="chat-1" resetKey={1} />);
    await flushPromises();
    fireEvent.click(screen.getByRole("button", { name: "助手运行状态" }));
    const stop = screen.getByRole("button", { name: "停止 plan-researcher" });
    expect(stop).toBeDisabled();
    fireEvent.click(stop);
    expect(mocks.cancelSubAgentRun).toHaveBeenCalledTimes(1);
    mocks.getSubAgentRuns.mockResolvedValue(
      snapshot([run({ status: "cancelled" })]),
    );
    await act(async () => {
      finish({ run: run({ status: "cancelled" }) });
    });
    expect(screen.getByText("已停止")).toBeInTheDocument();
    rerender(<SubAgentRunMonitor chatId="chat-1" resetKey={2} />);
    await flushPromises();
    expect(screen.queryByRole("button", { name: "助手运行状态" })).toBeNull();
  });

  it("updates retained and newly discovered runs independently after reset", async () => {
    vi.useFakeTimers();
    const oldRun = run({ run_id: "retained", agent_name: "retained-agent" });
    const newRun = run({
      run_id: "new",
      agent_name: "new-agent",
      status: "pending",
    });
    mocks.getSubAgentRuns.mockResolvedValue(snapshot([oldRun]));
    const { rerender } = render(
      <SubAgentRunMonitor chatId="chat-1" resetKey={0} />,
    );
    await flushPromises();
    rerender(<SubAgentRunMonitor chatId="chat-1" resetKey={1} />);
    await flushPromises();
    mocks.getSubAgentRuns.mockResolvedValue(
      snapshot([{ ...oldRun, status: "completed" }, newRun]),
    );
    await act(async () => {
      emitSubAgentRunsRefreshIfPresent("start_subagent", "chat-1");
    });
    fireEvent.click(screen.getByRole("button", { name: "助手运行状态" }));
    expect(screen.getByText("retained-agent")).toBeInTheDocument();
    expect(screen.getByText("new-agent")).toBeInTheDocument();
    expect(screen.getByText("已完成")).toBeInTheDocument();
    expect(screen.getByText("启动中")).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    mocks.getSubAgentRuns.mockResolvedValue(
      snapshot([
        { ...oldRun, status: "completed" },
        { ...newRun, status: "completed" },
      ]),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(screen.getAllByText("已完成")).toHaveLength(2);
    const calls = mocks.getSubAgentRuns.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(calls);
  });

  it("caps budget consumption while preserving snapshot status", async () => {
    mocks.getSubAgentRuns.mockResolvedValue(
      snapshot([
        run({
          budget_consumption: {
            elapsed_ms: 150_000,
            timeout_ms: 120_000,
            ratio: 1.25,
          },
        }),
      ]),
    );

    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "助手运行状态" }),
    );

    expect(screen.getByText("运行中")).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", {
        name: "plan-researcher 时间预算消耗",
      }),
    ).toHaveAttribute("aria-valuenow", "100");
  });

  it("prefers run nickname for display labels", async () => {
    mocks.getSubAgentRuns.mockResolvedValue(
      snapshot([run({ nickname: "研究员" })]),
    );

    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "助手运行状态" }),
    );

    expect(screen.getByText("研究员")).toBeInTheDocument();
    expect(screen.queryByText("plan-researcher")).not.toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", {
        name: "研究员 时间预算消耗",
      }),
    ).toBeInTheDocument();
  });

  it("renders assistant budgets without displaying completed results", async () => {
    mocks.getSubAgentRuns.mockResolvedValue(
      snapshot([
        run({
          status: "completed",
          stoppable: false,
          summary_preview: "已完成的结果摘要",
        }),
      ]),
    );

    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "助手运行状态" }),
    );

    expect(screen.getAllByText("时间 30s / 2m")).toHaveLength(1);
    expect(screen.getAllByText("轮次 2 / 4")).toHaveLength(1);
    expect(screen.queryByText("已完成的结果摘要")).toBeNull();
  });

  it("treats a partial assistant as terminal without displaying its result", async () => {
    mocks.getSubAgentRuns.mockResolvedValue(
      snapshot([
        run({
          status: "partial",
          stoppable: false,
          summary_preview: "可用的部分结果",
        }),
      ]),
    );

    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "助手运行状态" }),
    );

    expect(screen.getByText("部分完成")).toBeInTheDocument();
    expect(screen.queryByText("可用的部分结果")).toBeNull();
  });

  it("allows stopping only running runs", async () => {
    mocks.getSubAgentRuns
      .mockResolvedValueOnce(snapshot([run()]))
      .mockResolvedValueOnce(
        snapshot([run({ status: "cancelled", stoppable: false })]),
      );
    mocks.cancelSubAgentRun.mockResolvedValueOnce({
      run: run({ status: "cancelled", stoppable: false }),
    });

    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "助手运行状态" }),
    );

    const stopButton = await screen.findByRole("button", {
      name: "停止 plan-researcher",
    });
    fireEvent.click(stopButton);

    expect(stopButton).toBeDisabled();
    await waitFor(() => {
      expect(mocks.cancelSubAgentRun).toHaveBeenCalledWith(
        "chat-1",
        "subagent-1",
      );
    });
    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: "停止 plan-researcher" }),
      ).toBeNull();
    });
  });

  it("shows in-panel error and toast when stop request fails", async () => {
    mocks.getSubAgentRuns.mockResolvedValue(snapshot([run()]));
    mocks.cancelSubAgentRun.mockRejectedValueOnce(new Error("network"));

    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "助手运行状态" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "停止 plan-researcher" }),
    );

    expect(await screen.findByText("停止请求失败")).toBeInTheDocument();
    expect(mocks.messageError).toHaveBeenCalledWith("停止请求失败");
  });
});
