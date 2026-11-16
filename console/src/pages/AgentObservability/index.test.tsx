import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AgentObservabilityPage from ".";

const mocks = vi.hoisted(() => ({
  listRuns: vi.fn(),
  getCapabilities: vi.fn(),
  getHealth: vi.fn(),
  getEvents: vi.fn(),
  getDetail: vi.fn(),
  iframeState: {
    manager: true,
    isSuperManager: false,
    source: "source-a",
  },
}));

vi.mock("../../api/modules/agentObservability", () => ({
  getAgentObservabilityCapabilities: mocks.getCapabilities,
  getAgentObservabilityHealth: mocks.getHealth,
  getAgentObservabilityRunDetail: mocks.getDetail,
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
    mocks.getDetail.mockResolvedValue({
      run: { run_id: "run-a" },
      attempts: [],
      spans: [{
        span_id: "span-a",
        run_id: "run-a",
        attempt_id: null,
        parent_span_id: null,
        span_type: "Agent",
        operation: "execute",
        kind: "SERVER",
        name: "agent.execute",
        step_index: null,
        started_at: "2026-11-15T00:00:00Z",
        ended_at: null,
        status: "running",
        technical_status: null,
        has_error: null,
        error_type: null,
        duration_us: null,
        input_tokens: null,
        output_tokens: null,
      }],
      spans_has_more: false,
      spans_next_cursor: null,
    });
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

  it("loads the next Span page and appends the returned nodes", async () => {
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
        status: "running",
        quality: "partial",
        duration_us: null,
        llm_calls: null,
        tool_calls: null,
        input_tokens: null,
        output_tokens: null,
        span_count: 2,
        error_span_count: 0,
      }],
      next_cursor: null,
      generated_at: "2026-11-15T00:00:00Z",
      window_start: "2026-11-14T00:00:00Z",
      window_end: "2026-11-15T00:00:00Z",
    });
    mocks.getDetail
      .mockResolvedValueOnce({
        run: { run_id: "run-a" },
        attempts: [],
        spans: [{
          span_id: "span-a",
          run_id: "run-a",
          attempt_id: null,
          parent_span_id: null,
          span_type: "Agent",
          operation: "execute",
          kind: "SERVER",
          name: "agent.execute",
          step_index: null,
          started_at: "2026-11-15T00:00:00Z",
          ended_at: null,
          status: "running",
          technical_status: null,
          has_error: null,
          error_type: null,
          duration_us: null,
          input_tokens: null,
          output_tokens: null,
        }],
        spans_has_more: true,
        spans_next_cursor: "span-cursor",
      })
      .mockResolvedValueOnce({
        run: { run_id: "run-a" },
        attempts: [],
        spans: [{
          span_id: "span-b",
          run_id: "run-a",
          attempt_id: null,
          parent_span_id: "span-a",
          span_type: "LLM",
          operation: "chat",
          kind: "CLIENT",
          name: "model.call",
          step_index: null,
          started_at: "2026-11-15T00:00:01Z",
          ended_at: null,
          status: "running",
          technical_status: null,
          has_error: null,
          error_type: null,
          duration_us: null,
          input_tokens: null,
          output_tokens: null,
        }],
        spans_has_more: false,
        spans_next_cursor: null,
      });
    render(<AgentObservabilityPage />);
    fireEvent.click(await screen.findByText("question-a"));
    expect(await screen.findByText("加载更多 Span")).toBeInTheDocument();
    fireEvent.click(screen.getByText("加载更多 Span"));
    expect(await screen.findByText("model.call")).toBeInTheDocument();
    expect(mocks.getDetail).toHaveBeenNthCalledWith(
      2,
      "run-a",
      { spanLimit: 200, spanCursor: "span-cursor" },
    );
    fireEvent.click(screen.getByRole("button", { name: "刷新 Run 详情" }));
    await vi.waitFor(() => expect(mocks.getDetail).toHaveBeenCalledTimes(3));
  });

  it("reloads the scoped list when the active Source changes", async () => {
    const { rerender } = render(<AgentObservabilityPage />);
    expect(await screen.findByText("当前时间范围没有已投影的 Run")).toBeInTheDocument();
    mocks.iframeState.source = "source-b";
    rerender(<AgentObservabilityPage />);
    await vi.waitFor(() => expect(mocks.listRuns).toHaveBeenCalledTimes(2));
  });
});
