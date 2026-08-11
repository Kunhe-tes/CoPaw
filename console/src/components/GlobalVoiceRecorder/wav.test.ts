import { describe, expect, it } from "vitest";

import { createVoiceRecordingFile, encodePcm16Wav } from "./wav";

async function blobDataView(blob: Blob): Promise<DataView> {
  return new DataView(await blob.arrayBuffer());
}

function ascii(view: DataView, offset: number, length: number): string {
  return String.fromCharCode(
    ...Array.from({ length }, (_, index) => view.getUint8(offset + index)),
  );
}

describe("GlobalVoiceRecorder WAV encoding", () => {
  it("writes a mono 16-kHz 16-bit little-endian RIFF/WAVE header", async () => {
    const blob = encodePcm16Wav(Float32Array.from([-1, 0, 1]));
    const view = await blobDataView(blob);

    expect(blob.type).toBe("audio/wav");
    expect(blob.size).toBe(44 + 3 * 2);
    expect(ascii(view, 0, 4)).toBe("RIFF");
    expect(view.getUint32(4, true)).toBe(42);
    expect(ascii(view, 8, 4)).toBe("WAVE");
    expect(ascii(view, 12, 4)).toBe("fmt ");
    expect(view.getUint16(20, true)).toBe(1);
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(24, true)).toBe(16_000);
    expect(view.getUint32(28, true)).toBe(32_000);
    expect(view.getUint16(34, true)).toBe(16);
    expect(ascii(view, 36, 4)).toBe("data");
    expect(view.getUint32(40, true)).toBe(6);
    expect(view.getInt16(44, true)).toBe(-32_768);
    expect(view.getInt16(46, true)).toBe(0);
    expect(view.getInt16(48, true)).toBe(32_767);
  });

  it("clamps out-of-range samples and creates a named WAV File", async () => {
    const file = createVoiceRecordingFile(
      Float32Array.from([-2, 2]),
      new Date("2026-07-30T12:34:56.000Z"),
    );
    const view = await blobDataView(file);

    expect(file.name).toBe("copaw-recording-2026-07-30T12-34-56Z.wav");
    expect(file.type).toBe("audio/wav");
    expect(view.getInt16(44, true)).toBe(-32_768);
    expect(view.getInt16(46, true)).toBe(32_767);
  });
});
