import { useCallback, useEffect, useRef, useState } from "react";

import {
  BrowserPcmCapture,
  type BrowserPcmCaptureHandlers,
  isBrowserPcmCaptureSupported,
} from "./browserPcmCapture";
import { mergePcmChunks, VOICE_WAV_SAMPLE_RATE } from "./audio";
import {
  defaultVoiceTranscriptionAdapter,
  isVoiceTranscriptionConfigured,
  transcribeRecording,
  type VoiceTranscriptionAdapter,
} from "./transcription";
import type {
  VoiceRecorderError,
  VoiceRecorderStatus,
  VoiceRecording,
} from "./types";
import { createVoiceRecordingFile } from "./wav";

export const VOICE_RECORDING_WARNING_MS = 9 * 60 * 1_000;
export const VOICE_RECORDING_LIMIT_MS = 10 * 60 * 1_000;

export type VoiceRecordingStopReason = "manual" | "limit" | "interrupted";

interface PcmCapture {
  start: () => Promise<void>;
  stop: () => Promise<void>;
}

const defaultCaptureFactory = (handlers: BrowserPcmCaptureHandlers) =>
  new BrowserPcmCapture(handlers);
const defaultNow = () => performance.now();

export interface UseVoiceRecorderOptions {
  createCapture?: (handlers: BrowserPcmCaptureHandlers) => PcmCapture;
  isCaptureSupported?: () => boolean;
  now?: () => number;
  warningMs?: number;
  limitMs?: number;
  transcriptionAdapter?: VoiceTranscriptionAdapter;
  fetchImplementation?: typeof fetch;
  onTranscriptionSuccess?: (text: string) => void;
}

function captureErrorFrom(error: unknown): VoiceRecorderError {
  const name =
    typeof error === "object" && error && "name" in error
      ? String(error.name)
      : "";
  const detail = error instanceof Error ? error.message : String(error);
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return { code: "permission-denied", detail };
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return { code: "device-unavailable", detail };
  }
  return { code: "capture-failed", detail };
}

