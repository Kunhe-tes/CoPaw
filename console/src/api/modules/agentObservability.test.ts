import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("../request", () => ({ request: mocks.request }));

import {
  getAgentObservabilityCapabilities,
  getAgentObservabilityHealth,
  listAgentObservabilityRuns,
} from "./agentObservability";

describe("agent observability API", () => {
  beforeEach(() => mocks.request.mockReset());

  it("sends an explicit source set and preserves a signed cursor window", async () => {
    mocks.request.mockResolvedValue({ items: [], next_cursor: null });
    await listAgentObservabilityRuns({
      sources: ["source a", "source/b"],
      cursor: "signed+cursor",
      start: "2026-11-15T00:00:00+00:00",
      end: "2026-11-15T23:59:00+00:00",
      limit: 50,
    });
    expect(mocks.request).toHaveBeenCalledWith(
      "/agent-observability/runs?source_id=source+a&source_id=source%2Fb&cursor=signed%2Bcursor&start=2026-11-15T00%3A00%3A00%2B00%3A00&end=2026-11-15T23%3A59%3A00%2B00%3A00&limit=50",
      { signal: undefined },
    );
  });

  it("uses the dedicated capability and admin health endpoints", async () => {
    mocks.request.mockResolvedValue({});
    const signal = new AbortController().signal;
    await getAgentObservabilityCapabilities(signal);
    await getAgentObservabilityHealth(signal);
    expect(mocks.request).toHaveBeenNthCalledWith(
      1,
      "/agent-observability/capabilities",
      { signal },
    );
    expect(mocks.request).toHaveBeenNthCalledWith(
      2,
      "/agent-observability/health",
      { signal },
    );
  });
});
