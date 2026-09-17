export const VOICE_SOP_PROMPT_PREFIX =
  "@wplus-sop-miner 我要澄清一个工作流程，流程是：";

export function buildVoiceSopPrompt(transcript: string): string {
  if (!transcript || transcript.startsWith(VOICE_SOP_PROMPT_PREFIX)) {
    return transcript;
  }
  return `${VOICE_SOP_PROMPT_PREFIX}${transcript}`;
}
