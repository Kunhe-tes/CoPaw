import { describe, expect, it, vi } from "vitest";
import { createWelcomeSkillMentions } from "./welcomeSkillMentions";

const items = [{ name: "browser", description: "Use a browser" }];

describe("createWelcomeSkillMentions", () => {
  it("retains every selected occurrence instead of truncating the UI selection", () => {
    const setSelectedSkillNames = vi.fn();
    const mentions = createWelcomeSkillMentions({
      effectiveSkills: items,
      effectiveSkillsLoading: false,
      isComposingRef: { current: false },
      loadEffectiveSkills: vi.fn(),
      pendingSelectedSkillNamesRef: { current: [] },
      selectedSkillNames: [],
      setSelectedSkillNames,
    });

    mentions.skillMentions.onChange([
      "browser",
      "browser",
      "browser",
      "browser",
      "browser",
      "browser",
    ]);

    expect(setSelectedSkillNames).toHaveBeenCalledWith([
      "browser",
      "browser",
      "browser",
      "browser",
      "browser",
      "browser",
    ]);
  });

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

  it("exposes a retry action when the available-skill request failed", () => {
    const loadEffectiveSkills = vi.fn();
    const mentions = createWelcomeSkillMentions({
      effectiveSkills: [],
      effectiveSkillsError: true,
      effectiveSkillsLoading: false,
      isComposingRef: { current: false },
      loadEffectiveSkills,
      pendingSelectedSkillNamesRef: { current: [] },
      selectedSkillNames: [],
      setSelectedSkillNames: vi.fn(),
    });

    expect(mentions.skillMentions.error).toBe(true);
    mentions.skillMentions.onRetry?.();
    expect(loadEffectiveSkills).toHaveBeenCalledOnce();
  });
});
