import { describe, expect, it } from "vitest";
import { payloadFromValues } from "./index";

describe("expert model selection", () => {
  it("keeps the selected provider and model in the expert payload", () => {
    expect(
      payloadFromValues({
        name: "reviewer",
        description: "Review changes",
        instruction: "Review carefully",
        keywordsText: "review",
        skillsText: [],
        mcpsText: [],
        model: { provider: "openai", id: "gpt-5.4" },
      }),
    ).toMatchObject({
      model: { provider: "openai", id: "gpt-5.4" },
    });
  });

  it("uses null for the inherit-current-chat-model choice", () => {
    expect(
      payloadFromValues({
        name: "reviewer",
        description: "Review changes",
        instruction: "Review carefully",
        model: "",
      }).model,
    ).toBeNull();
  });
});
