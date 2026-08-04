import { useEffect, useRef } from "react";

export const HISTORY_PRELOAD_DISTANCE = 240;

interface UseHistoryPreloadOptions {
  scrollElement: HTMLElement | null;
  onNearStart: () => Promise<void>;
  disabled?: boolean;
  resetKey?: string | null;
}

function getVisualStart(element: HTMLElement): number {
  return Math.min(0, element.clientHeight - element.scrollHeight);
}

function isNearVisualStart(element: HTMLElement): boolean {
  return element.scrollTop - getVisualStart(element) <= HISTORY_PRELOAD_DISTANCE;
}

/**
 * Requests one older-history page after the user enters the top preload zone.
 * A new request requires leaving and re-entering that zone, preventing an
 * exhausted or short timeline from repeatedly fetching every page at once.
 */
export default function useHistoryPreload({
  scrollElement,
  onNearStart,
  disabled = false,
  resetKey,
}: UseHistoryPreloadOptions): void {
  const onNearStartRef = useRef(onNearStart);
  const requestingRef = useRef(false);
  const hasObservedScrollRef = useRef(false);
  const wasNearStartRef = useRef(false);

  useEffect(() => {
    onNearStartRef.current = onNearStart;
  }, [onNearStart]);

  useEffect(() => {
    requestingRef.current = false;
    hasObservedScrollRef.current = false;
    wasNearStartRef.current = false;
  }, [resetKey]);

  useEffect(() => {
    if (!scrollElement) return;

    const evaluate = () => {
      const nearStart = isNearVisualStart(scrollElement);
      if (!nearStart) {
        wasNearStartRef.current = false;
        return;
      }
      if (disabled || wasNearStartRef.current || requestingRef.current) {
        return;
      }

      wasNearStartRef.current = true;
      requestingRef.current = true;
      void onNearStartRef.current().finally(() => {
        requestingRef.current = false;
      });
    };

    const handleScroll = () => {
      hasObservedScrollRef.current = true;
      evaluate();
    };
    const handleResize = () => {
      if (hasObservedScrollRef.current) evaluate();
    };

    scrollElement.addEventListener("scroll", handleScroll, { passive: true });
    const resizeObserver =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(handleResize);
    resizeObserver?.observe(scrollElement);

    return () => {
      scrollElement.removeEventListener("scroll", handleScroll);
      resizeObserver?.disconnect();
    };
  }, [disabled, scrollElement]);
}
