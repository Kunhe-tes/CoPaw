import { describe, expect, it } from "vitest";

import {
  mergePcmChunks,
  StreamingLinearResampler,
  VOICE_WAV_SAMPLE_RATE,
} from "./audio";

describe("GlobalVoiceRecorder audio utilities", () => {
  it("downsamples streaming mono PCM to 16 kHz without resetting chunk phase", () => {
    const source = Float32Array.from({ length: 480 }, (_, index) =>
      Math.sin(index / 10),
    );
    const oneShot = new StreamingLinearResampler(48_000).process(source);
    const streaming = new StreamingLinearResampler(48_000);
    const split = mergePcmChunks([
      streaming.process(source.slice(0, 127)),
      streaming.process(source.slice(127, 301)),
      streaming.process(source.slice(301)),
    ]);

    expect(oneShot).toHaveLength(160);
    expect(split).toHaveLength(160);
    expect(Array.from(split)).toEqual(Array.from(oneShot));
  });

  it("copies already-16-kHz chunks and merges them in order", () => {
    const resampler = new StreamingLinearResampler(VOICE_WAV_SAMPLE_RATE);
    const first = Float32Array.from([0.1, 0.2]);
    const second = Float32Array.from([-0.3]);
    const output = mergePcmChunks([
      resampler.process(first),
      resampler.process(second),
    ]);

    expect(output).not.toBe(first);
    expect(Array.from(output)).toEqual([
      Math.fround(0.1),
      Math.fround(0.2),
      Math.fround(-0.3),
    ]);
  });

  it("rejects invalid sample rates", () => {
    expect(() => new StreamingLinearResampler(0)).toThrow(
      "Audio sample rates must be positive.",
    );
  });
});
