import { describe, expect, it } from "vitest";

import appSource from "../../App.tsx?raw";
import chatSpeechSource from "../agentscope-chat/Sender/useSpeech.ts?raw";
import runtimeInputSource from "../agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/Input/index.tsx?raw";
import welcomeInputSource from "../agentscope-chat/WelcomeCenterLayout/index.tsx?raw";
import mainLayoutSource from "../../layouts/MainLayout/index.tsx?raw";
import chatPageSource from "../../pages/Chat/index.tsx?raw";
import voiceSettingsSource from "../../pages/Settings/VoiceTranscription/index.tsx?raw";

describe("GlobalVoiceRecorder product boundaries", () => {
  it("mounts the recorder only inside Chat for an allowed user", () => {
    expect(mainLayoutSource).not.toContain("GlobalVoiceRecorder");
    expect(chatPageSource).toContain(
      "<GlobalVoiceRecorder enabled={voiceRecorderEnabled}>",
    );
    expect(chatPageSource).toContain("shouldShowGlobalVoiceRecorder(");
    expect(chatPageSource).toContain(
      'new URLSearchParams(location.search).get("origin") === "Y"',
    );
    expect(runtimeInputSource).toContain("<VoiceRecorderTrigger />");
    expect(welcomeInputSource).toContain("<VoiceRecorderTrigger />");
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
