import { describe, expect, it, vi } from "vitest";
import { createWelcomeSkillMentions } from "./welcomeSkillMentions";

const items = [
  { id: "skill:browser", type: "skill" as const, label: "browser", name: "browser", description: "Use a browser" },
];

describe("createWelcomeSkillMentions", () => {
  it("retains every selected occurrence instead of truncating the UI selection", () => {
    const setSelectedContextReferences = vi.fn();
    const mentions = createWelcomeSkillMentions({
      contextReferences: items,
      contextReferencesLoading: false,
      isComposingRef: { current: false },
      loadContextReferences: vi.fn(),
      pendingContextReferencesRef: { current: [] },
      selectedContextReferences: [],
      setSelectedContextReferences,
    });

    mentions.skillMentions.onChange([
      ...items,
    ]);

    expect(setSelectedContextReferences).toHaveBeenCalledWith(items);
  });

  it("reflects updated skill selection in welcome props and stages it before submit", async () => {
    const pendingContextReferencesRef = { current: [] as typeof items };
    const setSelectedContextReferences = vi.fn();
    const loadContextReferences = vi.fn();

    const initial = createWelcomeSkillMentions({
      contextReferences: items,
      contextReferencesLoading: false,
      isComposingRef: { current: false },
      loadContextReferences,
      pendingContextReferencesRef,
      selectedContextReferences: [],
      setSelectedContextReferences,
    });
    const updated = createWelcomeSkillMentions({
      contextReferences: items,
      contextReferencesLoading: false,
      isComposingRef: { current: false },
      loadContextReferences,
      pendingContextReferencesRef,
      selectedContextReferences: items,
      setSelectedContextReferences,
    });

    expect(initial.skillMentions.selected).toEqual([]);
    expect(updated.skillMentions.selected).toEqual(items);

    await expect(updated.beforeSubmit()).resolves.toBe(true);
    expect(pendingContextReferencesRef.current).toEqual(items);
    expect(setSelectedContextReferences).toHaveBeenCalledWith([]);
  });

  it("exposes a retry action when the available-skill request failed", () => {
    const loadContextReferences = vi.fn();
    const mentions = createWelcomeSkillMentions({
      contextReferences: [],
      contextReferencesError: true,
      contextReferencesLoading: false,
      isComposingRef: { current: false },
      loadContextReferences,
      pendingContextReferencesRef: { current: [] },
      selectedContextReferences: [],
      setSelectedContextReferences: vi.fn(),
    });

    expect(mentions.skillMentions.error).toBe(true);
    mentions.skillMentions.onRetry?.();
    expect(loadContextReferences).toHaveBeenCalledWith("");
  });
});
