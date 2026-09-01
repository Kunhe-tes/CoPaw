import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getConsoleAccessDecision,
  resolveConsoleAccess,
  runAccessControlledInitialization,
} from "./consoleAccess";

const originalEnv = window.__env__;

describe("Console access gate", () => {
  afterEach(() => {
    window.__env__ = originalEnv;
    document.cookie = "userid=; Max-Age=0; path=/";
  });

  it("allows iframe access without requiring the direct-access whitelist", () => {
    expect(
      resolveConsoleAccess({
        isEmbedded: true,
        userId: null,
        directAccessUserWhitelist: [],
      }),
    ).toEqual({ allowed: true, reason: "embedded", userId: null });
  });

  it("allows top-level access only in Vite development mode", () => {
    expect(
      resolveConsoleAccess({
        isDevelopment: true,
        isEmbedded: false,
        userId: null,
        directAccessUserWhitelist: [],
      }),
    ).toEqual({
      allowed: true,
      reason: "local-development",
      userId: null,
    });

    expect(
      resolveConsoleAccess({
        isDevelopment: false,
        isEmbedded: false,
        userId: null,
        directAccessUserWhitelist: [],
      }).allowed,
    ).toBe(false);
  });

  it("allows a top-level user listed in the runtime whitelist", () => {
    expect(
      resolveConsoleAccess({
        isEmbedded: false,
        userId: "SAP001",
        directAccessUserWhitelist: ["SAP001", "SAP002"],
      }),
    ).toEqual({ allowed: true, reason: "direct-allowlist", userId: "SAP001" });
  });

  it("fails closed for missing, unmatched, or wildcard direct access", () => {
    expect(
      resolveConsoleAccess({
        isEmbedded: false,
        userId: null,
        directAccessUserWhitelist: ["SAP001"],
      }).allowed,
    ).toBe(false);
    expect(
      resolveConsoleAccess({
        isEmbedded: false,
        userId: "SAP002",
        directAccessUserWhitelist: ["SAP001"],
      }).allowed,
    ).toBe(false);
    expect(
      resolveConsoleAccess({
        isEmbedded: false,
        userId: "SAP002",
        directAccessUserWhitelist: ["*"],
      }).allowed,
    ).toBe(false);
  });

  it("reads the standalone identity from the userid cookie", () => {
    document.cookie = "userid=SAP%20001; path=/";
    window.__env__ = { directAccessUserWhitelist: ["SAP 001"] };

    expect(getConsoleAccessDecision(false, false)).toEqual({
      allowed: true,
      reason: "direct-allowlist",
      userId: "SAP 001",
    });
  });

  it("does not start application initialization when access is denied", async () => {
    const initializeAllowedApp = vi.fn();
    const renderAccessDenied = vi.fn();

    await runAccessControlledInitialization({
      decision: { allowed: false, reason: "direct-denied", userId: "SAP002" },
      initializeAllowedApp,
      renderAccessDenied,
    });

    expect(initializeAllowedApp).not.toHaveBeenCalled();
    expect(renderAccessDenied).toHaveBeenCalledOnce();
  });
});
