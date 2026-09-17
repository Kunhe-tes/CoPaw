import { afterEach, describe, expect, it } from "vitest";

import {
  isVoiceRecorderUserAllowed,
  needsChatRecorderClearance,
  shouldShowGlobalVoiceRecorder,
} from "./presentation";

const originalEnv = window.__env__;

describe("GlobalVoiceRecorder presentation boundaries", () => {
  afterEach(() => {
    window.__env__ = originalEnv;
  });

  it("fails closed when the recorder whitelist is missing or empty", () => {
    expect(isVoiceRecorderUserAllowed("SAP001")).toBe(false);

    window.__env__ = { voiceRecorderUserWhitelist: [] };
    expect(isVoiceRecorderUserAllowed("SAP001")).toBe(false);
  });

  it("allows listed users and supports the all-users wildcard", () => {
    window.__env__ = {
      voiceRecorderUserWhitelist: ["SAP001", "SAP002"],
    };
    expect(isVoiceRecorderUserAllowed("SAP001")).toBe(true);
    expect(isVoiceRecorderUserAllowed("SAP003")).toBe(false);
    expect(isVoiceRecorderUserAllowed(null)).toBe(false);

    window.__env__ = { voiceRecorderUserWhitelist: ["*"] };
    expect(isVoiceRecorderUserAllowed(null)).toBe(true);
  });

  it("shows the recorder for an allowed user on any normal page", () => {
    window.__env__ = { voiceRecorderUserWhitelist: ["SAP001"] };
    expect(shouldShowGlobalVoiceRecorder("SAP001", false, false)).toBe(true);
    expect(shouldShowGlobalVoiceRecorder("SAP002", false, false)).toBe(false);
  });

  it("remains hidden in content-only presentation", () => {
    window.__env__ = { voiceRecorderUserWhitelist: ["SAP001"] };
    expect(shouldShowGlobalVoiceRecorder("SAP001", true, false)).toBe(false);
  });

  it("remains hidden for origin=Y URL access", () => {
    window.__env__ = { voiceRecorderUserWhitelist: ["SAP001"] };
    expect(shouldShowGlobalVoiceRecorder("SAP001", false, true)).toBe(false);
  });

  it("adds composer clearance only for Chat routes", () => {
    expect(needsChatRecorderClearance("/chat")).toBe(true);
    expect(needsChatRecorderClearance("/chat/session/123")).toBe(true);
    expect(needsChatRecorderClearance("/models")).toBe(false);
    expect(needsChatRecorderClearance("/voice-transcription")).toBe(false);
  });
});
