import { describe, expect, it } from "vitest";
import {
  normalizeSelectableExperts,
  resolveExpertLabel,
  toggleExpertSelection,
} from "./expertSelection";

describe("expert selection helpers", () => {
  it("keeps only valid enabled experts and sorts by display name", () => {
    expect(
      normalizeSelectableExperts([
        {
          definition_id: "z",
          enabled: true,
          valid: true,
          definition: { name: "Zeta", description: "" },
        },
        {
          definition_id: "invalid",
          enabled: true,
          valid: false,
          definition: { name: "Invalid", description: "" },
        },
        {
          definition_id: "disabled",
          enabled: false,
          valid: true,
          definition: { name: "Disabled", description: "" },
        },
        {
          definition_id: "a",
          enabled: true,
          valid: true,
          definition: { name: "Alpha", description: "" },
        },
      ]),
    ).toEqual([
      { id: "a", name: "Alpha", description: "" },
      { id: "z", name: "Zeta", description: "" },
    ]);
  });

  it("toggles expert selection and clears it when plan mode is active", () => {
    expect(toggleExpertSelection(null, "expert-1", false)).toBe("expert-1");
    expect(toggleExpertSelection("expert-1", "expert-1", false)).toBeNull();
    expect(toggleExpertSelection(null, "expert-1", true)).toBeNull();
  });

  it("falls back to the id when an expert name is empty", () => {
    expect(resolveExpertLabel({ id: "expert-1", name: "" })).toBe("expert-1");
  });
});
