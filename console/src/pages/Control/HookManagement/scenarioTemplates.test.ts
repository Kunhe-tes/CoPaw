import { describe, expect, it } from "vitest";

import { createScenarioEvent, scenarioTemplates } from "./scenarioTemplates";

describe("Hook scenario templates", () => {
  it("creates an independent complete tool-audit event", () => {
    const event = createScenarioEvent("tool-audit");

    expect(event.event).toBe("PostToolUse");
    expect(event.groups).toHaveLength(1);
    expect(event.groups[0]).toMatchObject({ matcher: { tools: [] } });
    expect(event.groups[0]?.hooks[0]).toMatchObject({
      type: "prompt",
      failPolicy: "allow",
    });
  });

  it("does not share nested template state between creations", () => {
    const first = createScenarioEvent("tool-audit");
    const second = createScenarioEvent("tool-audit");
    first.groups[0]?.hooks.push({ id: "extra", type: "prompt", prompt: "x" });

    expect(second.groups[0]?.hooks).toHaveLength(1);
  });

  it("lists the user-facing complete scenario choices", () => {
    expect(scenarioTemplates.map((template) => template.id)).toEqual([
      "session-start-check",
      "prompt-preprocess",
      "tool-audit",
      "tool-block",
      "failure-alert",
    ]);
  });
});
