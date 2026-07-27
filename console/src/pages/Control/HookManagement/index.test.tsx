import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getConfiguration: vi.fn(),
  listScripts: vi.fn(),
  saveConfiguration: vi.fn(),
  uploadScripts: vi.fn(),
  manualTest: vi.fn(),
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

vi.mock("@/api/modules/hookManagement", () => ({
  hookManagementApi: mocks,
}));

vi.mock("@/hooks/useAppMessage", () => ({
  useAppMessage: () => ({ message: mocks.message }),
}));

import HookManagementPage from ".";

const hooks = {
  enabled: true,
  events: {
    PreToolUse: [
      {
        id: "tool-guards",
        matcher: { tools: [] },
        hooks: [
          {
            id: "guard-shell",
            type: "command",
            argv: ["python", "hooks/scripts/guard.py"],
          },
        ],
      },
    ],
  },
};

describe("HookManagementPage", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getConfiguration.mockResolvedValue({ hooks, revision: "rev-1" });
    mocks.listScripts.mockResolvedValue([
      { filename: "guard.py", size: 12, sha256: "a".repeat(64) },
    ]);
    mocks.saveConfiguration.mockResolvedValue({ hooks, revision: "rev-2" });
    mocks.uploadScripts.mockResolvedValue({
      accepted: [],
      warned: [],
      failed: [],
    });
    mocks.manualTest.mockResolvedValue({ redacted_summary: { status: "ok" } });
  });

  it("selects a Handler and exposes ordered argv fields", async () => {
    render(<HookManagementPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: /guard-shell/i }),
    );

    expect(screen.getByLabelText("命令参数 1")).toHaveValue("python");
    expect(screen.getByLabelText("命令参数 2")).toHaveValue(
      "hooks/scripts/guard.py",
    );
  });

  it("requires confirmation before submitting a real manual test", async () => {
    render(<HookManagementPage />);
    fireEvent.click(
      await screen.findByRole("button", { name: /guard-shell/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: "执行人工测试" }));

    const execute = screen.getByRole("button", { name: "执行测试" });
    expect(execute).toBeDisabled();

    fireEvent.click(screen.getByLabelText(/确认将执行真实/i));
    fireEvent.click(execute);

    await waitFor(() => expect(mocks.manualTest).toHaveBeenCalled());
  });

  it("keeps a draft and offers reload when saving conflicts", async () => {
    mocks.saveConfiguration.mockRejectedValueOnce(
      Object.assign(new Error("stale"), { status: 409 }),
    );
    render(<HookManagementPage />);

    fireEvent.click(await screen.findByRole("button", { name: "保存并激活" }));

    expect(await screen.findByText("配置已被更新")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "重新加载最新配置" }),
    ).toBeEnabled();
  });
});
