import { describe, expect, it, vi } from "vitest";
import { createWelcomeSkillMentions } from "./welcomeSkillMentions";

const items = [{ name: "browser", description: "Use a browser" }];

describe("createWelcomeSkillMentions", () => {
  it("reflects updated skill selection in welcome props and stages it before submit", async () => {
    const pendingSelectedSkillNamesRef = { current: [] as string[] };
    const setSelectedSkillNames = vi.fn();
    const loadEffectiveSkills = vi.fn();

    const initial = createWelcomeSkillMentions({
      effectiveSkills: items,
      effectiveSkillsLoading: false,
      isComposingRef: { current: false },
      loadEffectiveSkills,
      pendingSelectedSkillNamesRef,
      selectedSkillNames: [],
      setSelectedSkillNames,
    });
    const updated = createWelcomeSkillMentions({
      effectiveSkills: items,
      effectiveSkillsLoading: false,
      isComposingRef: { current: false },
      loadEffectiveSkills,
      pendingSelectedSkillNamesRef,
      selectedSkillNames: ["browser"],
      setSelectedSkillNames,
    });

    expect(initial.skillMentions.selected).toEqual([]);
    expect(updated.skillMentions.selected).toEqual(["browser"]);

    await expect(updated.beforeSubmit()).resolves.toBe(true);
    expect(pendingSelectedSkillNamesRef.current).toEqual(["browser"]);
    expect(setSelectedSkillNames).toHaveBeenCalledWith([]);
  });
});
