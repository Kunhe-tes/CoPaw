import { useCallback, useEffect, useRef, useState } from "react";

export const TOP_PULL_THRESHOLD = 72;
export const TOP_PULL_MAX_OFFSET = 120;
export const TOP_PULL_RESISTANCE = 0.45;

export type TopOverscrollState = "idle" | "pulling" | "ready" | "loading";

export const toVisualPullOffset = (rawPull: number) =>
  Math.min(TOP_PULL_MAX_OFFSET, Math.max(0, rawPull) * TOP_PULL_RESISTANCE);

interface UseTopOverscrollOptions {
  scrollElement: HTMLElement | null;
  onTriggered: () => Promise<void>;
  disabled?: boolean;
}

function isAtVisualTop(element: HTMLElement): boolean {
  const visualTop = Math.min(
    0,
    element.clientHeight - element.scrollHeight,
  );
  return element.scrollTop <= visualTop + 2;
}

export default function useTopOverscroll({
  scrollElement,
  onTriggered,
  disabled = false,
}: UseTopOverscrollOptions) {
  const [state, setState] = useState<TopOverscrollState>("idle");
  const [visualOffset, setVisualOffset] = useState(0);
  const onTriggeredRef = useRef(onTriggered);
  const activePointerRef = useRef<{ id: number; startY: number } | null>(null);
  const loadingRef = useRef(false);

  useEffect(() => {
    onTriggeredRef.current = onTriggered;
  }, [onTriggered]);

  const reset = useCallback(() => {
    activePointerRef.current = null;
    setVisualOffset(0);
    if (!loadingRef.current) setState("idle");
  }, []);

  useEffect(() => {
    if (!scrollElement || disabled) {
      reset();
      return;
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (
        event.button !== 0 ||
        loadingRef.current ||
        !isAtVisualTop(scrollElement)
      ) {
        return;
      }
      activePointerRef.current = {
        id: event.pointerId,
        startY: event.clientY,
      };
      scrollElement.setPointerCapture?.(event.pointerId);
    };

    const handlePointerMove = (event: PointerEvent) => {
      const activePointer = activePointerRef.current;
      if (!activePointer || activePointer.id !== event.pointerId) return;

      const offset = toVisualPullOffset(event.clientY - activePointer.startY);
      if (offset > 0 && event.cancelable) event.preventDefault();
      setVisualOffset(offset);
      setState(offset >= TOP_PULL_THRESHOLD ? "ready" : "pulling");
    };

    const release = async (event: PointerEvent) => {
      const activePointer = activePointerRef.current;
      if (!activePointer || activePointer.id !== event.pointerId) return;

      const offset = toVisualPullOffset(event.clientY - activePointer.startY);
      activePointerRef.current = null;
      scrollElement.releasePointerCapture?.(event.pointerId);
      setVisualOffset(0);

      if (offset < TOP_PULL_THRESHOLD || loadingRef.current) {
        setState("idle");
        return;
      }

      loadingRef.current = true;
      setState("loading");
      try {
        await onTriggeredRef.current();
      } finally {
        loadingRef.current = false;
        setState("idle");
      }
    };

    scrollElement.addEventListener("pointerdown", handlePointerDown);
    scrollElement.addEventListener("pointermove", handlePointerMove, {
      passive: false,
    });
    scrollElement.addEventListener("pointerup", release);
    scrollElement.addEventListener("pointercancel", reset);
    scrollElement.addEventListener("lostpointercapture", reset);
    return () => {
      scrollElement.removeEventListener("pointerdown", handlePointerDown);
      scrollElement.removeEventListener("pointermove", handlePointerMove);
      scrollElement.removeEventListener("pointerup", release);
      scrollElement.removeEventListener("pointercancel", reset);
      scrollElement.removeEventListener("lostpointercapture", reset);
    };
  }, [disabled, reset, scrollElement]);

  return { state, visualOffset };
}
