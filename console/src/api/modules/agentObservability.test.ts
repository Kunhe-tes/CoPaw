import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("../request", () => ({ request: mocks.request }));

import {
  getAgentObservabilityCapabilities,
  getAgentObservabilityHealth,
  getAgentObservabilityRunDetail,
  getAgentObservabilityRunEvents,
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

  it("loads a bounded Run detail with an optional Attempt filter", async () => {
    mocks.request.mockResolvedValue({});
    await getAgentObservabilityRunDetail("run/one", {
      attemptId: "attempt-one",
      spanLimit: 120,
      spanCursor: "signed+span-cursor",
    });
    expect(mocks.request).toHaveBeenCalledWith(
      "/agent-observability/runs/run%2Fone?attempt_id=attempt-one&span_limit=120&span_cursor=signed%2Bspan-cursor",
      { signal: undefined },
    );
  });

  it("loads a bounded event page with an optional Span filter and cursor", async () => {
    mocks.request.mockResolvedValue({ items: [], next_cursor: null });
    await getAgentObservabilityRunEvents("run/one", {
      spanId: "span-one",
      cursor: "signed+cursor",
      limit: 100,
    });
    expect(mocks.request).toHaveBeenCalledWith(
      "/agent-observability/runs/run%2Fone/events?span_id=span-one&cursor=signed%2Bcursor&limit=100",
      { signal: undefined },
    );
  });
});
