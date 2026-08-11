import {
  VOICE_WAV_BITS_PER_SAMPLE,
  VOICE_WAV_CHANNELS,
  VOICE_WAV_SAMPLE_RATE,
} from "./audio";

const WAV_HEADER_BYTES = 44;

function writeAscii(view: DataView, offset: number, value: string): void {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}

export function encodePcm16Wav(samples: Float32Array): Blob {
  const bytesPerSample = VOICE_WAV_BITS_PER_SAMPLE / 8;
  const dataBytes = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(WAV_HEADER_BYTES + dataBytes);
  const view = new DataView(buffer);

  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, VOICE_WAV_CHANNELS, true);
  view.setUint32(24, VOICE_WAV_SAMPLE_RATE, true);
  view.setUint32(
    28,
    VOICE_WAV_SAMPLE_RATE * VOICE_WAV_CHANNELS * bytesPerSample,
    true,
  );
  view.setUint16(32, VOICE_WAV_CHANNELS * bytesPerSample, true);
  view.setUint16(34, VOICE_WAV_BITS_PER_SAMPLE, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, dataBytes, true);

  samples.forEach((sample, index) => {
    const clamped = Math.max(-1, Math.min(1, sample));
    const integer =
      clamped < 0 ? Math.round(clamped * 0x8000) : Math.round(clamped * 0x7fff);
    view.setInt16(WAV_HEADER_BYTES + index * bytesPerSample, integer, true);
  });

  return new Blob([buffer], { type: "audio/wav" });
}

export function createVoiceRecordingFile(
  samples: Float32Array,
  createdAt = new Date(),
): File {
  const timestamp = createdAt
    .toISOString()
    .replace(/\.\d{3}Z$/, "Z")
    .replace(/:/g, "-");
  const filename = `copaw-recording-${timestamp}.wav`;
  const wav = encodePcm16Wav(samples);
  return new File([wav], filename, {
    type: "audio/wav",
    lastModified: createdAt.getTime(),
  });
}
