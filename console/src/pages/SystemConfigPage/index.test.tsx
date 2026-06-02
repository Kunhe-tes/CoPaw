import React from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SystemConfigPage from "./index";
import { useIframeStore } from "@/stores/iframeStore";
import { useSourceSystemConfigStore } from "@/stores/sourceSystemConfigStore";

const mocks = vi.hoisted(() => ({
  sourceSystemConfigApi: {
    getCurrent: vi.fn(),
    updateCurrent: vi.fn(),
    deleteCurrent: vi.fn(),
  },
  messageApi: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@/api/modules/sourceSystemConfig", () => ({
  sourceSystemConfigApi: mocks.sourceSystemConfigApi,
}));

vi.mock("@/hooks/useAppMessage", () => ({
  useAppMessage: () => ({
    message: mocks.messageApi,
  }),
}));

describe("SystemConfigPage", () => {
  const loadEffectiveConfig = vi.fn().mockResolvedValue(undefined);

  function createDeferred<T>() {
    let resolve!: (value: T) => void;
    let reject!: (reason?: unknown) => void;
    const promise = new Promise<T>((nextResolve, nextReject) => {
      resolve = nextResolve;
      reject = nextReject;
    });
    return { promise, resolve, reject };
  }

  function getTaskProgressSwitch() {
    return screen.getAllByRole("switch")[0];
  }

  function getToolResultCompactSwitch() {
    return screen.getAllByRole("switch")[1];
  }

  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    useIframeStore.getState().clearContext();
    useIframeStore.getState().setContext({
      source: "portal",
      manager: true,
    });
    useSourceSystemConfigStore.setState({
      config: null,
      sourceId: null,
      loading: false,
      error: null,
      requestSeq: 0,
      loadEffectiveConfig,
    });
    mocks.sourceSystemConfigApi.getCurrent.mockResolvedValue({
      source_id: "portal",
      config: {},
      version: 0,
      is_default: true,
      updated_by: null,
      updated_at: null,
    });
  });

  it("renders 403 state for non-manager access", async () => {
    useIframeStore.getState().setContext({
      manager: false,
      isSuperManager: false,
    });

    render(<SystemConfigPage />);

    expect(await screen.findByText("403")).toBeTruthy();
    expect(
      screen.getByText("仅管理员可访问当前系统配置页面。"),
    ).toBeTruthy();
    expect(mocks.sourceSystemConfigApi.getCurrent).not.toHaveBeenCalled();
  });

  it("uses 系统 wording across the system config page", async () => {
    render(<SystemConfigPage />);

    expect(await screen.findByText("当前系统")).toBeTruthy();
    expect(screen.getByText("系统特性配置")).toBeTruthy();
    expect(screen.queryByText("当前 Source")).toBeNull();
    expect(screen.queryByText(/Source/)).toBeNull();
  });

  it("loads current-source config and saves switch changes", async () => {
    mocks.sourceSystemConfigApi.updateCurrent.mockResolvedValue({
      source_id: "portal",
      config: {
        feature_switches: {
          chat_task_progress_enabled: false,
        },
      },
      version: 1,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-20 22:00:00",
    });

    render(<SystemConfigPage />);

    await waitFor(() => {
      expect(screen.queryAllByText("继承默认值").length).toBeGreaterThan(0);
    });

    fireEvent.click(getTaskProgressSwitch());
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.sourceSystemConfigApi.updateCurrent).toHaveBeenCalledWith({
        config: {
          feature_switches: {
            chat_task_progress_enabled: false,
          },
        },
      });
    });
    expect(loadEffectiveConfig).toHaveBeenCalledWith("portal");
    expect(mocks.messageApi.success).toHaveBeenCalled();
  });

  it("saves tool result compact values while preserving unknown raw keys", async () => {
    mocks.sourceSystemConfigApi.getCurrent.mockResolvedValueOnce({
      source_id: "portal",
      config: {
        provider_policy: { default_model: "qwen-max" },
        tool_result_compact: {
          recent_max_bytes: 12000,
          unknown_retained: "yes",
        },
      },
      version: 1,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-20 22:00:00",
    });
    mocks.sourceSystemConfigApi.updateCurrent.mockResolvedValue({
      source_id: "portal",
      config: {
        provider_policy: { default_model: "qwen-max" },
        tool_result_compact: {
          enabled: false,
          recent_max_bytes: 16000,
          unknown_retained: "yes",
        },
      },
      version: 2,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-21 10:00:00",
    });

    render(<SystemConfigPage />);

    expect(await screen.findByText("工具输出控制")).toBeTruthy();

    fireEvent.click(getToolResultCompactSwitch());
    fireEvent.change(screen.getByDisplayValue("12000"), {
      target: { value: "16000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.sourceSystemConfigApi.updateCurrent).toHaveBeenCalledWith({
        config: {
          provider_policy: { default_model: "qwen-max" },
          tool_result_compact: {
            enabled: false,
            recent_max_bytes: 16000,
            unknown_retained: "yes",
          },
        },
      });
    });
    expect(loadEffectiveConfig).toHaveBeenCalledWith("portal");
  });

  it("saves explicit immediate truncation configs", async () => {
    mocks.sourceSystemConfigApi.updateCurrent.mockResolvedValue({
      source_id: "portal",
      config: {
        file_read_truncation: {
          enabled: true,
          max_bytes: 50000,
        },
      },
      version: 1,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-21 10:00:00",
    });

    render(<SystemConfigPage />);

    expect(await screen.findByText("工具输出控制")).toBeTruthy();
    expect(screen.getByText("继承旧工具结果近期阈值")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "启用独立配置" }));
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.sourceSystemConfigApi.updateCurrent).toHaveBeenCalledWith({
        config: {
          file_read_truncation: {
            enabled: true,
            max_bytes: 50000,
          },
        },
      });
    });
  });

  it("can restore a single immediate truncation section to inheritance", async () => {
    mocks.sourceSystemConfigApi.getCurrent.mockResolvedValueOnce({
      source_id: "portal",
      config: {
        provider_policy: { default_model: "qwen-max" },
        file_read_truncation: {
          enabled: true,
          max_bytes: 12000,
        },
      },
      version: 1,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-21 10:00:00",
    });
    mocks.sourceSystemConfigApi.updateCurrent.mockResolvedValue({
      source_id: "portal",
      config: {
        provider_policy: { default_model: "qwen-max" },
      },
      version: 2,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-21 11:00:00",
    });

    render(<SystemConfigPage />);

    expect(await screen.findByText("工具输出控制")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "恢复继承" }));
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.sourceSystemConfigApi.updateCurrent).toHaveBeenCalledWith({
        config: {
          provider_policy: { default_model: "qwen-max" },
        },
      });
    });
  });

  it("blocks invalid tool result compact thresholds before saving", async () => {
    mocks.sourceSystemConfigApi.updateCurrent.mockResolvedValue({
      source_id: "portal",
      config: {
        tool_result_compact: {
          recent_max_bytes: 4000,
        },
      },
      version: 1,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-21 10:00:00",
    });

    render(<SystemConfigPage />);

    expect(await screen.findByText("工具输出控制")).toBeTruthy();

    fireEvent.change(screen.getByDisplayValue("50000"), {
      target: { value: "1000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.messageApi.error).toHaveBeenCalledWith(
        "近期结果预览字节数不能小于旧结果预览字节数",
      );
    });
    expect(mocks.sourceSystemConfigApi.updateCurrent).not.toHaveBeenCalled();

    expect(screen.getByRole("button", { name: "common.save" })).toBeEnabled();
    fireEvent.change(screen.getByDisplayValue("1000"), {
      target: { value: "4000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.sourceSystemConfigApi.updateCurrent).toHaveBeenCalledWith({
        config: {
          tool_result_compact: {
            recent_max_bytes: 4000,
          },
        },
      });
    });
  });

  it("blocks invalid immediate truncation max bytes before saving", async () => {
    mocks.sourceSystemConfigApi.getCurrent.mockResolvedValueOnce({
      source_id: "portal",
      config: {
        file_read_truncation: {
          enabled: true,
          max_bytes: 999,
        },
      },
      version: 1,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-21 10:00:00",
    });

    render(<SystemConfigPage />);

    expect(await screen.findByText("工具输出控制")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.messageApi.error).toHaveBeenCalledWith(
        "文件读取输出片段字节数不能小于 1000",
      );
    });
    expect(mocks.sourceSystemConfigApi.updateCurrent).not.toHaveBeenCalled();
  });

  it("deletes explicit config and refreshes effective config", async () => {
    mocks.sourceSystemConfigApi.getCurrent
      .mockResolvedValueOnce({
        source_id: "portal",
        config: {
          feature_switches: {
            chat_task_progress_enabled: false,
          },
        },
        version: 2,
        is_default: false,
        updated_by: "alice",
        updated_at: "2026-05-20 22:00:00",
      })
      .mockResolvedValueOnce({
        source_id: "portal",
        config: {},
        version: 0,
        is_default: true,
        updated_by: null,
        updated_at: null,
      });
    mocks.sourceSystemConfigApi.deleteCurrent.mockResolvedValue({
      deleted: true,
    });

    render(<SystemConfigPage />);

    expect(await screen.findByText("存在显式覆盖")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "common.delete" }));

    await waitFor(() => {
      expect(mocks.sourceSystemConfigApi.deleteCurrent).toHaveBeenCalledTimes(
        1,
      );
    });
    expect(loadEffectiveConfig).toHaveBeenCalledWith("portal");
    expect(await screen.findByText("继承默认值")).toBeTruthy();
  });

  it("clears stale draft and blocks save when the next source load fails", async () => {
    mocks.sourceSystemConfigApi.getCurrent
      .mockResolvedValueOnce({
        source_id: "portal",
        config: {
          feature_switches: {
            chat_task_progress_enabled: false,
          },
        },
        version: 2,
        is_default: false,
        updated_by: "alice",
        updated_at: "2026-05-20 22:00:00",
      })
      .mockRejectedValueOnce(new Error("retail load failed"));

    render(<SystemConfigPage />);

    await waitFor(() => {
      expect(getTaskProgressSwitch()).toHaveAttribute("aria-checked", "false");
    });

    act(() => {
      useIframeStore.getState().setContext({
        source: "retail",
      });
    });

    expect(await screen.findByText("当前系统配置请求失败")).toBeTruthy();
    expect(getTaskProgressSwitch()).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("button", { name: "common.save" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "common.delete" }),
    ).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "common.save" }));
    expect(mocks.sourceSystemConfigApi.updateCurrent).not.toHaveBeenCalled();
  });

  it("ignores stale save responses after switching to another source", async () => {
    const saveDeferred = createDeferred<{
      source_id: string;
      config: Record<string, unknown>;
      version: number;
      is_default: boolean;
      updated_by: string | null;
      updated_at: string | null;
    }>();
    mocks.sourceSystemConfigApi.getCurrent
      .mockResolvedValueOnce({
        source_id: "portal",
        config: {
          feature_switches: {
            chat_task_progress_enabled: false,
          },
        },
        version: 1,
        is_default: false,
        updated_by: "alice",
        updated_at: "2026-05-20 22:00:00",
      })
      .mockResolvedValueOnce({
        source_id: "retail",
        config: {},
        version: 0,
        is_default: true,
        updated_by: null,
        updated_at: null,
      });
    mocks.sourceSystemConfigApi.updateCurrent.mockReturnValueOnce(
      saveDeferred.promise,
    );

    render(<SystemConfigPage />);

    await waitFor(() => {
      expect(getTaskProgressSwitch()).toHaveAttribute("aria-checked", "false");
    });

    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    act(() => {
      useIframeStore.getState().setContext({
        source: "retail",
      });
    });

    await waitFor(() => {
      expect(screen.getAllByText("retail").length).toBeGreaterThan(0);
      expect(getTaskProgressSwitch()).toHaveAttribute("aria-checked", "true");
    });

    await act(async () => {
      saveDeferred.resolve({
        source_id: "portal",
        config: {
          feature_switches: {
            chat_task_progress_enabled: false,
          },
        },
        version: 2,
        is_default: false,
        updated_by: "alice",
        updated_at: "2026-05-21 10:00:00",
      });
      await saveDeferred.promise;
    });

    await waitFor(() => {
      expect(screen.getAllByText("retail").length).toBeGreaterThan(0);
      expect(getTaskProgressSwitch()).toHaveAttribute("aria-checked", "true");
    });
    expect(loadEffectiveConfig).not.toHaveBeenCalledWith("portal");
  });
});
