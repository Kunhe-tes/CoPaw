import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AgentObservabilityPage from ".";

const mocks = vi.hoisted(() => ({
  listRuns: vi.fn(),
  iframeState: {
    manager: true,
    isSuperManager: false,
    source: "source-a",
  },
}));

vi.mock("../../api/modules/agentObservability", () => ({
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

  it("reloads the scoped list when the active Source changes", async () => {
    const { rerender } = render(<AgentObservabilityPage />);
    expect(await screen.findByText("当前时间范围没有已投影的 Run")).toBeInTheDocument();
    mocks.iframeState.source = "source-b";
    rerender(<AgentObservabilityPage />);
    await vi.waitFor(() => expect(mocks.listRuns).toHaveBeenCalledTimes(2));
  });
});
