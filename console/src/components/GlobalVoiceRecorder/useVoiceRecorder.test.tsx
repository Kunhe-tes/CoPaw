import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { BrowserPcmCaptureHandlers } from "./browserPcmCapture";
import { ControlledPcmCapture, installObjectUrlMocks } from "./testUtils";
import type { VoiceTranscriptionAdapter } from "./transcription";
import { useVoiceRecorder } from "./useVoiceRecorder";

describe("useVoiceRecorder", () => {
  let captures: ControlledPcmCapture[];
  let objectUrls: ReturnType<typeof installObjectUrlMocks>;
  const transcriptionAdapter: VoiceTranscriptionAdapter = {
    url: "https://speech.example.test",
    buildRequest: (file) => ({ method: "POST", body: file }),
    extractText: async (response) => response.text(),
  };

  const createCapture = (handlers: BrowserPcmCaptureHandlers) => {
    const capture = new ControlledPcmCapture(handlers);
    captures.push(capture);
    return capture;
  };

  beforeEach(() => {
    captures = [];
    objectUrls = installObjectUrlMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("exposes the unsupported state without requesting a microphone", () => {
    const { result } = renderHook(() =>
      useVoiceRecorder({
        createCapture,
        isCaptureSupported: () => false,
      }),
    );

    expect(result.current.status).toBe("unsupported");
    expect(captures).toHaveLength(0);
  });

  it("surfaces permission denial with an open recovery workspace", async () => {
    const deniedError = new Error("Permission denied");
    deniedError.name = "NotAllowedError";
    const stop = vi.fn(async () => undefined);
    const { result } = renderHook(() =>
      useVoiceRecorder({
        createCapture: () => ({
          start: vi.fn(async () => {
            throw deniedError;
          }),
          stop,
        }),
        isCaptureSupported: () => true,
      }),
    );

    await act(async () => {
      await result.current.startRecording();
    });

    expect(result.current.status).toBe("permission-denied");
    expect(result.current.error?.code).toBe("permission-denied");
    expect(result.current.panelOpen).toBe(true);
  });

  it("retains one WAV across rerenders and revokes it on confirmed replacement", async () => {
    const { result, rerender, unmount } = renderHook(() =>
      useVoiceRecorder({
        createCapture,
        isCaptureSupported: () => true,
      }),
    );

    await act(async () => {
      await result.current.startRecording();
    });
    act(() => {
      captures[0].emit(new Float32Array(1_600).fill(0.25));
    });
    await act(async () => {
      await result.current.stopRecording();
    });

    const firstRecording = result.current.recording;
    expect(result.current.status).toBe("ready");
    expect(firstRecording?.file.name.endsWith(".wav")).toBe(true);
    expect(firstRecording?.file.type).toBe("audio/wav");
    expect(firstRecording?.durationMs).toBe(100);
    expect(result.current.panelOpen).toBe(true);
    rerender();
    expect(result.current.recording).toBe(firstRecording);

    act(() => result.current.setTranscript("需要一并清除"));
    await act(async () => {
      await result.current.startRecording(true);
    });
    expect(objectUrls.revokeObjectURL).toHaveBeenCalledWith(
      "blob:voice-recording",
    );
    expect(result.current.recording).toBeNull();
    expect(result.current.transcript).toBe("");
    expect(result.current.status).toBe("recording");

    unmount();
    expect(captures[1].stop).toHaveBeenCalledOnce();
  });

  it("uses monotonic time for warning and automatically stops at the limit", async () => {
    vi.useFakeTimers();
    let now = 0;
    let resolveResponse!: (response: Response) => void;
    const fetchMock = vi.fn<typeof fetch>(
      () =>
        new Promise<Response>((resolve) => {
          resolveResponse = resolve;
        }),
    );
    const { result } = renderHook(() =>
      useVoiceRecorder({
        createCapture,
        isCaptureSupported: () => true,
        now: () => now,
        warningMs: 900,
        limitMs: 1_000,
        transcriptionAdapter,
        fetchImplementation: fetchMock,
      }),
    );

    await act(async () => {
      await result.current.startRecording();
    });
    act(() => {
      captures[0].emit(new Float32Array(1_600).fill(0.1));
      now = 950;
      vi.advanceTimersByTime(200);
    });
    expect(result.current.durationWarning).toBe(true);
    expect(result.current.status).toBe("recording");

    await act(async () => {
      now = 1_000;
      vi.advanceTimersByTime(200);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.status).toBe("transcribing");
    expect(result.current.stopReason).toBe("limit");
    expect(captures[0].stop).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledOnce();

    let autoRequest!: Promise<void>;
    act(() => {
      autoRequest = result.current.transcribe();
    });
    await act(async () => {
      resolveResponse(new Response("达到上限后的文字"));
      await autoRequest;
    });
    expect(result.current.status).toBe("ready");
    expect(result.current.transcript).toBe("达到上限后的文字");
  });

  it("finalizes valid PCM on device interruption and errors for empty audio", async () => {
    let resolveResponse!: (response: Response) => void;
    const fetchMock = vi.fn<typeof fetch>(
      () =>
        new Promise<Response>((resolve) => {
          resolveResponse = resolve;
        }),
    );
    const first = renderHook(() =>
      useVoiceRecorder({
        createCapture,
        isCaptureSupported: () => true,
        transcriptionAdapter,
        fetchImplementation: fetchMock,
      }),
    );
    await act(async () => {
      await first.result.current.startRecording();
    });
    act(() => {
      captures[0].emit(new Float32Array(320).fill(0.2));
    });
    await act(async () => {
      captures[0].interrupt();
      await Promise.resolve();
    });
    expect(first.result.current.status).toBe("transcribing");
    expect(first.result.current.stopReason).toBe("interrupted");
    expect(first.result.current.error?.code).toBe("device-interrupted");
    expect(first.result.current.recording).not.toBeNull();
    expect(fetchMock).toHaveBeenCalledOnce();

    let autoRequest!: Promise<void>;
    act(() => {
      autoRequest = first.result.current.transcribe();
    });
    await act(async () => {
      resolveResponse(new Response("中断前的文字"));
      await autoRequest;
    });
    expect(first.result.current.status).toBe("ready");
    expect(first.result.current.transcript).toBe("中断前的文字");
    expect(first.result.current.error?.code).toBe("device-interrupted");
    first.unmount();

    const second = renderHook(() =>
      useVoiceRecorder({
        createCapture,
        isCaptureSupported: () => true,
      }),
    );
    await act(async () => {
      await second.result.current.startRecording();
    });
    await act(async () => {
      captures[1].interrupt();
      await Promise.resolve();
    });
    expect(second.result.current.status).toBe("error");
    expect(second.result.current.error?.code).toBe("device-interrupted");
    expect(second.result.current.recording).toBeNull();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("automatically transcribes once and preserves WAV/draft after retry failure", async () => {
    let resolveResponse!: (response: Response) => void;
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            resolveResponse = resolve;
          }),
      )
      .mockRejectedValueOnce(new TypeError("CORS blocked"));
    const onTranscriptionSuccess = vi.fn();
    const { result } = renderHook(() =>
      useVoiceRecorder({
        createCapture,
        isCaptureSupported: () => true,
        transcriptionAdapter,
        fetchImplementation: fetchMock,
        onTranscriptionSuccess,
      }),
    );

    await act(async () => {
      await result.current.startRecording();
    });
    act(() => captures[0].emit(new Float32Array(160).fill(0.1)));
    await act(async () => {
      await result.current.stopRecording();
    });
    const recording = result.current.recording;
    expect(result.current.status).toBe("transcribing");
    expect(fetchMock).toHaveBeenCalledOnce();

    let firstRequest!: Promise<void>;
    let duplicateRequest!: Promise<void>;
    act(() => {
      firstRequest = result.current.transcribe();
      duplicateRequest = result.current.transcribe();
    });
    expect(firstRequest).toBe(duplicateRequest);
    expect(fetchMock).toHaveBeenCalledOnce();
    await act(async () => {
      resolveResponse(new Response("识别完成"));
      await firstRequest;
    });
    expect(result.current.transcript).toBe("识别完成");
    expect(onTranscriptionSuccess).toHaveBeenCalledOnce();
    expect(onTranscriptionSuccess).toHaveBeenCalledWith("识别完成");

    act(() => result.current.setTranscript("保留的草稿"));
    await act(async () => {
      await result.current.transcribe();
    });
    expect(result.current.status).toBe("ready");
    expect(result.current.error?.code).toBe("transcription-failed");
    expect(result.current.transcript).toBe("保留的草稿");
    expect(result.current.recording).toBe(recording);
    expect(onTranscriptionSuccess).toHaveBeenCalledOnce();
  });

  it("does not automatically request transcription while the adapter is unconfigured", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    const { result } = renderHook(() =>
      useVoiceRecorder({
        createCapture,
        isCaptureSupported: () => true,
        fetchImplementation: fetchMock,
      }),
    );

    await act(async () => {
      await result.current.startRecording();
    });
    act(() => captures[0].emit(new Float32Array(160).fill(0.1)));
    await act(async () => {
      await result.current.stopRecording();
    });

    expect(result.current.status).toBe("ready");
    expect(result.current.recording).not.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("cleans capture buffers and object URLs on page teardown", async () => {
    const { result, unmount } = renderHook(() =>
      useVoiceRecorder({
        createCapture,
        isCaptureSupported: () => true,
      }),
    );
    await act(async () => {
      await result.current.startRecording();
    });
    act(() => captures[0].emit(new Float32Array(160).fill(0.1)));
    await act(async () => {
      await result.current.stopRecording();
    });

    unmount();
    expect(objectUrls.revokeObjectURL).toHaveBeenCalledWith(
      "blob:voice-recording",
    );
  });
});
