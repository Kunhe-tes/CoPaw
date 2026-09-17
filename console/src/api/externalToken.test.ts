import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchNewToken } from "./externalToken";

describe("fetchNewToken", () => {
  beforeEach(() => {
    window.__env__ = {
      systemCode: "system-a",
      systemSect: "secret-a",
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not log issued access tokens", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          data: {
            accessToken: "live-token",
            expiresIn: 3600,
          },
        }),
        { status: 200 },
      ),
    );
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});

    await expect(fetchNewToken()).resolves.toEqual({
      token: "live-token",
      expiresIn: 3600,
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(logSpy).not.toHaveBeenCalled();
  });
});
