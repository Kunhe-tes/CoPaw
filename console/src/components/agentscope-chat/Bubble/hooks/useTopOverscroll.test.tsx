import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import useTopOverscroll, {
  TOP_PULL_THRESHOLD,
  toVisualPullOffset,
} from "./useTopOverscroll";

function Harness({ onTriggered }: { onTriggered: () => Promise<void> }) {
  const [scrollElement, setScrollElement] = useState<HTMLDivElement | null>(
    null,
  );
  const { state, visualOffset } = useTopOverscroll({
    onTriggered,
    scrollElement,
  });

  return (
    <div
      data-offset={visualOffset}
      data-state={state}
      data-testid="scroll-container"
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

describe("useTopOverscroll", () => {
  afterEach(cleanup);

  it("resists the raw pull distance and arms at the visual threshold", () => {
    expect(toVisualPullOffset(100)).toBe(45);
    expect(toVisualPullOffset(160)).toBe(TOP_PULL_THRESHOLD);
  });

  it("triggers once when an armed drag is released from the visual top", async () => {
    const onTriggered = vi.fn().mockResolvedValue(undefined);
    render(<Harness onTriggered={onTriggered} />);
    const container = screen.getByTestId("scroll-container");

    fireEvent.pointerDown(container, { button: 0, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(container, { clientY: 260, pointerId: 1 });

    expect(container).toHaveAttribute("data-state", "ready");
    expect(Number(container.dataset.offset)).toBe(TOP_PULL_THRESHOLD);

    await act(async () => {
      fireEvent.pointerUp(container, { clientY: 260, pointerId: 1 });
    });

    expect(onTriggered).toHaveBeenCalledTimes(1);
    expect(container).toHaveAttribute("data-state", "idle");
  });

  it("does not trigger before the threshold", async () => {
    const onTriggered = vi.fn().mockResolvedValue(undefined);
    render(<Harness onTriggered={onTriggered} />);
    const container = screen.getByTestId("scroll-container");

    fireEvent.pointerDown(container, { button: 0, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(container, { clientY: 240, pointerId: 1 });

    await act(async () => {
      fireEvent.pointerUp(container, { clientY: 240, pointerId: 1 });
    });

    expect(onTriggered).not.toHaveBeenCalled();
  });
});
