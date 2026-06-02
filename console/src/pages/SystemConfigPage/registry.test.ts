import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CURRENT_SOURCE_SYSTEM_CONFIG_SWITCHES,
  writeRegisteredSwitchValue,
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
});
