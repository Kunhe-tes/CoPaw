export const VOICE_WAV_SAMPLE_RATE = 16_000;
export const VOICE_WAV_CHANNELS = 1;
export const VOICE_WAV_BITS_PER_SAMPLE = 16;

export class StreamingLinearResampler {
  private readonly ratio: number;
  private inputOffset = 0;
  private nextOutputPosition = 0;
  private previousSample: number | undefined;

  constructor(
    private readonly inputSampleRate: number,
    private readonly outputSampleRate = VOICE_WAV_SAMPLE_RATE,
  ) {
    if (inputSampleRate <= 0 || outputSampleRate <= 0) {
      throw new Error("Audio sample rates must be positive.");
    }
    this.ratio = inputSampleRate / outputSampleRate;
  }

  process(input: Float32Array): Float32Array {
    if (input.length === 0) {
      return new Float32Array();
    }

    if (this.inputSampleRate === this.outputSampleRate) {
      this.inputOffset += input.length;
      this.previousSample = input[input.length - 1];
      return input.slice();
    }

    const hasPrevious = this.previousSample !== undefined;
    const combinedStart = this.inputOffset - (hasPrevious ? 1 : 0);
    const combinedLength = input.length + (hasPrevious ? 1 : 0);
    const combined = new Float32Array(combinedLength);
    if (hasPrevious) {
      combined[0] = this.previousSample as number;
      combined.set(input, 1);
    } else {
      combined.set(input);
    }

    const combinedEnd = combinedStart + combined.length - 1;
    const output: number[] = [];
    while (this.nextOutputPosition <= combinedEnd) {
      const lowerIndex = Math.floor(this.nextOutputPosition);
      const upperIndex = Math.ceil(this.nextOutputPosition);
      if (upperIndex > combinedEnd) {
        break;
      }

      const lower = combined[lowerIndex - combinedStart];
      const upper = combined[upperIndex - combinedStart];
      const fraction = this.nextOutputPosition - lowerIndex;
      output.push(lower + (upper - lower) * fraction);
      this.nextOutputPosition += this.ratio;
    }

    this.inputOffset += input.length;
    this.previousSample = input[input.length - 1];
    return Float32Array.from(output);
  }
}

export function mergePcmChunks(chunks: readonly Float32Array[]): Float32Array {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const samples = new Float32Array(length);
  let offset = 0;
  chunks.forEach((chunk) => {
    samples.set(chunk, offset);
    offset += chunk.length;
  });
  return samples;
}
