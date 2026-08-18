import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installAudioPlaybackMocks } from "./testUtils";
import GlobalVoiceRecorder from "./index";
import VoiceRecorderQuickMenuItem from "./VoiceRecorderQuickMenuItem";
import VoiceRecorderTrigger from "./VoiceRecorderTrigger";

const mocks = vi.hoisted(() => ({
  recorder: {} as Record<string, unknown>,
  recorderOptions: {} as Record<string, unknown>,
  emitChatInputAppendText: vi.fn(),
  emitChatInputReplaceText: vi.fn(),
}));

vi.mock("@agentscope-ai/icons", () => ({
  SparkMicLine: () => <span data-testid="mic-icon" />,
  SparkMicOnLine: () => <span data-testid="mic-on-icon" />,
}));

vi.mock("@agentscope-ai/design", () => ({
  IconButton: ({
    bordered,
    icon,
    ...props
  }: ButtonHTMLAttributes<HTMLButtonElement> & {
    bordered?: boolean;
    icon?: ReactNode;
  }) => {
    void bordered;
    return (
      <button type="button" {...props}>
        {icon}
      </button>
    );
  },
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

function renderRecorder(enabled = true) {
  return render(
    <GlobalVoiceRecorder enabled={enabled}>
      <div data-testid="recorder-child">聊天内容</div>
      <VoiceRecorderTrigger />
    </GlobalVoiceRecorder>,
  );
}

function renderRecorderQuickMenuItem(enabled = true) {
  return render(
    <GlobalVoiceRecorder enabled={enabled}>
      <VoiceRecorderQuickMenuItem />
    </GlobalVoiceRecorder>,
  );
}

describe("GlobalVoiceRecorder UI", () => {
  beforeEach(() => {
    seedRecorder();
    mocks.emitChatInputAppendText.mockReset();
    mocks.emitChatInputReplaceText.mockReset();
    installAudioPlaybackMocks();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders an inline trigger and starts recording from idle", () => {
    renderRecorder();

    const launcher = screen.getByRole("button", { name: "开始语音录制" });
    expect(launcher).toBeEnabled();
    expect(launcher.textContent).toBe("");
    fireEvent.click(launcher);
    expect(mocks.recorder.startRecording).toHaveBeenCalledOnce();
  });

  it("renders a labelled quick menu item and starts recording from idle", () => {
    renderRecorderQuickMenuItem();

    const launcher = screen.getByRole("button", { name: "语音录制" });
    expect(launcher).toBeEnabled();
    expect(launcher).toHaveTextContent("语音录制");
    fireEvent.click(launcher);
    expect(mocks.recorder.startRecording).toHaveBeenCalledOnce();
  });

  it("renders only its children when voice recording is not enabled", () => {
    renderRecorder(false);

    expect(screen.getByTestId("recorder-child")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "开始语音录制" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("global-voice-recorder"),
    ).not.toBeInTheDocument();
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
    renderRecorder();

    const root = screen.getByTestId("global-voice-recorder");
    expect(root.className).toContain("chatClearance");
    expect(
      screen.getByRole("button", { name: "正在录音 00:01" }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.queryByRole("region", { name: "语音录制面板" }),
    ).not.toBeInTheDocument();
  });

  it("forwards successful transcription to the chat input", () => {
    renderRecorder();
    const notifySuccess = mocks.recorderOptions.onTranscriptionSuccess as (
      text: string,
    ) => void;
    notifySuccess("聊天页转写");
    expect(mocks.emitChatInputAppendText).toHaveBeenCalledWith("聊天页转写");
  });

  it("renders local playback/download controls without a duplicate transcript draft", () => {
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
    renderRecorder();

    expect(screen.getByLabelText("录音播放控件")).toHaveAttribute(
      "src",
      "blob:voice",
    );
    expect(screen.getByRole("link", { name: /下载 WAV$/ })).toHaveAttribute(
      "download",
      "voice.wav",
    );
    expect(screen.queryByLabelText("可编辑的转写文字")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "复制" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /转换文字$/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "生成SOP" })).toBeEnabled();
    expect(screen.getByText("转写接口尚未配置")).toBeInTheDocument();
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
    renderRecorder();

    fireEvent.click(screen.getByRole("button", { name: "生成SOP" }));

    const sopPrompt =
      "@wplus-sop-miner 我要澄清一个工作流程，流程是：先提交申请，再等待审批";
    expect(mocks.emitChatInputReplaceText).toHaveBeenCalledWith(sopPrompt);
  });

  it("requires confirmation before replacing the current WAV and transcript", () => {
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

    expect(screen.getByRole("button", { name: "生成SOP" })).toBeDisabled();
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
