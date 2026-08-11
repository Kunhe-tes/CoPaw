import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
}));

vi.mock("../request", () => ({
  request: mocks.request,
}));

vi.mock("../config", () => ({
  getApiToken: () => "",
  getApiUrl: (path: string) => path,
}));

vi.mock("../authHeaders", () => ({
  buildAuthHeaders: () => ({}),
}));

describe("chat subagent api", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches subagent run snapshot by backend chat id", async () => {
    mocks.request.mockResolvedValueOnce({
      chat_id: "chat-1",
      session_id: "session-1",
      runs: [],
    });
    const { chatApi } = await import("./chat");

    const result = await chatApi.getSubAgentRuns("chat-1");

    expect(result.runs).toEqual([]);
    expect(mocks.request).toHaveBeenCalledWith(
      "/subagents/runs?chat_id=chat-1",
    );
  });

  it("cancels one subagent run with backend chat id in body", async () => {
    mocks.request.mockResolvedValueOnce({
      run: { run_id: "subagent-1", status: "cancelled" },
    });
    const { chatApi } = await import("./chat");

    await chatApi.cancelSubAgentRun("chat-1", "subagent-1");

    expect(mocks.request).toHaveBeenCalledWith(
      "/subagents/runs/subagent-1/cancel",
      {
        method: "POST",
        body: JSON.stringify({ chat_id: "chat-1" }),
      },
    );
  });
});
