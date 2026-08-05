import { beforeEach, describe, expect, it, vi } from "vitest";

import { securityApi } from "./security";

const requestMock = vi.hoisted(() => vi.fn());

vi.mock("../request", () => ({
  request: requestMock,
}));

beforeEach(() => {
  requestMock.mockReset();
  requestMock.mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  });
});

describe("securityApi skill scan history", () => {
  it("requests one bounded backend page", async () => {
    await securityApi.getBlockedHistory(2, 10);

    expect(requestMock).toHaveBeenCalledTimes(1);
    const path = requestMock.mock.calls[0][0] as string;
    const url = new URL(path, "http://security.test");
    expect(url.pathname).toBe("/config/security/skill-scanner/blocked-history");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      page: "2",
      page_size: "10",
    });
  });

  it("deletes a history record by stable id", async () => {
    await securityApi.removeBlockedEntry("record/1");

    expect(requestMock).toHaveBeenCalledWith(
      "/config/security/skill-scanner/blocked-history/record%2F1",
      { method: "DELETE" },
    );
  });

  it("requests the latest warning for one skill", async () => {
    await securityApi.getLatestScanWarning(
      "skill/with spaces",
      "2026-08-03T08:30:00+00:00",
    );

    expect(requestMock).toHaveBeenCalledTimes(1);
    const path = requestMock.mock.calls[0][0] as string;
    const url = new URL(path, "http://security.test");
    expect(url.pathname).toBe(
      "/config/security/skill-scanner/blocked-history/latest-warning",
    );
    expect(url.searchParams.get("skill_name")).toBe("skill/with spaces");
    expect(url.searchParams.get("since")).toBe("2026-08-03T08:30:00+00:00");
  });

  it("captures the server warning cursor", async () => {
    requestMock.mockResolvedValueOnce({
      cursor: "2026-08-03T08:30:00+00:00",
    });

    await expect(securityApi.getScanWarningCursor()).resolves.toBe(
      "2026-08-03T08:30:00+00:00",
    );
    expect(requestMock).toHaveBeenCalledWith(
      "/config/security/skill-scanner/warning-cursor",
    );
  });
});
