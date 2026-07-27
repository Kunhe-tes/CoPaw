import { describe, expect, it } from "vitest";

import {
  addPromptSegment,
  buildCapabilitySummaries,
  filterCapabilitySummaries,
  movePromptSegment,
  removePromptSegment,
} from "./workbench";

describe("source-system configuration workbench", () => {
  it("marks only the changed capability as unsaved", () => {
    const summaries = buildCapabilitySummaries({
      savedConfig: {},
      draftConfig: { query_retry: { enabled: true } },
      effectiveConfig: { query_retry: { enabled: false, max_retries: 3 } },
    });

    expect(summaries.find((item) => item.id === "model")).toMatchObject({
      state: "unsaved",
      sourceLabel: "继承 Agent 配置",
    });
  });

  it("returns only changed cards for the unsaved filter", () => {
    const summaries = buildCapabilitySummaries({
      savedConfig: {},
      draftConfig: { system_prompt_injections: ["keep replies concise"] },
      effectiveConfig: {},
    });

    expect(
      filterCapabilitySummaries(summaries, "unsaved").map(({ id }) => id),
    ).toEqual(["conversation"]);
  });

  it("keeps shared feature switches scoped to their own capability", () => {
    const summaries = buildCapabilitySummaries({
      savedConfig: {},
      draftConfig: {
        feature_switches: { chat_task_progress_enabled: false },
      },
      effectiveConfig: {},
    });

    expect(summaries.find((item) => item.id === "conversation")?.state).toBe(
      "unsaved",
    );
    expect(summaries.find((item) => item.id === "safety")?.state).toBe(
      "default",
    );
  });

  it("preserves prompt order while adding, moving, and removing", () => {
    expect(addPromptSegment(["first"])).toEqual(["first", ""]);
    expect(movePromptSegment(["first", "second"], 1, -1)).toEqual([
      "second",
      "first",
    ]);
    expect(removePromptSegment(["first", "second"], 0)).toEqual(["second"]);
  });
});
