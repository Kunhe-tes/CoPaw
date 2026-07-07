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

  function getZhaohuToolGuardNotificationSwitch() {
    return screen.getAllByRole("switch")[2];
  }

  function getCronUnreadAutoPauseSwitch() {
    return screen.getAllByRole("switch")[3];
  }

  function getArchiveMaintenanceSwitch() {
    return screen.getAllByRole("switch")[5];
  }

  function getToolResultCompactSwitch() {
    return screen.getAllByRole("switch")[6];
  }

  function seedEffectiveConfig(config: Record<string, unknown> = {}) {
    useSourceSystemConfigStore.setState({
      config: {
        source_id: "portal",
        config,
        version: 1,
        is_default: false,
        stale: false,
        updated_by: "alice",
        updated_at: "2026-05-21 10:00:00",
      },
      sourceId: "portal",
    });
  }

  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    loadEffectiveConfig.mockReset();
    loadEffectiveConfig.mockResolvedValue(undefined);
    mocks.sourceSystemConfigApi.getCurrent.mockReset();
    mocks.sourceSystemConfigApi.updateCurrent.mockReset();
    mocks.sourceSystemConfigApi.deleteCurrent.mockReset();
    mocks.messageApi.success.mockReset();
    mocks.messageApi.error.mockReset();
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
    expect(screen.getByText("仅管理员可访问当前系统配置页面。")).toBeTruthy();
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

  it("saves zhaohu Tool Guard approval notification switch changes", async () => {
    mocks.sourceSystemConfigApi.updateCurrent.mockResolvedValue({
      source_id: "portal",
      config: {
        approval_notifications: {
          zhaohu_tool_guard_enabled: true,
        },
      },
      version: 1,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-20 22:00:00",
    });

    render(<SystemConfigPage />);

    expect(await screen.findByText("Tool Guard 审批招乎通知")).toBeTruthy();

    fireEvent.click(getZhaohuToolGuardNotificationSwitch());
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.sourceSystemConfigApi.updateCurrent).toHaveBeenCalledWith({
        config: {
          approval_notifications: {
            zhaohu_tool_guard_enabled: true,
          },
        },
      });
    });
    expect(loadEffectiveConfig).toHaveBeenCalledWith("portal");
  });

  it("saves cron unread auto pause settings", async () => {
    mocks.sourceSystemConfigApi.updateCurrent.mockResolvedValue({
      source_id: "portal",
      config: {
        cron_unread_auto_pause: {
          enabled: false,
          threshold: 12,
        },
      },
      version: 1,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-20 22:00:00",
    });

    render(<SystemConfigPage />);

    expect(await screen.findByText("定时任务未读自动暂停")).toBeTruthy();

    fireEvent.change(screen.getByDisplayValue("10"), {
      target: { value: "12" },
    });
    fireEvent.click(getCronUnreadAutoPauseSwitch());
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.sourceSystemConfigApi.updateCurrent).toHaveBeenCalledWith({
        config: {
          cron_unread_auto_pause: {
            enabled: false,
            threshold: 12,
          },
        },
      });
    });
  });

  it("saves cron task session cleanup settings", async () => {
    mocks.sourceSystemConfigApi.getCurrent.mockResolvedValueOnce({
      source_id: "portal",
      config: {
        provider_policy: { default_model: "qwen-max" },
        cron_task_session_cleanup: {
          enabled: true,
          retention_days: 30,
          cron: "0 1 * * *",
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
        cron_task_session_cleanup: {
          enabled: true,
          retention_days: 45,
          cron: "30 2 * * *",
          unknown_retained: "yes",
        },
      },
      version: 2,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-21 10:00:00",
    });

    render(<SystemConfigPage />);

    const scheduledTaskCardTitle = await screen.findByText("定时任务设置");
    const scheduledTaskCard = scheduledTaskCardTitle.closest(".ant-card");
    expect(screen.getByText("定时任务未读自动暂停").closest(".ant-card")).toBe(
      scheduledTaskCard,
    );
    expect(screen.getByText("定时任务会话历史清理").closest(".ant-card")).toBe(
      scheduledTaskCard,
    );
    expect(screen.getByText("01:00")).toBeTruthy();

    fireEvent.change(screen.getByDisplayValue("30"), {
      target: { value: "45" },
    });
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "每日运行时间" }));
    fireEvent.click(await screen.findByText("02:30"));
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.sourceSystemConfigApi.updateCurrent).toHaveBeenCalledWith({
        config: {
          provider_policy: { default_model: "qwen-max" },
          cron_task_session_cleanup: {
            enabled: true,
            retention_days: 45,
            cron: "30 2 * * *",
            unknown_retained: "yes",
          },
        },
      });
    });
  });

  it("saves archive maintenance settings", async () => {
    mocks.sourceSystemConfigApi.getCurrent.mockResolvedValueOnce({
      source_id: "portal",
      config: {
        provider_policy: { default_model: "qwen-max" },
        archive_maintenance: {
          enabled: true,
          cron: "0 3 * * *",
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
        archive_maintenance: {
          enabled: false,
          cron: "30 3 * * *",
          unknown_retained: "yes",
        },
      },
      version: 2,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-21 10:00:00",
    });

    render(<SystemConfigPage />);

    expect(await screen.findByText("文件归档维护")).toBeTruthy();
    expect(screen.getByText("03:00")).toBeTruthy();

    fireEvent.mouseDown(
      screen.getByRole("combobox", { name: "归档维护每日运行时间" }),
    );
    fireEvent.click(await screen.findByText("03:30"));
    fireEvent.click(getArchiveMaintenanceSwitch());
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.sourceSystemConfigApi.updateCurrent).toHaveBeenCalledWith({
        config: {
          provider_policy: { default_model: "qwen-max" },
          archive_maintenance: {
            enabled: false,
            cron: "30 3 * * *",
            unknown_retained: "yes",
          },
        },
      });
    });
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

  it("saves system prompt injections", async () => {
    mocks.sourceSystemConfigApi.getCurrent.mockResolvedValueOnce({
      source_id: "portal",
      config: {
        system_prompt_injections: ["source prompt"],
      },
      version: 1,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-21 10:00:00",
    });
    mocks.sourceSystemConfigApi.updateCurrent.mockResolvedValue({
      source_id: "portal",
      config: {
        system_prompt_injections: ["source prompt", "runtime rule"],
      },
      version: 2,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-21 11:00:00",
    });

    render(<SystemConfigPage />);

    const input = await screen.findByLabelText("系统提示词注入");
    expect(input).toHaveValue("source prompt");

    fireEvent.change(input, {
      target: {
        value: "source prompt\n\nruntime rule\n\nsource prompt",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.sourceSystemConfigApi.updateCurrent).toHaveBeenCalledWith({
        config: {
          system_prompt_injections: ["source prompt", "runtime rule"],
        },
      });
    });
  });

  it("saves model call policy overrides and restores inheritance", async () => {
    seedEffectiveConfig();
    mocks.sourceSystemConfigApi.getCurrent.mockResolvedValueOnce({
      source_id: "portal",
      config: {
        provider_policy: { default_model: "qwen-max" },
        query_retry: {
          enabled: true,
          max_retries: 2,
        },
        llm_rate_limiter: {
          llm_chat_max_concurrent: 1,
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
        llm_rate_limiter: {
          llm_chat_max_concurrent: 1,
          llm_max_qpm: 12,
        },
      },
      version: 2,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-21 11:00:00",
    });

    render(<SystemConfigPage />);

    expect(await screen.findByText("模型调用策略")).toBeTruthy();
    expect(screen.getByText("查询重试")).toBeTruthy();
    expect(screen.getByText("LLM 并发限流")).toBeTruthy();

    fireEvent.click(screen.getAllByRole("button", { name: "恢复继承" })[0]);
    fireEvent.change(screen.getByDisplayValue("100"), {
      target: { value: "12" },
    });
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.sourceSystemConfigApi.updateCurrent).toHaveBeenCalledWith({
        config: {
          provider_policy: { default_model: "qwen-max" },
          llm_rate_limiter: {
            llm_chat_max_concurrent: 1,
            llm_max_qpm: 12,
          },
        },
      });
    });
  });

  it("enables model call policy override without saving page defaults implicitly", async () => {
    seedEffectiveConfig();
    mocks.sourceSystemConfigApi.updateCurrent.mockResolvedValue({
      source_id: "portal",
      config: {
        query_retry: {
          enabled: false,
          max_retries: 3,
          backoff_base: 2,
          backoff_cap: 30,
        },
      },
      version: 1,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-21 11:00:00",
    });

    render(<SystemConfigPage />);

    expect(await screen.findByText("模型调用策略")).toBeTruthy();
    expect(screen.getAllByText("继承 Agent 运行配置").length).toBeGreaterThan(
      0,
    );

    fireEvent.click(screen.getAllByRole("button", { name: "启用覆盖" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.sourceSystemConfigApi.updateCurrent).toHaveBeenCalledWith({
        config: {
          query_retry: {
            enabled: false,
            max_retries: 3,
            backoff_base: 2,
            backoff_cap: 30,
          },
        },
      });
    });
  });

  it("copies effective model call policy values when enabling override", async () => {
    seedEffectiveConfig({
      query_retry: {
        enabled: true,
        max_retries: 5,
        backoff_base: 1.5,
        backoff_cap: 60,
      },
    });
    mocks.sourceSystemConfigApi.updateCurrent.mockResolvedValue({
      source_id: "portal",
      config: {
        query_retry: {
          enabled: true,
          max_retries: 5,
          backoff_base: 1.5,
          backoff_cap: 60,
        },
      },
      version: 1,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-21 11:00:00",
    });

    render(<SystemConfigPage />);

    expect(await screen.findByText("模型调用策略")).toBeTruthy();

    fireEvent.click(screen.getAllByRole("button", { name: "启用覆盖" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.sourceSystemConfigApi.updateCurrent).toHaveBeenCalledWith({
        config: {
          query_retry: {
            enabled: true,
            max_retries: 5,
            backoff_base: 1.5,
            backoff_cap: 60,
          },
        },
      });
    });
  });

  it("waits for effective config before enabling model call policy override", async () => {
    const effectiveDeferred = createDeferred<void>();
    loadEffectiveConfig.mockReturnValueOnce(effectiveDeferred.promise);
    mocks.sourceSystemConfigApi.updateCurrent.mockResolvedValue({
      source_id: "portal",
      config: {
        query_retry: {
          enabled: true,
          max_retries: 5,
          backoff_base: 1.5,
          backoff_cap: 60,
        },
      },
      version: 1,
      is_default: false,
      updated_by: "alice",
      updated_at: "2026-05-21 11:00:00",
    });

    render(<SystemConfigPage />);

    expect(await screen.findByText("模型调用策略")).toBeTruthy();
    expect(
      screen.getAllByRole("button", { name: "启用覆盖" })[0],
    ).toBeDisabled();

    act(() => {
      useSourceSystemConfigStore.setState({
        config: {
          source_id: "portal",
          config: {
            query_retry: {
              enabled: true,
              max_retries: 5,
              backoff_base: 1.5,
              backoff_cap: 60,
            },
          },
          version: 1,
          is_default: false,
          stale: false,
          updated_by: "alice",
          updated_at: "2026-05-21 10:00:00",
        },
        sourceId: "portal",
      });
    });
    await act(async () => {
      effectiveDeferred.resolve(undefined);
      await effectiveDeferred.promise;
    });

    await waitFor(() => {
      expect(
        screen.getAllByRole("button", { name: "启用覆盖" })[0],
      ).toBeEnabled();
    });

    fireEvent.click(screen.getAllByRole("button", { name: "启用覆盖" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => {
      expect(mocks.sourceSystemConfigApi.updateCurrent).toHaveBeenCalledWith({
        config: {
          query_retry: {
            enabled: true,
            max_retries: 5,
            backoff_base: 1.5,
            backoff_cap: 60,
          },
        },
      });
    });
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
    loadEffectiveConfig.mockClear();

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
