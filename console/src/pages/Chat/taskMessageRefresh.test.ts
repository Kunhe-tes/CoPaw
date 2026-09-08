import { describe, expect, it, vi } from "vitest";
import { refreshTaskSessionWithRetry } from "./taskMessageRefresh";

describe("refreshTaskSessionWithRetry", () => {
  it("retries a transient session refresh failure", async () => {
    const refreshSession = vi
      .fn<() => Promise<boolean>>()
      .mockRejectedValueOnce(new Error("server error"))
      .mockResolvedValueOnce(true);
    const wait = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);

    await expect(
      refreshTaskSessionWithRetry(refreshSession, {
        maxAttempts: 3,
        retryDelayMs: 0,
        wait,
      }),
    ).resolves.toBe(true);

    expect(refreshSession).toHaveBeenCalledTimes(2);
    expect(wait).toHaveBeenCalledOnce();
  });
});
