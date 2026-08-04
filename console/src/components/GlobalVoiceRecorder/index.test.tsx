import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installAudioPlaybackMocks, installClipboardMock } from "./testUtils";
import GlobalVoiceRecorder from "./index";

const mocks = vi.hoisted(() => ({
  message: {
    success: vi.fn(),
    error: vi.fn(),
  },
  recorder: {} as Record<string, unknown>,
  recorderOptions: {} as Record<string, unknown>,
  emitChatInputAppendText: vi.fn(),
  emitChatInputReplaceText: vi.fn(),
}));

vi.mock("@/hooks/useAppMessage", () => ({
  useAppMessage: () => ({ message: mocks.message }),
}));

vi.mock("./useVoiceRecorder", () => ({
  formatRecordingDuration: (durationMs: number) =>
    durationMs >= 1_000 ? "00:01" : "00:00",
  useVoiceRecorder: (options: Record<string, unknown>) => {
    mocks.recorderOptions = options;
    return mocks.recorder;
  },
}));

vi.mock("@/components/agentscope-chat/chatInputDraft", () => ({
  emitChatInputAppendText: mocks.emitChatInputAppendText,
  emitChatInputReplaceText: mocks.emitChatInputReplaceText,
}));

function seedRecorder(overrides: Record<string, unknown> = {}) {
  Object.assign(mocks.recorder, {
    status: "idle",
    supported: true,
    recording: null,
    elapsedMs: 0,
    durationWarning: false,
    stopReason: null,
    error: null,
    transcript: "",
    setTranscript: vi.fn(),
    panelOpen: false,
    setPanelOpen: vi.fn(),
    transcriptionConfigured: false,
    startRecording: vi.fn(async () => true),
    stopRecording: vi.fn(async () => undefined),
    discardRecording: vi.fn(),
    transcribe: vi.fn(async () => undefined),
    ...overrides,
  });
}

function renderRecorder(path = "/models") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <GlobalVoiceRecorder />
    </MemoryRouter>,
  );
}

