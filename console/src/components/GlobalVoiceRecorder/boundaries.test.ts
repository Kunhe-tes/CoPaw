import { describe, expect, it } from "vitest";

import appSource from "../../App.tsx?raw";
import chatSpeechSource from "../agentscope-chat/Sender/useSpeech.ts?raw";
import mainLayoutSource from "../../layouts/MainLayout/index.tsx?raw";
import voiceSettingsSource from "../../pages/Settings/VoiceTranscription/index.tsx?raw";

describe("GlobalVoiceRecorder product boundaries", () => {
  it("mounts outside routed content only for an allowed iframe user", () => {
    expect(mainLayoutSource).toContain(
      "shouldShowGlobalVoiceRecorder(\n        voiceRecorderUserId,\n        showContentOnly,\n        isOriginY,\n      )",
    );
    expect(mainLayoutSource).toContain("<GlobalVoiceRecorder />");
    expect(mainLayoutSource).toContain(
      "const voiceRecorderUserId = useIframeStore((state) => state.userId)",
    );
    expect(mainLayoutSource).toContain(
      'new URLSearchParams(location.search).get("origin") === "Y"',
    );
    expect(mainLayoutSource).not.toContain(
      "shouldShowGlobalVoiceRecorder(hideMenu",
    );
  });

  it("keeps Login outside the authenticated MainLayout", () => {
    expect(appSource).toContain(
      '<Route path="/login" element={<LoginPage />} />',
    );
    expect(appSource).toContain("<AuthGuard>");
    expect(appSource).toContain("<MainLayout />");
  });

  it("does not couple the existing Chat speech-to-text control or Voice settings", () => {
    expect(chatSpeechSource).toContain("SpeechRecognition");
    expect(chatSpeechSource).not.toContain("GlobalVoiceRecorder");
    expect(chatSpeechSource).not.toContain("transcribeRecording");
    expect(voiceSettingsSource).not.toContain("GlobalVoiceRecorder");
    expect(voiceSettingsSource).not.toContain("transcribeRecording");
  });
});
