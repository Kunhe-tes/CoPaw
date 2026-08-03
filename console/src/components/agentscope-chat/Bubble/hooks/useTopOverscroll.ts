import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

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
  const visualTop = Math.min(0, element.clientHeight - element.scrollHeight);
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
  const previousVisualOffsetRef = useRef(0);

  useEffect(() => {
    onTriggeredRef.current = onTriggered;
  }, [onTriggered]);

  useLayoutEffect(() => {
    const previousVisualOffset = previousVisualOffsetRef.current;
    const offsetDelta = visualOffset - previousVisualOffset;
    if (scrollElement && offsetDelta !== 0 && scrollElement.scrollTop < 0) {
      scrollElement.scrollTop -= offsetDelta;
    }
    previousVisualOffsetRef.current = visualOffset;
  }, [scrollElement, visualOffset]);

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

    let wheelPull = 0;
    let wheelResetTimer: ReturnType<typeof setTimeout> | undefined;

    const clearWheelResetTimer = () => {
      if (wheelResetTimer !== undefined) {
        clearTimeout(wheelResetTimer);
        wheelResetTimer = undefined;
      }
    };

    const triggerLoading = async () => {
      if (loadingRef.current) return;
      loadingRef.current = true;
      setVisualOffset(TOP_PULL_THRESHOLD);
      setState("loading");
      try {
        await onTriggeredRef.current();
      } finally {
        loadingRef.current = false;
        setVisualOffset(0);
        setState("idle");
      }
    };

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

    const release = (event: PointerEvent) => {
      const activePointer = activePointerRef.current;
      if (!activePointer || activePointer.id !== event.pointerId) return;

      const offset = toVisualPullOffset(event.clientY - activePointer.startY);
      activePointerRef.current = null;
      scrollElement.releasePointerCapture?.(event.pointerId);
      if (offset < TOP_PULL_THRESHOLD || loadingRef.current) {
        setVisualOffset(0);
        setState("idle");
        return;
      }

      void triggerLoading();
    };

    const handleWheel = (event: WheelEvent) => {
      if (loadingRef.current || event.deltaY >= 0) return;
      if (!isAtVisualTop(scrollElement) && wheelPull === 0) return;

      if (event.cancelable) event.preventDefault();
      const delta =
        event.deltaMode === WheelEvent.DOM_DELTA_LINE
          ? -event.deltaY * 16
          : -event.deltaY;
      wheelPull += delta;
      const offset = toVisualPullOffset(wheelPull);
      setVisualOffset(offset);

      if (offset >= TOP_PULL_THRESHOLD) {
        clearWheelResetTimer();
        wheelPull = 0;
        void triggerLoading();
        return;
      }

      setState("pulling");
      clearWheelResetTimer();
      wheelResetTimer = setTimeout(() => {
        wheelPull = 0;
        setVisualOffset(0);
        setState("idle");
      }, 160);
    };

    scrollElement.addEventListener("pointerdown", handlePointerDown);
    scrollElement.addEventListener("pointermove", handlePointerMove, {
      passive: false,
    });
    scrollElement.addEventListener("pointerup", release);
    scrollElement.addEventListener("wheel", handleWheel, { passive: false });
    scrollElement.addEventListener("pointercancel", reset);
    scrollElement.addEventListener("lostpointercapture", reset);
    return () => {
      clearWheelResetTimer();
      scrollElement.removeEventListener("pointerdown", handlePointerDown);
      scrollElement.removeEventListener("pointermove", handlePointerMove);
      scrollElement.removeEventListener("pointerup", release);
      scrollElement.removeEventListener("wheel", handleWheel);
      scrollElement.removeEventListener("pointercancel", reset);
      scrollElement.removeEventListener("lostpointercapture", reset);
    };
  }, [disabled, reset, scrollElement]);

  return { state, visualOffset };
}
