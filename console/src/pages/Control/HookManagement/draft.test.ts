import { describe, expect, it } from "vitest";

import {
  addHandler,
  isScriptReference,
  removeHandler,
} from "./draft";
import type { HookConfigDraft } from "./types";

const emptyConfig: HookConfigDraft = { enabled: true, events: {} };

const config: HookConfigDraft = {
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

describe("Hook configuration draft helpers", () => {
  it("adds a command Handler without mutating the source draft", () => {
    const next = addHandler(config, "PreToolUse", "tool-guards", "command");

    expect(next.events.PreToolUse[0]?.hooks.slice(-1)[0]).toMatchObject({
      type: "command",
      argv: [""],
    });
    expect(config.events.PreToolUse[0]?.hooks).toHaveLength(1);
  });

  it("removes only the selected Handler", () => {
    const next = removeHandler(
      config,
      "PreToolUse",
      "tool-guards",
      "guard-shell",
    );

    expect(next.events.PreToolUse[0]?.hooks).toEqual([]);
    expect(config.events.PreToolUse[0]?.hooks).toHaveLength(1);
  });

  it("recognises only controlled script references", () => {
    expect(isScriptReference("hooks/scripts/guard.py")).toBe(true);
    expect(isScriptReference("python")).toBe(false);
    expect(isScriptReference("/tmp/guard.py")).toBe(false);
  });

  it("leaves an unrelated empty configuration structurally valid", () => {
    expect(emptyConfig).toEqual({ enabled: true, events: {} });
  });
});
