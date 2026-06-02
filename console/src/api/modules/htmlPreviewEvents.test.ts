import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  buildAuthHeaders: vi.fn(),
  clearAuthToken: vi.fn(),
  getApiUrl: vi.fn((path: string) => `/api${path}`),
  getIframeContext: vi.fn(),
  getUserId: vi.fn(),
  request: vi.fn(),
}));

vi.mock("../authHeaders", () => ({
  buildAuthHeaders: mocks.buildAuthHeaders,
}));

vi.mock("../config", () => ({
  clearAuthToken: mocks.clearAuthToken,
  getApiUrl: mocks.getApiUrl,
}));

vi.mock("../../stores/iframeStore", () => ({
  getIframeContext: mocks.getIframeContext,
}));

vi.mock("../../utils/identity", () => ({
  getUserId: mocks.getUserId,
}));

vi.mock("../request", () => ({
  request: mocks.request,
}));

describe("htmlPreviewEventsApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.buildAuthHeaders.mockReturnValue({
      Authorization: "Bearer token",
      "X-Source-Id": "copaw",
    });
    mocks.getIframeContext.mockReturnValue({ source: "copaw", bbk: "branch-1" });
    mocks.getUserId.mockReturnValue("user-1");
  });

  it("records clicks with auth headers without using global request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("", { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);

    const { htmlPreviewEventsApi } = await import("./htmlPreviewEvents");
    const result = await htmlPreviewEventsApi.recordClick({
      file_url: "https://example.com/a.html",
      button_id: "follow",
    });

    expect(result).toEqual({ success: false });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/html-preview/events",
      expect.objectContaining({
        method: "POST",
        keepalive: true,
        headers: expect.objectContaining({
          Authorization: "Bearer token",
          "Content-Type": "application/json",
          "X-Source-Id": "copaw",
        }),
      }),
    );
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      source_id: "copaw",
      user_id: "user-1",
      bbk_id: "branch-1",
      file_url: "https://example.com/a.html",
      button_id: "follow",
    });
    expect(mocks.request).not.toHaveBeenCalled();
    expect(mocks.clearAuthToken).not.toHaveBeenCalled();
  });

  it("records list snapshots with runtime context", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ success: true, customer_count: 2 }), {
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { htmlPreviewEventsApi } = await import("./htmlPreviewEvents");
    const result = await htmlPreviewEventsApi.recordListSnapshot({
      file_url: "https://example.com/a.html",
      list_key: "https://example.com/a.html",
      list_name: "a.html",
      customers: [
        {
          customer_id: "CUST-001",
          customer_name: "祝话",
        },
      ],
    });

    expect(result).toEqual({ success: true, customer_count: 2 });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/html-preview/list-snapshot",
      expect.objectContaining({
        method: "POST",
      }),
    );
    expect(fetchMock.mock.calls[0][1]).not.toHaveProperty("keepalive");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      source_id: "copaw",
      bbk_id: "branch-1",
      list_key: "https://example.com/a.html",
      customers: [
        {
          customer_id: "CUST-001",
          customer_name: "祝话",
        },
      ],
    });
  });

  it("passes bbk filters to summary query", async () => {
    const { htmlPreviewEventsApi } = await import("./htmlPreviewEvents");

    await htmlPreviewEventsApi.getSummary({
      startTime: "2026-05-30T00:00:00.000Z",
      endTime: "2026-05-30T23:59:59.999Z",
      bbkIds: "branch-1,branch-2",
      listKey: "list-1",
      limit: 20,
    });

    expect(mocks.request).toHaveBeenCalledWith(
      "/html-preview/events/summary?start_time=2026-05-30T00%3A00%3A00.000Z&end_time=2026-05-30T23%3A59%3A59.999Z&bbk_ids=branch-1%2Cbranch-2&list_key=list-1&limit=20",
    );
  });

  it("passes filters to event detail query", async () => {
    const { htmlPreviewEventsApi } = await import("./htmlPreviewEvents");

    await htmlPreviewEventsApi.getEvents({
      startTime: "2026-05-30T00:00:00.000Z",
      bbkIds: "branch-1",
      listKey: "list-1",
      limit: 10,
    });

    expect(mocks.request).toHaveBeenCalledWith(
      "/html-preview/events?start_time=2026-05-30T00%3A00%3A00.000Z&bbk_ids=branch-1&list_key=list-1&limit=10",
    );
  });

  it("passes filters to customer summary query", async () => {
    const { htmlPreviewEventsApi } = await import("./htmlPreviewEvents");

    await htmlPreviewEventsApi.getCustomerSummary({
      startTime: "2026-05-30T00:00:00.000Z",
      bbkIds: "branch-1",
      listKey: "list-1",
      limit: 20,
    });

    expect(mocks.request).toHaveBeenCalledWith(
      "/html-preview/events/customer-summary?start_time=2026-05-30T00%3A00%3A00.000Z&bbk_ids=branch-1&list_key=list-1&limit=20",
    );
  });

  it("passes filters to list and customer click analysis queries", async () => {
    const { htmlPreviewEventsApi } = await import("./htmlPreviewEvents");

    await htmlPreviewEventsApi.getLists({
      startTime: "2026-05-30T00:00:00.000Z",
      bbkIds: "branch-1",
      limit: 20,
    });
    await htmlPreviewEventsApi.getCustomerClicks({
      startTime: "2026-05-30T00:00:00.000Z",
      bbkIds: "branch-1",
      listKey: "list-1",
      includeUnclicked: true,
      limit: 50,
    });

    expect(mocks.request).toHaveBeenNthCalledWith(
      1,
      "/html-preview/lists?start_time=2026-05-30T00%3A00%3A00.000Z&bbk_ids=branch-1&limit=20",
    );
    expect(mocks.request).toHaveBeenNthCalledWith(
      2,
      "/html-preview/customer-clicks?start_time=2026-05-30T00%3A00%3A00.000Z&bbk_ids=branch-1&list_key=list-1&limit=50&include_unclicked=true",
    );
  });
});
