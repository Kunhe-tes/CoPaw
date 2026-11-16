import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AgentObservabilityPage from ".";

const mocks = vi.hoisted(() => ({
  listRuns: vi.fn(),
  getCapabilities: vi.fn(),
  getHealth: vi.fn(),
  getEvents: vi.fn(),
  iframeState: {
    manager: true,
    isSuperManager: false,
    source: "source-a",
  },
}));

vi.mock("../../api/modules/agentObservability", () => ({
  getAgentObservabilityCapabilities: mocks.getCapabilities,
  getAgentObservabilityHealth: mocks.getHealth,
  getAgentObservabilityRunEvents: mocks.getEvents,
  listAgentObservabilityRuns: mocks.listRuns,
}));

vi.mock("../../stores/iframeStore", () => ({
  useIframeStore: (selector: (state: typeof mocks.iframeState) => unknown) =>
    selector(mocks.iframeState),
}));

describe("AgentObservabilityPage", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.iframeState.manager = true;
    mocks.iframeState.isSuperManager = false;
    mocks.getCapabilities.mockResolvedValue({
      capture_enabled: true,
      storage_configured: true,
      storage_ready: true,
      projector_running: true,
      queue_events: 4096,
      queue_bytes: 8 * 1024 * 1024,
      max_event_bytes: 24 * 1024,
    });
    mocks.getHealth.mockResolvedValue({
      capture_enabled: true,
      storage_ready: true,
      projector_running: true,
      dropped_events: null,
      generated_at: "2026-11-15T00:00:00Z",
    });
    mocks.getEvents.mockResolvedValue({ items: [], next_cursor: null });
    mocks.listRuns.mockResolvedValue({
      items: [],
      next_cursor: null,
      generated_at: "2026-11-15T00:00:00Z",
      window_start: "2026-11-14T00:00:00Z",
      window_end: "2026-11-15T00:00:00Z",
    });
  });

  it("shows the authorized scoped Run list", async () => {
    render(<AgentObservabilityPage />);
    expect(await screen.findByText("当前时间范围没有已投影的 Run")).toBeInTheDocument();
    expect(await screen.findByText(/采集已开启/)).toBeInTheDocument();
    expect(mocks.listRuns).toHaveBeenCalledWith(
      expect.objectContaining({ sources: undefined, limit: 50 }),
      expect.any(AbortSignal),
    );
  });

  it("blocks direct navigation for ordinary users", () => {
    mocks.iframeState.manager = false;
    render(<AgentObservabilityPage />);
    expect(screen.getByText("403")).toBeInTheDocument();
    expect(mocks.listRuns).not.toHaveBeenCalled();
  });

  it("requests global health only for admins", async () => {
    mocks.iframeState.isSuperManager = true;
    render(<AgentObservabilityPage />);
    await screen.findByText("当前时间范围没有已投影的 Run");
    expect(mocks.getHealth).toHaveBeenCalledWith(expect.any(AbortSignal));
  });

  it("renders missing Run status as unknown", async () => {
    mocks.listRuns.mockResolvedValueOnce({
      items: [{
        run_id: "run-a",
        source_key: "source-a",
        tenant_key: "tenant-a",
        agent_key: "agent-a",
        chat_key: "chat-a",
        root_question_key: "question-a",
        started_at: "2026-11-15T00:00:00Z",
        ended_at: null,
        status: null,
        quality: "partial",
        duration_us: null,
        llm_calls: null,
        tool_calls: null,
        input_tokens: null,
        output_tokens: null,
        span_count: 1,
        error_span_count: 0,
      }],
      next_cursor: null,
      generated_at: "2026-11-15T00:00:00Z",
      window_start: "2026-11-14T00:00:00Z",
      window_end: "2026-11-15T00:00:00Z",
    });
    render(<AgentObservabilityPage />);
    expect(await screen.findByText("unknown")).toBeInTheDocument();
  });

  it("reloads the scoped list when the active Source changes", async () => {
    const { rerender } = render(<AgentObservabilityPage />);
    expect(await screen.findByText("当前时间范围没有已投影的 Run")).toBeInTheDocument();
    mocks.iframeState.source = "source-b";
    rerender(<AgentObservabilityPage />);
    await vi.waitFor(() => expect(mocks.listRuns).toHaveBeenCalledTimes(2));
  });
});
