import { describe, expect, it } from "vitest";
import { shouldClearPendingScenarioPreset } from "./scenarioPresetRequest";

describe("shouldClearPendingScenarioPreset", () => {
  it("keeps the first-message scenario selection after a transport failure", () => {
    expect(shouldClearPendingScenarioPreset(undefined)).toBe(false);
  });

  it("clears the selection only after acceptance or a stale-selection conflict", () => {
    expect(shouldClearPendingScenarioPreset(200)).toBe(true);
    expect(shouldClearPendingScenarioPreset(409)).toBe(true);
    expect(shouldClearPendingScenarioPreset(500)).toBe(false);
  });
});
