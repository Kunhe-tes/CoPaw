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
    vi.clearAllMocks();
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
      expect(mocks.getSubAgentRuns).toHaveBeenCalledWith("chat-1");
    });
    expect(screen.queryByRole("button", { name: /SubAgent/i })).toBeNull();
  });

  it("polls every 10 seconds while non-terminal runs exist", async () => {
    vi.useFakeTimers();
    mocks.getSubAgentRuns.mockResolvedValue(snapshot([run()]));

    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await flushPromises();
    screen.getByRole("button", { name: /SubAgent/i });

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
    screen.getByRole("button", { name: /SubAgent/i });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(1);
  });

  it("refreshes immediately when stream event requests refresh", async () => {
    mocks.getSubAgentRuns.mockResolvedValue(snapshot([run()]));

    render(<SubAgentRunMonitor chatId="chat-1" resetKey={0} />);
    await screen.findByRole("button", { name: /SubAgent/i });

    await act(async () => {
      document.dispatchEvent(new CustomEvent(SUBAGENT_RUNS_REFRESH_EVENT));
    });

    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(2);
  });

  it("hides earlier runs after reset and shows later snapshot runs", async () => {
    const oldRun = run({
      run_id: "subagent-old",
      agent_name: "old-agent",
    });
    const newRun = run({
      run_id: "subagent-new",
      agent_name: "new-agent",
    });
    mocks.getSubAgentRuns
      .mockResolvedValueOnce(snapshot([oldRun]))
      .mockResolvedValueOnce(snapshot([oldRun, newRun]));

    const { rerender } = render(
      <SubAgentRunMonitor chatId="chat-1" resetKey={0} />,
    );
    await flushPromises();
    screen.getByText("1 个 SubAgent 运行中");

    rerender(<SubAgentRunMonitor chatId="chat-1" resetKey={1} />);
    await flushPromises();
    expect(screen.queryByRole("button", { name: /SubAgent/i })).toBeNull();
    expect(mocks.getSubAgentRuns).toHaveBeenCalledTimes(1);

    await act(async () => {
      document.dispatchEvent(new CustomEvent(SUBAGENT_RUNS_REFRESH_EVENT));
    });

    expect(await screen.findByText("1 个 SubAgent 运行中")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /SubAgent/i }));
    expect(screen.queryByText("old-agent")).toBeNull();
    expect(screen.getByText("new-agent")).toBeInTheDocument();
  });

  it("ignores in-flight snapshots after reset without hiding new runs", async () => {
    const pending = deferredSnapshot();
    const oldRun = run({
      run_id: "subagent-old",
      agent_name: "old-agent",
    });
    const newRun = run({
      run_id: "subagent-new",
      agent_name: "new-agent",
    });
    mocks.getSubAgentRuns
      .mockResolvedValueOnce(snapshot([oldRun]))
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce(snapshot([oldRun, newRun]));

    const { rerender } = render(
      <SubAgentRunMonitor chatId="chat-1" resetKey={0} />,
    );
    await flushPromises();
    screen.getByText("1 个 SubAgent 运行中");

    await act(async () => {
      document.dispatchEvent(new CustomEvent(SUBAGENT_RUNS_REFRESH_EVENT));
    });

    rerender(<SubAgentRunMonitor chatId="chat-1" resetKey={1} />);
    await act(async () => {
      pending.resolve(snapshot([oldRun, newRun]));
    });

    expect(screen.queryByRole("button", { name: /SubAgent/i })).toBeNull();

    await act(async () => {
      document.dispatchEvent(new CustomEvent(SUBAGENT_RUNS_REFRESH_EVENT));
    });

    expect(await screen.findByText("1 个 SubAgent 运行中")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /SubAgent/i }));
    expect(screen.queryByText("old-agent")).toBeNull();
    expect(screen.getByText("new-agent")).toBeInTheDocument();
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
    fireEvent.click(await screen.findByRole("button", { name: /SubAgent/i }));

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
    fireEvent.click(await screen.findByRole("button", { name: /SubAgent/i }));

    expect(screen.getByText("研究员")).toBeInTheDocument();
    expect(
      screen.queryByText("plan-researcher"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", {
        name: "研究员 时间预算消耗",
      }),
    ).toBeInTheDocument();
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
    fireEvent.click(await screen.findByRole("button", { name: /SubAgent/i }));

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
    fireEvent.click(await screen.findByRole("button", { name: /SubAgent/i }));
    fireEvent.click(
      await screen.findByRole("button", { name: "停止 plan-researcher" }),
    );

    expect(await screen.findByText("停止请求失败")).toBeInTheDocument();
    expect(mocks.messageError).toHaveBeenCalledWith("停止请求失败");
  });
});
