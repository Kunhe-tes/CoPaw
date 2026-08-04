export type VoiceRecorderStatus =
  | "idle"
  | "requesting"
  | "recording"
  | "processing"
  | "ready"
  | "transcribing"
  | "permission-denied"
  | "unsupported"
  | "error";

export interface VoiceRecording {
  file: File;
  objectUrl: string;
  durationMs: number;
  createdAt: number;
}

export interface VoiceRecorderError {
  code:
    | "permission-denied"
    | "device-unavailable"
    | "device-interrupted"
    | "empty-audio"
    | "capture-failed"
    | "transcription-failed";
  detail?: string;
}