describe("GlobalVoiceRecorder UI", () => {
  beforeEach(() => {
    seedRecorder();
    mocks.message.success.mockReset();
    mocks.message.error.mockReset();
    mocks.emitChatInputAppendText.mockReset();
    mocks.emitChatInputReplaceText.mockReset();
    installClipboardMock();
    installAudioPlaybackMocks();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders a compact icon launcher and starts recording from idle", () => {
    renderRecorder();

    const launcher = screen.getByRole("button", { name: "开始语音录制" });
    expect(launcher).toBeEnabled();
    expect(launcher.textContent).toBe("");
    fireEvent.click(launcher);
    expect(mocks.recorder.startRecording).toHaveBeenCalledOnce();
  });

  it("keeps unsupported compatibility guidance keyboard discoverable", () => {
    seedRecorder({ status: "unsupported", supported: false });
    renderRecorder();

    expect(screen.getByRole("button", { name: "开始语音录制" })).toBeDisabled();
    expect(
      screen.getByRole("note", {
        name: "当前浏览器不支持所需的麦克风录音 API",
      }),
    ).toHaveAttribute("tabindex", "0");
  });

  it("keeps the active state visible while its workspace is closed", () => {
    seedRecorder({ status: "recording", elapsedMs: 1_000 });
    renderRecorder("/chat/session/1");

    const root = screen.getByTestId("global-voice-recorder");
    expect(root.className).toContain("chatClearance");
    expect(
      screen.getByRole("button", { name: "正在录音 00:01" }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.queryByRole("region", { name: "语音录制面板" }),
    ).not.toBeInTheDocument();
  });

  it("forwards successful transcription only while the current route is chat", () => {
    const chat = renderRecorder("/chat/session/1");

    const notifySuccess = mocks.recorderOptions.onTranscriptionSuccess as (
      text: string,
    ) => void;
    notifySuccess("聊天页转写");
    expect(mocks.emitChatInputAppendText).toHaveBeenCalledWith("聊天页转写");

    chat.unmount();
    mocks.emitChatInputAppendText.mockClear();
    renderRecorder("/models");
    const notifyOutsideChat = mocks.recorderOptions.onTranscriptionSuccess as (
      text: string,
    ) => void;
    notifyOutsideChat("其他页面转写");
    expect(mocks.emitChatInputAppendText).not.toHaveBeenCalled();
  });

  it("renders local playback/download and editable copyable transcript", async () => {
    const recording = {
      file: new File(["wav"], "voice.wav", { type: "audio/wav" }),
      objectUrl: "blob:voice",
      durationMs: 1_000,
      createdAt: 0,
    };
    seedRecorder({
      status: "ready",
      recording,
      transcript: "可编辑文字",
      panelOpen: true,
    });
    const clipboard = installClipboardMock();
    renderRecorder();

    expect(screen.getByLabelText("录音播放控件")).toHaveAttribute(
      "src",
      "blob:voice",
    );
    expect(screen.getByRole("link", { name: /下载 WAV$/ })).toHaveAttribute(
      "download",
      "voice.wav",
    );
    expect(screen.getByLabelText("可编辑的转写文字")).toHaveValue("可编辑文字");
    expect(screen.getByRole("button", { name: /转换文字$/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "生成SOP" })).toBeEnabled();
    expect(screen.getByText("转写接口尚未配置")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /复制$/ }));
    await waitFor(() => {
      expect(clipboard.writeText).toHaveBeenCalledWith("可编辑文字");
    });
    expect(mocks.message.success).toHaveBeenCalled();
  });

  it("generates an SOP draft and replaces the chat input", () => {
    seedRecorder({
      status: "ready",
      panelOpen: true,
      transcript: "先提交申请，再等待审批",
      recording: {
        file: new File(["wav"], "voice.wav", { type: "audio/wav" }),
        objectUrl: "blob:voice",
        durationMs: 1_000,
        createdAt: 0,
      },
    });
    renderRecorder("/chat/session/1");

    fireEvent.click(screen.getByRole("button", { name: "生成SOP" }));

    const sopPrompt =
      "@wplus-sop-miner 我要澄清一个工作流程，流程是：先提交申请，再等待审批";
    expect(mocks.recorder.setTranscript).toHaveBeenCalledWith(sopPrompt);
    expect(mocks.emitChatInputReplaceText).toHaveBeenCalledWith(sopPrompt);
  });

  it("updates the SOP draft without touching chat input outside chat", () => {
    seedRecorder({
      status: "ready",
      panelOpen: true,
      transcript: "执行复核",
      recording: {
        file: new File(["wav"], "voice.wav", { type: "audio/wav" }),
        objectUrl: "blob:voice",
        durationMs: 1_000,
        createdAt: 0,
      },
    });
    renderRecorder("/models");

    fireEvent.click(screen.getByRole("button", { name: "生成SOP" }));

    expect(mocks.recorder.setTranscript).toHaveBeenCalledWith(
      "@wplus-sop-miner 我要澄清一个工作流程，流程是：执行复核",
    );
    expect(mocks.emitChatInputReplaceText).not.toHaveBeenCalled();
  });

  it("requires confirmation before replacing the current WAV and draft", () => {
    seedRecorder({
      status: "ready",
      panelOpen: true,
      recording: {
        file: new File(["wav"], "voice.wav", { type: "audio/wav" }),
        objectUrl: "blob:voice",
        durationMs: 1_000,
        createdAt: 0,
      },
    });
    renderRecorder();

    fireEvent.click(screen.getByRole("button", { name: /重新录制$/ }));
    expect(screen.getByText("替换当前录音？")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "清除并重新录制" }));
    expect(mocks.recorder.startRecording).toHaveBeenCalledWith(true);
  });

  it("offers an explicit retry after automatic transcription fails", () => {
    seedRecorder({
      status: "ready",
      panelOpen: true,
      transcriptionConfigured: true,
      error: {
        code: "transcription-failed",
        detail: "CORS blocked",
      },
      recording: {
        file: new File(["wav"], "voice.wav", { type: "audio/wav" }),
        objectUrl: "blob:voice",
        durationMs: 1_000,
        createdAt: 0,
      },
    });
    renderRecorder();

    const retry = screen.getByRole("button", { name: /重新转换$/ });
    expect(retry).toBeEnabled();
    fireEvent.click(retry);
    expect(mocks.recorder.transcribe).toHaveBeenCalledOnce();
  });
});
