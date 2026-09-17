import { vi } from "vitest";

import type { BrowserPcmCaptureHandlers } from "./browserPcmCapture";

export class MockMediaStreamTrack extends EventTarget {
  kind = "audio";
  stop = vi.fn(() => {
    this.dispatchEvent(new Event("ended"));
  });

  interrupt(): void {
    this.dispatchEvent(new Event("ended"));
  }
}

export class MockMediaStream {
  readonly track = new MockMediaStreamTrack();

  getTracks(): MediaStreamTrack[] {
    return [this.track as unknown as MediaStreamTrack];
  }

  getAudioTracks(): MediaStreamTrack[] {
    return this.getTracks();
  }
}

export class ControlledPcmCapture {
  readonly start = vi.fn(async () => undefined);
  readonly stop = vi.fn(async () => undefined);

  constructor(readonly handlers: BrowserPcmCaptureHandlers) {}

  emit(samples: number[] | Float32Array): void {
    this.handlers.onSamples(Float32Array.from(samples));
  }

  interrupt(): void {
    this.handlers.onDeviceEnded();
  }
}

export function installObjectUrlMocks() {
  const createObjectURL = vi
    .fn<(object: Blob | MediaSource) => string>()
    .mockReturnValue("blob:voice-recording");
  const revokeObjectURL = vi.fn<(url: string) => void>();
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: createObjectURL,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: revokeObjectURL,
  });
  return { createObjectURL, revokeObjectURL };
}

export function installClipboardMock() {
  const writeText = vi
    .fn<(text: string) => Promise<void>>()
    .mockResolvedValue();
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  return { writeText };
}

export function installAudioPlaybackMocks() {
  const play = vi
    .spyOn(HTMLMediaElement.prototype, "play")
    .mockResolvedValue(undefined);
  const pause = vi
    .spyOn(HTMLMediaElement.prototype, "pause")
    .mockImplementation(() => undefined);
  return { play, pause };
}
