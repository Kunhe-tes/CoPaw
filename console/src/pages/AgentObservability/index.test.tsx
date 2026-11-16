import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
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
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

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
      generated_at: "2026-11-15T00:00:02Z",
      spans: [
        {
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
          quality: "partial",
          duration_us: null,
          time_to_first_chunk_us: null,
          time_to_first_visible_text_us: null,
          input_tokens: null,
          output_tokens: null,
          model_key: null,
          provider_key: null,
          request_model_key: null,
          response_model_key: null,
          model_key_source: null,
          streaming: null,
          finish_reason: null,
        },
      ],
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
    expect(
      await screen.findByText("当前时间范围没有已投影的 Run"),
    ).toBeInTheDocument();
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
      items: [
        {
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
        },
      ],
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
      items: [
        {
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
        },
      ],
      next_cursor: null,
      generated_at: "2026-11-15T00:00:00Z",
      window_start: "2026-11-14T00:00:00Z",
      window_end: "2026-11-15T00:00:00Z",
    });
    mocks.getDetail
      .mockResolvedValueOnce({
        run: { run_id: "run-a" },
        attempts: [],
        generated_at: "2026-11-15T00:00:02Z",
        spans: [
          {
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
            quality: "partial",
            duration_us: null,
            time_to_first_chunk_us: null,
            time_to_first_visible_text_us: null,
            input_tokens: null,
            output_tokens: null,
            model_key: null,
            provider_key: null,
            request_model_key: null,
            response_model_key: null,
            model_key_source: null,
            streaming: null,
            finish_reason: null,
          },
        ],
        spans_has_more: true,
        spans_next_cursor: "span-cursor",
      })
      .mockResolvedValueOnce({
        run: { run_id: "run-a" },
        attempts: [],
        generated_at: "2026-11-15T00:00:02Z",
        spans: [
          {
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
            quality: "partial",
            duration_us: null,
            time_to_first_chunk_us: null,
            time_to_first_visible_text_us: null,
            input_tokens: null,
            output_tokens: null,
            model_key: null,
            provider_key: null,
            request_model_key: null,
            response_model_key: null,
            model_key_source: null,
            streaming: null,
            finish_reason: null,
          },
          {
            span_id: "span-c",
            run_id: "run-a",
            attempt_id: null,
            parent_span_id: "missing-parent",
            span_type: "Tool",
            operation: "read",
            kind: "INTERNAL",
            name: "late.child",
            step_index: null,
            started_at: "2026-11-15T00:00:02Z",
            ended_at: "2026-11-15T00:00:03Z",
            status: "succeeded",
            technical_status: null,
            has_error: null,
            error_type: null,
            quality: "observed",
            duration_us: 1000000,
            time_to_first_chunk_us: null,
            time_to_first_visible_text_us: null,
            input_tokens: null,
            output_tokens: null,
            model_key: null,
            provider_key: null,
            request_model_key: null,
            response_model_key: null,
            model_key_source: null,
            streaming: null,
            finish_reason: null,
          },
        ],
        spans_has_more: false,
        spans_next_cursor: null,
      });
    render(<AgentObservabilityPage />);
    fireEvent.click(await screen.findByText("question-a"));
    expect(await screen.findByText("缺结束事件")).toBeInTheDocument();
    expect(await screen.findByText("加载更多 Span")).toBeInTheDocument();
    fireEvent.click(screen.getByText("加载更多 Span"));
    expect(await screen.findByText("model.call")).toBeInTheDocument();
    const orphanSpan = await screen.findByRole("treeitem", {
      name: /late.child/,
    });
    expect(orphanSpan).toHaveAttribute("aria-level", "2");
    expect(orphanSpan).toHaveTextContent("父节点未加载");
    expect(mocks.getDetail).toHaveBeenNthCalledWith(
      2,
      "run-a",
      { spanLimit: 200, spanCursor: "span-cursor" },
      expect.any(AbortSignal),
    );
    fireEvent.click(screen.getByRole("button", { name: "刷新 Run 详情" }));
    await vi.waitFor(() => expect(mocks.getDetail).toHaveBeenCalledTimes(3));
  });

  it("shows safe Tool execution metadata in the Inspector", async () => {
    mocks.listRuns.mockResolvedValueOnce({
      items: [
        {
          run_id: "run-a",
          source_key: "source-a",
          tenant_key: "tenant-a",
          agent_key: "agent-a",
          chat_key: "chat-a",
          root_question_key: "question-a",
          started_at: "2026-11-15T00:00:00Z",
          ended_at: null,
          status: "succeeded",
          quality: "observed",
          duration_us: 1,
          llm_calls: 0,
          tool_calls: 1,
          input_tokens: 0,
          output_tokens: 0,
          span_count: 1,
          error_span_count: 0,
        },
      ],
      next_cursor: null,
      generated_at: "2026-11-15T00:00:00Z",
      window_start: "2026-11-14T00:00:00Z",
      window_end: "2026-11-15T00:00:00Z",
    });
    mocks.getDetail.mockResolvedValueOnce({
      run: { run_id: "run-a" },
      attempts: [],
      generated_at: "2026-11-15T00:00:02Z",
      spans: [
        {
          span_id: "tool-span",
          run_id: "run-a",
          attempt_id: null,
          parent_span_id: null,
          span_type: "Tool",
          operation: "execute",
          kind: "INTERNAL",
          name: "registered.tool",
          step_index: null,
          started_at: "2026-11-15T00:00:00Z",
          ended_at: "2026-11-15T00:00:01Z",
          status: "failed",
          technical_status: "OK",
          has_error: false,
          error_type: "permission_denied",
          quality: "observed",
          duration_us: 1000000,
          time_to_first_chunk_us: null,
          time_to_first_visible_text_us: null,
          input_tokens: null,
          output_tokens: null,
          model_key: null,
          provider_key: null,
          request_model_key: null,
          response_model_key: null,
          model_key_source: null,
          streaming: null,
          finish_reason: null,
          tool: {
            tool_key: "read_file",
            tool_call_id: "call-1",
            tool_execution_id: "execution-1",
            executor_kind: "agent_tool",
            timeout_budget_ms: 2500,
          },
        },
      ],
      spans_has_more: false,
      spans_next_cursor: null,
    });
    render(<AgentObservabilityPage />);
    fireEvent.click(await screen.findByText("question-a"));
    fireEvent.click(await screen.findByRole("button", { name: /registered.tool/ }));
    expect(await screen.findByText("read_file")).toBeInTheDocument();
    expect(screen.getByText("call-1 · execution-1")).toBeInTheDocument();
    expect(screen.getByText("agent_tool · 2500 ms")).toBeInTheDocument();
    expect(screen.getByText("permission_denied")).toBeInTheDocument();
  });

  it("filters spans by Attempt and opens the selected Span Inspector", async () => {
    mocks.listRuns.mockResolvedValueOnce({
      items: [
        {
          run_id: "run-a",
          source_key: "source-a",
          tenant_key: "tenant-a",
          agent_key: "agent-a",
          chat_key: "chat-a",
          root_question_key: "question-a",
          started_at: "2026-11-15T00:00:00Z",
          ended_at: null,
          status: "waiting_approval",
          quality: "partial",
          duration_us: 1000,
          llm_calls: 1,
          tool_calls: 0,
          input_tokens: 3,
          output_tokens: 1,
          span_count: 1,
          error_span_count: 0,
        },
      ],
      next_cursor: null,
      generated_at: "2026-11-15T00:00:02Z",
      window_start: "2026-11-14T00:00:00Z",
      window_end: "2026-11-15T00:00:00Z",
    });
    const selectedSpan = {
      span_id: "span-a",
      run_id: "run-a",
      attempt_id: "attempt-a",
      parent_span_id: null,
      span_type: "LLM",
      operation: "chat",
      kind: "CLIENT",
      name: "model.call",
      step_index: null,
      started_at: "2026-11-15T00:00:00Z",
      ended_at: "2026-11-15T00:00:02Z",
      status: "waiting_approval",
      technical_status: "OK",
      has_error: 0,
      error_type: null,
      quality: "observed",
      duration_us: 1900000,
      time_to_first_chunk_us: null,
      time_to_first_visible_text_us: null,
      input_tokens: 3,
      output_tokens: 1,
      model_key: "model-a",
      provider_key: "provider-a",
      request_model_key: "model-a",
      response_model_key: "model-a",
      model_key_source: "response",
      streaming: 0,
      finish_reason: "stop",
    };
    mocks.getDetail
      .mockResolvedValueOnce({
        run: { run_id: "run-a" },
        attempts: [
          {
            attempt_id: "attempt-a",
            run_id: "run-a",
            attempt_index: 1,
            predecessor_attempt_id: null,
            started_at: "2026-11-15T00:00:00Z",
            ended_at: "2026-11-15T00:00:02Z",
            status: "waiting_approval",
            duration_us: 2000000,
          },
        ],
        generated_at: "2026-11-15T00:00:02Z",
        spans: [selectedSpan],
        spans_has_more: false,
        spans_next_cursor: null,
      })
      .mockResolvedValueOnce({
        run: { run_id: "run-a" },
        attempts: [],
        generated_at: "2026-11-15T00:00:03Z",
        spans: [selectedSpan],
        spans_has_more: false,
        spans_next_cursor: null,
      });
    render(<AgentObservabilityPage />);
    fireEvent.click(await screen.findByText("question-a"));
    expect(await screen.findByText("待审批")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /model.call/ }));
    expect(await screen.findByText("Span ID")).toBeInTheDocument();
    expect(screen.getByText("输入 3 · 输出 1")).toBeInTheDocument();
    expect(screen.getByText(/区间相差 100\.0 ms/)).toBeInTheDocument();

    fireEvent.mouseDown(
      screen.getByRole("combobox", { name: "按 Attempt 查看操作" }),
    );
    fireEvent.click(await screen.findByText("#1 · waiting_approval"));
    await vi.waitFor(() =>
      expect(mocks.getDetail).toHaveBeenLastCalledWith(
        "run-a",
        { attemptId: "attempt-a" },
        expect.any(AbortSignal),
      ),
    );
  });

  it("refreshes open detail every five seconds and pauses while hidden", async () => {
    mocks.listRuns.mockResolvedValueOnce({
      items: [
        {
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
          span_count: 1,
          error_span_count: 0,
        },
      ],
      next_cursor: null,
      generated_at: "2026-11-15T00:00:00Z",
      window_start: "2026-11-14T00:00:00Z",
      window_end: "2026-11-15T00:00:00Z",
    });
    render(<AgentObservabilityPage />);
    expect(await screen.findByText("question-a")).toBeInTheDocument();
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(screen.getByText("question-a"));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mocks.getDetail).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
      await Promise.resolve();
    });
    expect(mocks.getDetail).toHaveBeenCalledTimes(2);

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(mocks.getDetail).toHaveBeenCalledTimes(2);
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "visible",
    });
  });

  it("stops polling after all known execution is terminal but keeps manual refresh", async () => {
    mocks.listRuns.mockResolvedValueOnce({
      items: [
        {
          run_id: "run-a",
          source_key: "source-a",
          tenant_key: "tenant-a",
          agent_key: "agent-a",
          chat_key: "chat-a",
          root_question_key: "question-a",
          started_at: "2026-11-15T00:00:00Z",
          ended_at: "2026-11-15T00:00:02Z",
          status: "succeeded",
          quality: "observed",
          duration_us: 2000000,
          llm_calls: 0,
          tool_calls: 0,
          input_tokens: null,
          output_tokens: null,
          span_count: 1,
          error_span_count: 0,
        },
      ],
      next_cursor: null,
      generated_at: "2026-11-15T00:00:03Z",
      window_start: "2026-11-14T00:00:00Z",
      window_end: "2026-11-15T00:00:00Z",
    });
    mocks.getDetail.mockResolvedValueOnce({
      run: { run_id: "run-a", status: "succeeded" },
      attempts: [
        {
          attempt_id: "attempt-a",
          run_id: "run-a",
          attempt_index: 1,
          predecessor_attempt_id: null,
          started_at: "2026-11-15T00:00:00Z",
          ended_at: "2026-11-15T00:00:02Z",
          status: "succeeded",
          duration_us: 2000000,
        },
      ],
      generated_at: "2026-11-15T00:00:03Z",
      spans: [
        {
          span_id: "span-a",
          run_id: "run-a",
          attempt_id: "attempt-a",
          parent_span_id: null,
          span_type: "Agent",
          operation: "execute",
          kind: "SERVER",
          name: "agent.execute",
          step_index: null,
          started_at: "2026-11-15T00:00:00Z",
          ended_at: "2026-11-15T00:00:02Z",
          status: "succeeded",
          technical_status: "OK",
          has_error: 0,
          error_type: null,
          quality: "observed",
          duration_us: 2000000,
          time_to_first_chunk_us: null,
          time_to_first_visible_text_us: null,
          input_tokens: null,
          output_tokens: null,
          model_key: null,
          provider_key: null,
          request_model_key: null,
          response_model_key: null,
          model_key_source: null,
          streaming: null,
          finish_reason: null,
        },
      ],
      spans_has_more: false,
      spans_next_cursor: null,
    });
    render(<AgentObservabilityPage />);
    expect(await screen.findByText("question-a")).toBeInTheDocument();
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(screen.getByText("question-a"));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mocks.getDetail).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(mocks.getDetail).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "刷新 Run 详情" }));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mocks.getDetail).toHaveBeenCalledTimes(2);
  });

  it("reloads the scoped list when the active Source changes", async () => {
    const { rerender } = render(<AgentObservabilityPage />);
    expect(
      await screen.findByText("当前时间范围没有已投影的 Run"),
    ).toBeInTheDocument();
    mocks.iframeState.source = "source-b";
    rerender(<AgentObservabilityPage />);
    await vi.waitFor(() => expect(mocks.listRuns).toHaveBeenCalledTimes(2));
  });
});
