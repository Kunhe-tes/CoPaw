import { describe, expect, it, vi } from "vitest";

import {
  InvalidVoiceTranscriptionResponseError,
  transcribeRecording,
  UnconfiguredVoiceTranscriptionError,
  type VoiceTranscriptionAdapter,
} from "./transcription";

const wavFile = new File(["wav"], "recording.wav", { type: "audio/wav" });

function configuredAdapter(): VoiceTranscriptionAdapter {
  return {
    url: "https://speech.example.test/transcribe",
    buildRequest: (file) => {
      const body = new FormData();
      body.append("voice", file);
      return { method: "POST", body };
    },
    extractText: async (response) => {
      const payload = (await response.json()) as { result?: string };
      return payload.result ?? "";
    },
  };
}

describe("browser-direct voice transcription adapter", () => {
  it("does not issue a request while integration points are unconfigured", async () => {
    const fetchMock = vi.fn<typeof fetch>();

    await expect(
      transcribeRecording(
        wavFile,
        { url: "", buildRequest: null, extractText: null },
        fetchMock,
      ),
    ).rejects.toBeInstanceOf(UnconfiguredVoiceTranscriptionError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("builds an injected WAV request and extracts transcript text", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ result: "  转写结果  " }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(
      transcribeRecording(wavFile, configuredAdapter(), fetchMock),
    ).resolves.toBe("转写结果");
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://speech.example.test/transcribe");
    expect(init?.method).toBe("POST");
    expect((init?.body as FormData).get("voice")).toBe(wavFile);
  });

  it("rejects empty mapped text and propagates HTTP/network failures", async () => {
    const emptyFetch = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(JSON.stringify({}), { status: 200 }));
    await expect(
      transcribeRecording(wavFile, configuredAdapter(), emptyFetch),
    ).rejects.toBeInstanceOf(InvalidVoiceTranscriptionResponseError);

    const httpFetch = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response("no", { status: 503 }));
    await expect(
      transcribeRecording(wavFile, configuredAdapter(), httpFetch),
    ).rejects.toThrow("(503)");

    const networkFetch = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(
      transcribeRecording(wavFile, configuredAdapter(), networkFetch),
    ).rejects.toThrow("Failed to fetch");
  });
});
