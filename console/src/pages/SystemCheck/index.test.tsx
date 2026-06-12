import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SystemCheckPage, { parseTenantIds } from "./index";

const mocks = vi.hoisted(() => ({
  checkCronAuthExpiry: vi.fn(),
  messageApi: {
    error: vi.fn(),
    success: vi.fn(),
  },
  iframeState: {
    manager: true,
    isSuperManager: false,
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, options?: { defaultValue?: string }) =>
      options?.defaultValue ?? _key,
  }),
}));

vi.mock("@/api", () => ({
  default: {
    checkCronAuthExpiry: mocks.checkCronAuthExpiry,
  },
}));

vi.mock("@/hooks/useAppMessage", () => ({
  useAppMessage: () => ({
    message: mocks.messageApi,
  }),
}));

vi.mock("@/stores/iframeStore", () => ({
  useIframeStore: (selector: (state: typeof mocks.iframeState) => unknown) =>
    selector(mocks.iframeState),
}));

describe("SystemCheckPage", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.iframeState.manager = true;
    mocks.iframeState.isSuperManager = false;
    mocks.checkCronAuthExpiry.mockResolvedValue({ results: [] });
  });

  it("parses tenant IDs from supported separators and removes duplicates", () => {
    expect(parseTenantIds("tenant-a\ntenant-b，tenant-a, tenant-c tenant-d;tenant-e")).toEqual([
      "tenant-a",
      "tenant-b",
      "tenant-c",
      "tenant-d",
      "tenant-e",
    ]);
  });

  it("renders the manager auth expiry check with RMASSIST as default source", () => {
    render(<SystemCheckPage />);

    expect(screen.getByText("系统自检")).toBeInTheDocument();
    expect(screen.getByText("鉴权过期查询")).toBeInTheDocument();
    expect(screen.getByDisplayValue("RMASSIST")).toBeInTheDocument();
  });

  it("renders a 403 state for non-manager direct access", () => {
    mocks.iframeState.manager = false;

    render(<SystemCheckPage />);

    expect(screen.getByText("403")).toBeInTheDocument();
    expect(screen.getByText("仅管理员可访问系统自检页面。")).toBeInTheDocument();
    expect(mocks.checkCronAuthExpiry).not.toHaveBeenCalled();
  });

  it("validates empty tenant input without calling the backend", () => {
    render(<SystemCheckPage />);

    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    expect(screen.getByText("请输入至少一个租户 ID。")).toBeInTheDocument();
    expect(mocks.checkCronAuthExpiry).not.toHaveBeenCalled();
  });

  it("submits normalized tenants and renders successful results", async () => {
    mocks.checkCronAuthExpiry.mockResolvedValue({
      results: [
        {
          tenant_id: "tenant-a",
          source_id: "RMASSIST",
          status: "valid",
          is_expired: false,
          user_info_expires_at: "2026-06-11T04:00:00+00:00",
          message: "Auth user info is valid",
        },
      ],
    });
    render(<SystemCheckPage />);

    fireEvent.change(screen.getByLabelText("租户 ID"), {
      target: { value: "tenant-a, tenant-a tenant-b" },
    });
    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    await waitFor(() => {
      expect(mocks.checkCronAuthExpiry).toHaveBeenCalledWith({
        source_id: "RMASSIST",
        tenant_ids: ["tenant-a", "tenant-b"],
      });
    });
    expect(await screen.findByText("tenant-a")).toBeInTheDocument();
    expect(screen.getByText("valid")).toBeInTheDocument();
    expect(screen.getByText("否")).toBeInTheDocument();
    expect(screen.getByText("Auth user info is valid")).toBeInTheDocument();
  });

  it("keeps submitted inputs and shows an error when the query fails", async () => {
    mocks.checkCronAuthExpiry.mockRejectedValue(new Error("boom"));
    render(<SystemCheckPage />);

    fireEvent.change(screen.getByLabelText("Source ID"), {
      target: { value: "OTHER" },
    });
    fireEvent.change(screen.getByLabelText("租户 ID"), {
      target: { value: "tenant-a" },
    });
    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(screen.getByDisplayValue("OTHER")).toBeInTheDocument();
    expect(screen.getByDisplayValue("tenant-a")).toBeInTheDocument();
  });
});