export function formatRecordingDuration(durationMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1_000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(
    2,
    "0",
  )}`;
}

export function useVoiceRecorder(options: UseVoiceRecorderOptions = {}) {
  const createCapture = options.createCapture ?? defaultCaptureFactory;
  const isCaptureSupported =
    options.isCaptureSupported ?? isBrowserPcmCaptureSupported;
  const now = options.now ?? defaultNow;
  const warningMs = options.warningMs ?? VOICE_RECORDING_WARNING_MS;
  const limitMs = options.limitMs ?? VOICE_RECORDING_LIMIT_MS;
  const transcriptionAdapter =
    options.transcriptionAdapter ?? defaultVoiceTranscriptionAdapter;
  const fetchImplementation = options.fetchImplementation ?? fetch;
  const onTranscriptionSuccess = options.onTranscriptionSuccess;

  const supported = isCaptureSupported();
  const [status, setStatus] = useState<VoiceRecorderStatus>(
    supported ? "idle" : "unsupported",
  );
  const [recording, setRecording] = useState<VoiceRecording | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [durationWarning, setDurationWarning] = useState(false);
  const [stopReason, setStopReason] = useState<VoiceRecordingStopReason | null>(
    null,
  );
  const [error, setError] = useState<VoiceRecorderError | null>(null);
  const [transcript, setTranscript] = useState("");
  const [panelOpen, setPanelOpen] = useState(false);

  const mountedRef = useRef(true);
  const statusRef = useRef(status);
  const recordingRef = useRef<VoiceRecording | null>(null);
  const captureRef = useRef<PcmCapture | null>(null);
  const pcmChunksRef = useRef<Float32Array[]>([]);
  const pcmSampleCountRef = useRef(0);
  const startedAtRef = useRef(0);
  const timerRef = useRef<number | null>(null);
  const finalizingRef = useRef<Promise<void> | null>(null);
  const transcriptionPromiseRef = useRef<Promise<void> | null>(null);
  const transcriptionAbortRef = useRef<AbortController | null>(null);

  const updateStatus = useCallback((nextStatus: VoiceRecorderStatus) => {
    statusRef.current = nextStatus;
    if (mountedRef.current) {
      setStatus(nextStatus);
    }
  }, []);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const revokeRecording = useCallback(() => {
    const current = recordingRef.current;
    if (current) {
      URL.revokeObjectURL(current.objectUrl);
      recordingRef.current = null;
    }
    if (mountedRef.current) {
      setRecording(null);
    }
  }, []);

  const runTranscription = useCallback(
    (targetRecording: VoiceRecording): Promise<void> => {
      if (transcriptionPromiseRef.current) {
        return transcriptionPromiseRef.current;
      }
      if (!isVoiceTranscriptionConfigured(transcriptionAdapter)) {
        return Promise.resolve();
      }

      setError((currentError) =>
        currentError?.code === "transcription-failed" ? null : currentError,
      );
      updateStatus("transcribing");
      const abortController = new AbortController();
      transcriptionAbortRef.current = abortController;
      const request = transcribeRecording(
        targetRecording.file,
        transcriptionAdapter,
        fetchImplementation,
        abortController.signal,
      )
        .then((text) => {
          if (mountedRef.current && recordingRef.current === targetRecording) {
            setTranscript(text);
            onTranscriptionSuccess?.(text);
          }
        })
        .catch((transcriptionError: unknown) => {
          if (mountedRef.current && recordingRef.current === targetRecording) {
            setError({
              code: "transcription-failed",
              detail:
                transcriptionError instanceof Error
                  ? transcriptionError.message
                  : String(transcriptionError),
            });
          }
        })
        .finally(() => {
          if (transcriptionPromiseRef.current === request) {
            transcriptionPromiseRef.current = null;
            transcriptionAbortRef.current = null;
            if (
              mountedRef.current &&
              recordingRef.current === targetRecording
            ) {
              updateStatus("ready");
            }
          }
        });
      transcriptionPromiseRef.current = request;
      return request;
    },
    [
      fetchImplementation,
      onTranscriptionSuccess,
      transcriptionAdapter,
      updateStatus,
    ],
  );

  const finalizeRecording = useCallback(
    (reason: VoiceRecordingStopReason): Promise<void> => {
      if (finalizingRef.current) {
        return finalizingRef.current;
      }

      const finalize = async () => {
        clearTimer();
        updateStatus("processing");
        const capture = captureRef.current;
        captureRef.current = null;
        try {
          await capture?.stop();
        } catch {
          // Cleanup remains best-effort; captured PCM can still be finalized.
        }

        const samples = mergePcmChunks(pcmChunksRef.current);
        pcmChunksRef.current = [];
        pcmSampleCountRef.current = 0;
        if (samples.length === 0) {
          if (mountedRef.current) {
            setError({
              code:
                reason === "interrupted" ? "device-interrupted" : "empty-audio",
            });
            setStopReason(reason);
          }
          updateStatus("error");
          return;
        }

        const file = createVoiceRecordingFile(samples);
        const nextRecording: VoiceRecording = {
          file,
          objectUrl: URL.createObjectURL(file),
          durationMs: (samples.length / VOICE_WAV_SAMPLE_RATE) * 1_000,
          createdAt: Date.now(),
        };
        revokeRecording();
        recordingRef.current = nextRecording;
        if (mountedRef.current) {
          setRecording(nextRecording);
          setElapsedMs(nextRecording.durationMs);
          setStopReason(reason);
          setError(
            reason === "interrupted" ? { code: "device-interrupted" } : null,
          );
          setPanelOpen(true);
        }
        updateStatus("ready");
        void runTranscription(nextRecording);
      };

      finalizingRef.current = finalize().finally(() => {
        finalizingRef.current = null;
      });
      return finalizingRef.current;
    },
    [clearTimer, revokeRecording, runTranscription, updateStatus],
  );

  const startRecording = useCallback(
    async (replaceCurrent = false): Promise<boolean> => {
      if (!supported || statusRef.current === "requesting") {
        return false;
      }
      if (recordingRef.current && !replaceCurrent) {
        return false;
      }
      if (
        statusRef.current === "recording" ||
        statusRef.current === "processing" ||
        statusRef.current === "transcribing"
      ) {
        return false;
      }

      if (replaceCurrent) {
        revokeRecording();
        setTranscript("");
      }
      setError(null);
      setStopReason(null);
      setElapsedMs(0);
      setDurationWarning(false);
      pcmChunksRef.current = [];
      pcmSampleCountRef.current = 0;
      updateStatus("requesting");
      setPanelOpen(true);

      const capture = createCapture({
        onSamples: (samples) => {
          if (statusRef.current !== "recording" || samples.length === 0) {
            return;
          }
          pcmChunksRef.current.push(samples);
          pcmSampleCountRef.current += samples.length;
        },
        onDeviceEnded: () => {
          if (statusRef.current === "recording") {
            void finalizeRecording("interrupted");
          }
        },
      });
      captureRef.current = capture;

      try {
        await capture.start();
        if (!mountedRef.current || captureRef.current !== capture) {
          await capture.stop();
          return false;
        }
        startedAtRef.current = now();
        updateStatus("recording");
        setPanelOpen(true);
        timerRef.current = window.setInterval(() => {
          const nextElapsed = Math.max(0, now() - startedAtRef.current);
          setElapsedMs(Math.min(nextElapsed, limitMs));
          if (nextElapsed >= warningMs) {
            setDurationWarning(true);
          }
          if (nextElapsed >= limitMs) {
            void finalizeRecording("limit");
          }
        }, 200);
        return true;
      } catch (captureError) {
        if (captureRef.current === capture) {
          captureRef.current = null;
        }
        const nextError = captureErrorFrom(captureError);
        if (mountedRef.current) {
          setError(nextError);
          setPanelOpen(true);
        }
        updateStatus(
          nextError.code === "permission-denied"
            ? "permission-denied"
            : "error",
        );
        return false;
      }
    },
    [
      createCapture,
      finalizeRecording,
      limitMs,
      now,
      revokeRecording,
      supported,
      updateStatus,
      warningMs,
    ],
  );

  const stopRecording = useCallback(
    () => finalizeRecording("manual"),
    [finalizeRecording],
  );

  const discardRecording = useCallback(() => {
    if (statusRef.current === "recording") {
      return;
    }
    revokeRecording();
    setTranscript("");
    setError(null);
    setStopReason(null);
    setElapsedMs(0);
    setDurationWarning(false);
    updateStatus(supported ? "idle" : "unsupported");
  }, [revokeRecording, supported, updateStatus]);

  const transcribe = useCallback((): Promise<void> => {
    const currentRecording = recordingRef.current;
    if (!currentRecording) {
      return Promise.resolve();
    }
    return runTranscription(currentRecording);
  }, [runTranscription]);

  useEffect(() => {
    mountedRef.current = true;
    const teardown = () => {
      clearTimer();
      const capture = captureRef.current;
      captureRef.current = null;
      void capture?.stop();
      pcmChunksRef.current = [];
      pcmSampleCountRef.current = 0;
      transcriptionAbortRef.current?.abort();
      transcriptionAbortRef.current = null;
      const current = recordingRef.current;
      if (current) {
        URL.revokeObjectURL(current.objectUrl);
        recordingRef.current = null;
      }
    };
    window.addEventListener("pagehide", teardown);
    return () => {
      mountedRef.current = false;
      window.removeEventListener("pagehide", teardown);
      teardown();
    };
  }, [clearTimer]);

  return {
    status,
    supported,
    recording,
    elapsedMs,
    durationWarning,
    stopReason,
    error,
    transcript,
    setTranscript,
    panelOpen,
    setPanelOpen,
    transcriptionConfigured:
      isVoiceTranscriptionConfigured(transcriptionAdapter),
    startRecording,
    stopRecording,
    discardRecording,
    transcribe,
  };
}
