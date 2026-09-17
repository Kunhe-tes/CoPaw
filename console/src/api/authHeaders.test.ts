import { beforeEach, describe, expect, it, vi } from "vitest";

import { buildAuthHeaders } from "./authHeaders";
import { useIframeStore } from "../stores/iframeStore";

interface CustomWindow extends Window {
  currentUserId?: string;
}

vi.mock("./config", () => ({
  getApiToken: vi.fn(() => ""),
}));

vi.mock("./externalToken", () => ({
  getExternalToken: vi.fn(() => ""),
  isExternalTokenEnabled: vi.fn(() => false),
}));

describe("buildAuthHeaders", () => {
  beforeEach(() => {
    sessionStorage.clear();
    useIframeStore.getState().clearContext();
    delete (window as CustomWindow).currentUserId;
  });

  it("独立访问时也会携带默认 source 头", () => {
    expect(buildAuthHeaders()).toMatchObject({
      "X-User-Id": "default",
      "X-Tenant-Id": "default",
      "X-Source-Id": "RMASSIST",
    });
  });

  it("iframe source 会覆盖默认 source", () => {
    useIframeStore.getState().setContext({ source: "rmassist" });

    expect(buildAuthHeaders()["X-Source-Id"]).toBe("rmassist");
  });

  it("super manager 会发送 admin 角色头", () => {
    useIframeStore.getState().setContext({ isSuperManager: true });

    expect(buildAuthHeaders()["X-User-Role"]).toBe("admin");
  });

  it("manager 会发送 manager 角色头", () => {
    useIframeStore.getState().setContext({ manager: true });

    expect(buildAuthHeaders()["X-User-Role"]).toBe("manager");
  });
});
