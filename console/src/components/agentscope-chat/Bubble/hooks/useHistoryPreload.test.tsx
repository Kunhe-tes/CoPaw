import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import useHistoryPreload from "./useHistoryPreload";

function Harness({ onNearStart }: { onNearStart: () => Promise<void> }) {
  const [scrollElement, setScrollElement] = useState<HTMLDivElement | null>(
    null,
  );
  useHistoryPreload({ onNearStart, scrollElement, resetKey: "chat-1" });

  return (
    <div
      data-testid="scroll-container"
      ref={(element) => {
        if (!element) return;
        Object.defineProperties(element, {
          clientHeight: { configurable: true, value: 400 },
          scrollHeight: { configurable: true, value: 1000 },
          scrollTop: { configurable: true, value: -500, writable: true },
        });
        setScrollElement(element);
      }}
    />
  );
}

function TopHarness({ onNearStart }: { onNearStart: () => Promise<void> }) {
  const [scrollElement, setScrollElement] = useState<HTMLDivElement | null>(
    null,
  );
  useHistoryPreload({ onNearStart, scrollElement, resetKey: "chat-1" });

  return (
    <div
      data-testid="top-scroll-container"
      ref={(element) => {
        if (!element) return;
        Object.defineProperties(element, {
          clientHeight: { configurable: true, value: 400 },
          scrollHeight: { configurable: true, value: 1000 },
          scrollTop: { configurable: true, value: -600, writable: true },
        });
        setScrollElement(element);
      }}
    />
  );
}

describe("useHistoryPreload", () => {
  afterEach(cleanup);

  it("does not load history merely because the list mounts at the visual top", () => {
    const onNearStart = vi.fn().mockResolvedValue(undefined);
    render(<TopHarness onNearStart={onNearStart} />);

    expect(onNearStart).not.toHaveBeenCalled();
  });

  it("requests older history when normal upward scrolling enters the preload range", async () => {
    const onNearStart = vi.fn().mockResolvedValue(undefined);
    render(<Harness onNearStart={onNearStart} />);
    const container = screen.getByTestId("scroll-container");

    container.scrollTop = -380;
    await act(async () => {
      fireEvent.scroll(container);
    });

    expect(onNearStart).toHaveBeenCalledTimes(1);
  });

  it("waits for the user to leave the preload range before requesting another page", async () => {
    const onNearStart = vi.fn().mockResolvedValue(undefined);
    render(<Harness onNearStart={onNearStart} />);
    const container = screen.getByTestId("scroll-container");

    container.scrollTop = -380;
    await act(async () => {
      fireEvent.scroll(container);
      fireEvent.scroll(container);
    });
    expect(onNearStart).toHaveBeenCalledTimes(1);

    container.scrollTop = -200;
    fireEvent.scroll(container);
    container.scrollTop = -380;
    await act(async () => {
      fireEvent.scroll(container);
    });
    expect(onNearStart).toHaveBeenCalledTimes(2);
  });
});
