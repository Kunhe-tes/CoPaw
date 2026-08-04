import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  BrowserPcmCapture,
  isBrowserPcmCaptureSupported,
} from "./browserPcmCapture";
import { MockMediaStream } from "./testUtils";

class ConnectableNode {
  connect<T>(target: T): T {
    return target;
  }

  disconnect(): void {}
}

class MockGainNode extends ConnectableNode {
  gain = { value: 1 };
}

class MockAudioWorkletNode extends ConnectableNode {
  static latest: MockAudioWorkletNode | null = null;
  port = {
    onmessage: null as ((event: MessageEvent<Float32Array>) => void) | null,
  };

  constructor() {
    super();
    MockAudioWorkletNode.latest = this;
  }

  emit(samples: Float32Array): void {
    this.port.onmessage?.({ data: samples } as MessageEvent<Float32Array>);
  }
}

class MockAudioContext {
  sampleRate = 48_000;
  state: AudioContextState = "running";
  destination = new ConnectableNode();
  audioWorklet = { addModule: vi.fn(async () => undefined) };
  close = vi.fn(async () => {
    this.state = "closed";
  });
  resume = vi.fn(async () => undefined);
  createMediaStreamSource = vi.fn(() => new ConnectableNode());
  createGain = vi.fn(() => new MockGainNode());
}

describe("BrowserPcmCapture", () => {
  let stream: MockMediaStream;
  let originalMediaDevices: MediaDevices | undefined;

  beforeEach(() => {
    stream = new MockMediaStream();
    originalMediaDevices = navigator.mediaDevices;
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn(async () => stream as unknown as MediaStream),
      },
    });
    vi.stubGlobal("AudioContext", MockAudioContext);
    vi.stubGlobal("AudioWorkletNode", MockAudioWorkletNode);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: originalMediaDevices,
    });
    MockAudioWorkletNode.latest = null;
  });

  it("captures worklet PCM, downmixes to 16 kHz, and reports device interruption", async () => {
    const onSamples = vi.fn();
    const onDeviceEnded = vi.fn();
    const capture = new BrowserPcmCapture({ onSamples, onDeviceEnded });

    expect(isBrowserPcmCaptureSupported()).toBe(true);
    await capture.start();
    MockAudioWorkletNode.latest?.emit(
      Float32Array.from({ length: 480 }, (_, index) => index / 480),
    );

    expect(onSamples).toHaveBeenCalledOnce();
    expect(onSamples.mock.calls[0][0]).toHaveLength(160);
    stream.track.interrupt();
    expect(onDeviceEnded).toHaveBeenCalledOnce();

    await capture.stop();
    await capture.stop();
    expect(stream.track.stop).toHaveBeenCalledOnce();
    expect(onDeviceEnded).toHaveBeenCalledOnce();
  });

  it("reports unsupported browsers without requesting media", () => {
    vi.stubGlobal("AudioWorkletNode", undefined);

    expect(isBrowserPcmCaptureSupported()).toBe(false);
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
  });
});
