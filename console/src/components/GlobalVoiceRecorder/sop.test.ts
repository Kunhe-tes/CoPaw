import { describe, expect, it } from "vitest";

import { buildVoiceSopPrompt, VOICE_SOP_PROMPT_PREFIX } from "./sop";

describe("buildVoiceSopPrompt", () => {
  it("prefixes a transcription for SOP clarification", () => {
    expect(buildVoiceSopPrompt("先提交申请，再等待审批")).toBe(
      `${VOICE_SOP_PROMPT_PREFIX}先提交申请，再等待审批`,
    );
  });

  it("does not duplicate the SOP prefix", () => {
    const prompt = `${VOICE_SOP_PROMPT_PREFIX}先提交申请`;
    expect(buildVoiceSopPrompt(prompt)).toBe(prompt);
  });

  it("keeps an empty draft empty", () => {
    expect(buildVoiceSopPrompt("")).toBe("");
  });
});
