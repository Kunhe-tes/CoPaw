import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
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

  it("keeps a renamed Handler selected for continued editing", async () => {
    render(<HookManagementPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: /guard-shell/i }),
    );
    fireEvent.change(screen.getByLabelText("Handler ID"), {
      target: { value: "guard-shell-renamed" },
    });

    expect(screen.getByLabelText("Handler ID")).toHaveValue(
      "guard-shell-renamed",
    );
    expect(screen.getByLabelText("命令参数 1")).toHaveValue("python");
  });

  it("edits the selected Matcher Group and its tool matcher", async () => {
    render(<HookManagementPage />);

    fireEvent.click(await screen.findByRole("button", { name: "tool-guards" }));

    expect(screen.getByLabelText("Matcher Group ID")).toHaveValue(
      "tool-guards",
    );
    expect(screen.getByLabelText("匹配工具（每行一个）")).toHaveValue("");
  });

  it("removes an event from the local draft", async () => {
    render(<HookManagementPage />);

    fireEvent.click(await screen.findByRole("button", { name: "删除事件" }));

    expect(screen.queryByText("PreToolUse")).not.toBeInTheDocument();
  });

  it("exposes all supported common and command Handler fields", async () => {
    render(<HookManagementPage />);
    fireEvent.click(
      await screen.findByRole("button", { name: /guard-shell/i }),
    );

    fireEvent.click(screen.getByText("高级设置"));

    expect(screen.getByLabelText("状态消息")).toBeInTheDocument();
    expect(screen.getByLabelText("仅执行一次")).toBeInTheDocument();
    expect(screen.getByLabelText("附带会话快照")).toBeInTheDocument();
    expect(screen.getByLabelText("Shell")).toBeInTheDocument();
    expect(screen.getByLabelText("环境变量（JSON）")).toBeInTheDocument();
  });

  it("uploads a newly selected script without waiting for state to settle", async () => {
    render(<HookManagementPage />);
    fireEvent.click(await screen.findByRole("tab", { name: "脚本库" }));
    const file = new File(["print('ok')"], "new-hook.py", {
      type: "text/x-python",
    });

    fireEvent.change(screen.getByLabelText("选择 Hook 脚本文件"), {
      target: { files: [file] },
    });

    await waitFor(() =>
      expect(mocks.uploadScripts).toHaveBeenCalledWith([file], []),
    );
  });

  it("does not retain JSON field values when switching Handlers", async () => {
    mocks.getConfiguration.mockResolvedValueOnce({
      revision: "rev-1",
      hooks: {
        enabled: true,
        events: {
          PreToolUse: [
            {
              id: "tool-guards",
              matcher: { tools: [] },
              hooks: [
                {
                  id: "first-command",
                  type: "command",
                  argv: ["echo"],
                  env: { FIRST: "one" },
                },
                {
                  id: "second-command",
                  type: "command",
                  argv: ["echo"],
                  env: { SECOND: "two" },
                },
              ],
            },
          ],
        },
      },
    });
    render(<HookManagementPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: /first-command/i }),
    );
    expect(
      (screen.getByLabelText("环境变量（JSON）") as HTMLTextAreaElement).value,
    ).toContain("FIRST");

    fireEvent.click(screen.getByRole("button", { name: /second-command/i }));
    expect(
      (screen.getByLabelText("环境变量（JSON）") as HTMLTextAreaElement).value,
    ).toContain("SECOND");
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
    expect(mocks.manualTest).toHaveBeenCalledWith(
      expect.objectContaining({ id: "guard-shell" }),
      expect.objectContaining({ hook_event_name: "PreToolUse" }),
    );
  });

  it("shows invalid manual-test Context errors inside the test dialog", async () => {
    render(<HookManagementPage />);
    fireEvent.click(
      await screen.findByRole("button", { name: /guard-shell/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: "执行人工测试" }));
    fireEvent.change(screen.getByLabelText("Hook Context（JSON）"), {
      target: { value: "not-json" },
    });
    fireEvent.click(screen.getByLabelText(/确认将执行真实/i));
    fireEvent.click(screen.getByRole("button", { name: "执行测试" }));

    expect(
      await within(screen.getByRole("dialog")).findByText(
        "Hook Context 必须是有效 JSON",
      ),
    ).toBeInTheDocument();
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
