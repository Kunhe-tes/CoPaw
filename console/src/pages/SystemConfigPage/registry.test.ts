import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CRON_TASK_SESSION_CLEANUP_RUN_TIME_OPTIONS,
  CURRENT_SOURCE_SYSTEM_CONFIG_SWITCHES,
  clearModelCallPolicyConfig,
  enableModelCallPolicyConfig,
  normalizeSystemPromptInjections,
  readCronTaskSessionCleanupConfig,
  readCronUnreadAutoPauseConfig,
  readLlmRateLimiterConfigState,
  readQueryRetryConfigState,
  readSystemPromptInjections,
  validateSourceSystemConfig,
  writeCronTaskSessionCleanupValue,
  writeCronUnreadAutoPauseValue,
  writeLlmRateLimiterValue,
  writeQueryRetryValue,
  writeRegisteredSwitchValue,
  writeSystemPromptInjections,
  writeToolResultCompactValue,
} from "./registry";

describe("SystemConfigPage registry compatibility", () => {
  const originalStructuredClone = globalThis.structuredClone;

  afterEach(() => {
    vi.unstubAllGlobals();
    if (originalStructuredClone) {
      globalThis.structuredClone = originalStructuredClone;
    } else {
      delete (globalThis as typeof globalThis & { structuredClone?: unknown })
        .structuredClone;
    }
  });

  it("writes switch values without requiring native structuredClone", () => {
    vi.stubGlobal("structuredClone", undefined);
    const source = {
      provider_policy: { default_model: "qwen-max" },
    };

    const next = writeRegisteredSwitchValue(
      source,
      CURRENT_SOURCE_SYSTEM_CONFIG_SWITCHES[0],
      false,
    );

    expect(next).toEqual({
      provider_policy: { default_model: "qwen-max" },
      feature_switches: { chat_task_progress_enabled: false },
    });
    expect(source).toEqual({
      provider_policy: { default_model: "qwen-max" },
    });
  });

  it("preserves nested tool config keys without native structuredClone", () => {
    vi.stubGlobal("structuredClone", undefined);
    const source = {
      tool_result_compact: {
        recent_max_bytes: 12000,
        unknown_retained: "yes",
      },
    };

    const next = writeToolResultCompactValue(source, "recent_max_bytes", 16000);

    expect(next).toEqual({
      tool_result_compact: {
        recent_max_bytes: 16000,
        unknown_retained: "yes",
      },
    });
    expect(source.tool_result_compact.recent_max_bytes).toBe(12000);
  });

  it("reads default cron unread auto pause settings", () => {
    expect(readCronUnreadAutoPauseConfig({})).toEqual({
      enabled: true,
      threshold: 10,
    });
  });

  it("reads default cron task session cleanup settings", () => {
    expect(readCronTaskSessionCleanupConfig({})).toEqual({
      enabled: false,
      retention_days: 30,
      run_time: "01:00",
      cron: "0 1 * * *",
    });
  });

  it("offers selectable cron task session cleanup run times", () => {
    expect(CRON_TASK_SESSION_CLEANUP_RUN_TIME_OPTIONS).toContain("01:00");
    expect(CRON_TASK_SESSION_CLEANUP_RUN_TIME_OPTIONS).toContain("02:30");
    expect(CRON_TASK_SESSION_CLEANUP_RUN_TIME_OPTIONS).toHaveLength(48);
  });

  it("writes cron task session cleanup settings without mutating source", () => {
    vi.stubGlobal("structuredClone", undefined);
    const source = {
      provider_policy: { default_model: "qwen-max" },
      cron_task_session_cleanup: {
        enabled: true,
        unknown_retained: "yes",
      },
    };

    const next = writeCronTaskSessionCleanupValue(source, "run_time", "02:30");

    expect(next).toEqual({
      provider_policy: { default_model: "qwen-max" },
      cron_task_session_cleanup: {
        enabled: true,
        unknown_retained: "yes",
        cron: "30 2 * * *",
      },
    });
    expect(source.cron_task_session_cleanup).toEqual({
      enabled: true,
      unknown_retained: "yes",
    });
  });

  it("rejects invalid cron task session cleanup values", () => {
    expect(
      validateSourceSystemConfig({
        cron_task_session_cleanup: {
          enabled: true,
          retention_days: 0,
          cron: "0 1 * * *",
        },
      }),
    ).toContain("1");
    expect(
      validateSourceSystemConfig({
        cron_task_session_cleanup: {
          enabled: true,
          retention_days: 30,
          cron: "*/5 * * * *",
        },
      }),
    ).toContain("cron");
  });

  it("writes cron unread auto pause settings without mutating source", () => {
    vi.stubGlobal("structuredClone", undefined);
    const source = {
      provider_policy: { default_model: "qwen-max" },
      cron_unread_auto_pause: {
        enabled: true,
      },
    };

    const next = writeCronUnreadAutoPauseValue(source, "threshold", 12);

    expect(next).toEqual({
      provider_policy: { default_model: "qwen-max" },
      cron_unread_auto_pause: {
        enabled: true,
        threshold: 12,
      },
    });
    expect(source.cron_unread_auto_pause).toEqual({
      enabled: true,
    });
  });

  it("keeps query retry inherited until explicitly enabled", () => {
    expect(readQueryRetryConfigState({})).toEqual({
      explicit: false,
      config: {
        enabled: false,
        max_retries: 3,
        backoff_base: 2,
        backoff_cap: 30,
      },
    });

    const next = enableModelCallPolicyConfig({}, "query_retry");

    expect(next).toEqual({
      query_retry: {
        enabled: false,
        max_retries: 3,
        backoff_base: 2,
        backoff_cap: 30,
      },
    });
  });

  it("reads model call policy defaults from effective config", () => {
    expect(
      readQueryRetryConfigState(
        {},
        {
          query_retry: {
            enabled: true,
            max_retries: 5,
            backoff_base: 1.5,
            backoff_cap: 60,
          },
        },
      ),
    ).toEqual({
      explicit: false,
      config: {
        enabled: true,
        max_retries: 5,
        backoff_base: 1.5,
        backoff_cap: 60,
      },
    });

    expect(
      enableModelCallPolicyConfig({}, "llm_rate_limiter", {
        llm_rate_limiter: {
          llm_max_concurrent: 8,
          llm_chat_max_concurrent: 4,
          llm_cron_max_concurrent: 6,
          llm_max_qpm: 200,
          llm_rate_limit_pause: 7,
          llm_rate_limit_jitter: 2,
          llm_acquire_timeout: 600,
          llm_chat_acquire_timeout: 120,
          llm_cron_acquire_timeout: null,
        },
      }),
    ).toEqual({
      llm_rate_limiter: {
        llm_max_concurrent: 8,
        llm_chat_max_concurrent: 4,
        llm_cron_max_concurrent: 6,
        llm_max_qpm: 200,
        llm_rate_limit_pause: 7,
        llm_rate_limit_jitter: 2,
        llm_acquire_timeout: 600,
        llm_chat_acquire_timeout: 120,
        llm_cron_acquire_timeout: null,
      },
    });
  });

  it("writes and clears query retry overrides without mutating source", () => {
    vi.stubGlobal("structuredClone", undefined);
    const source = {
      provider_policy: { default_model: "qwen-max" },
      query_retry: {
        enabled: true,
        unknown_retained: "yes",
      },
    };

    const next = writeQueryRetryValue(source, "max_retries", 2);
    const cleared = clearModelCallPolicyConfig(next, "query_retry");

    expect(next).toEqual({
      provider_policy: { default_model: "qwen-max" },
      query_retry: {
        enabled: true,
        max_retries: 2,
        unknown_retained: "yes",
      },
    });
    expect(cleared).toEqual({
      provider_policy: { default_model: "qwen-max" },
    });
    expect(source.query_retry).toEqual({
      enabled: true,
      unknown_retained: "yes",
    });
  });

  it("keeps llm rate limiter inherited until explicitly enabled", () => {
    expect(readLlmRateLimiterConfigState({})).toEqual({
      explicit: false,
      config: {
        llm_max_concurrent: 5,
        llm_chat_max_concurrent: 2,
        llm_cron_max_concurrent: 3,
        llm_max_qpm: 100,
        llm_rate_limit_pause: 5,
        llm_rate_limit_jitter: 1,
        llm_acquire_timeout: 300,
        llm_chat_acquire_timeout: null,
        llm_cron_acquire_timeout: null,
      },
    });
  });

  it("writes and clears llm rate limiter overrides without mutating source", () => {
    vi.stubGlobal("structuredClone", undefined);
    const source = {
      provider_policy: { default_model: "qwen-max" },
      llm_rate_limiter: {
        llm_chat_max_concurrent: 1,
        unknown_retained: "yes",
      },
    };

    const next = writeLlmRateLimiterValue(source, "llm_max_qpm", 12);
    const cleared = clearModelCallPolicyConfig(next, "llm_rate_limiter");

    expect(next).toEqual({
      provider_policy: { default_model: "qwen-max" },
      llm_rate_limiter: {
        llm_chat_max_concurrent: 1,
        llm_max_qpm: 12,
        unknown_retained: "yes",
      },
    });
    expect(cleared).toEqual({
      provider_policy: { default_model: "qwen-max" },
    });
    expect(source.llm_rate_limiter).toEqual({
      llm_chat_max_concurrent: 1,
      unknown_retained: "yes",
    });
  });

  it("rejects invalid cron unread auto pause threshold", () => {
    expect(
      validateSourceSystemConfig({
        cron_unread_auto_pause: {
          enabled: true,
          threshold: 0,
        },
      }),
    ).toContain("1");
  });

  it("normalizes system prompt injections", () => {
    expect(
      normalizeSystemPromptInjections([" keep ", "", "keep", "next\nline"]),
    ).toEqual(["keep", "next\nline"]);
  });

  it("reads default system prompt injections", () => {
    expect(readSystemPromptInjections({})).toEqual([]);
  });

  it("writes system prompt injections without mutating source", () => {
    vi.stubGlobal("structuredClone", undefined);
    const source = {
      provider_policy: { default_model: "qwen-max" },
      system_prompt_injections: ["old"],
    };

    const next = writeSystemPromptInjections(source, [
      " keep ",
      "",
      "keep",
      "next",
    ]);

    expect(next).toEqual({
      provider_policy: { default_model: "qwen-max" },
      system_prompt_injections: ["keep", "next"],
    });
    expect(source.system_prompt_injections).toEqual(["old"]);
  });

  it("clears system prompt injections when no prompts remain", () => {
    const next = writeSystemPromptInjections(
      {
        provider_policy: { default_model: "qwen-max" },
        system_prompt_injections: ["old"],
      },
      [" ", ""],
    );

    expect(next).toEqual({
      provider_policy: { default_model: "qwen-max" },
    });
  });
});
