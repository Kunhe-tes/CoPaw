export interface VoiceTranscriptionAdapter {
  url: string;
  buildRequest: ((wavFile: File) => RequestInit) | null;
  extractText: ((response: Response) => Promise<string>) | null;
}

export class UnconfiguredVoiceTranscriptionError extends Error {
  constructor() {
    super("Voice transcription is not configured.");
    this.name = "UnconfiguredVoiceTranscriptionError";
  }
}

export class InvalidVoiceTranscriptionResponseError extends Error {
  constructor() {
    super("Voice transcription returned an empty or invalid response.");
    this.name = "InvalidVoiceTranscriptionResponseError";
  }
}

// Integration point 1: fill in the browser-accessible transcription endpoint.
const TRANSCRIPTION_API_URL = "";

// Integration point 2: construct the external API request with the WAV file.
// Do not place a long-lived private credential in browser code.
const buildTranscriptionRequest: VoiceTranscriptionAdapter["buildRequest"] =
  null;

// Integration point 3: map the external API response to the transcript text.
const extractTranscriptionText: VoiceTranscriptionAdapter["extractText"] = null;

export const defaultVoiceTranscriptionAdapter: VoiceTranscriptionAdapter = {
  url: TRANSCRIPTION_API_URL,
  buildRequest: buildTranscriptionRequest,
  extractText: extractTranscriptionText,
};

export function isVoiceTranscriptionConfigured(
  adapter = defaultVoiceTranscriptionAdapter,
): boolean {
  return Boolean(
    adapter.url.trim() && adapter.buildRequest && adapter.extractText,
  );
}

export async function transcribeRecording(
  wavFile: File,
  adapter = defaultVoiceTranscriptionAdapter,
  fetchImplementation: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<string> {
  if (!isVoiceTranscriptionConfigured(adapter)) {
    throw new UnconfiguredVoiceTranscriptionError();
  }

  const request = adapter.buildRequest!(wavFile);
  const response = await fetchImplementation(adapter.url, {
    ...request,
    signal: request.signal ?? signal,
  });
  if (!response.ok) {
    throw new Error(`Voice transcription request failed (${response.status}).`);
  }

  const text = (await adapter.extractText!(response)).trim();
  if (!text) {
    throw new InvalidVoiceTranscriptionResponseError();
  }
  return text;
}
