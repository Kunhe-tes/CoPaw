import { describe, expect, it } from "vitest";

import { getEventSummary, getLifecycleEvents } from "./overviewModel";

describe("Hook overview model", () => {
  it("returns configured event counts and handler labels in lifecycle order", () => {
    const summary = getEventSummary(
      {
        enabled: true,
        events: {
          PostToolUse: [
            {
              id: "results",
              matcher: { tools: [] },
              hooks: [
                { id: "parse", type: "prompt", prompt: "parse" },
                { id: "record", type: "command", argv: ["echo", "record"] },
              ],
            },
          ],
          PreToolUse: [
            {
              id: "guards",
              matcher: { tools: [] },
              hooks: [
                { id: "validate", type: "http", url: "https://example.test" },
              ],
            },
          ],
        },
      },
      "PostToolUse",
    );

    expect(summary).toMatchObject({
      groups: 1,
      handlers: 2,
      configured: true,
    });
    expect(summary.handlerLabels).toEqual(["Prompt", "Command"]);
    expect(getLifecycleEvents({ enabled: true, events: {} })).toEqual([
      "SessionStart",
      "UserPromptSubmit",
      "PreToolUse",
      "PostToolUse",
      "PostToolUseFailure",
      "BeforeStop",
      "Stop",
    ]);
  });

  it("keeps unconfigured events empty", () => {
    expect(getEventSummary({ enabled: true, events: {} }, "BeforeStop")).toEqual({
      configured: false,
      groups: 0,
      handlers: 0,
      handlerLabels: [],
    });
  });
});
