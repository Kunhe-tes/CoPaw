import React, {
  createContext,
  useCallback,
  useContext,
  useLayoutEffect,
  useMemo,
  useRef,
} from "react";

interface AutoPreviewCandidate {
  open: () => void;
}

interface AutoPreviewHtmlContextValue {
  enabled: boolean;
  register: (candidate: AutoPreviewCandidate) => () => void;
}

const noopUnregister = () => undefined;

const AutoPreviewHtmlContext = createContext<AutoPreviewHtmlContextValue>({
  enabled: false,
  register: () => noopUnregister,
});

interface AutoPreviewHtmlProviderProps {
  children: React.ReactNode;
  triggerKey: number;
  onConsumed: () => void;
}

export function AutoPreviewHtmlProvider(props: AutoPreviewHtmlProviderProps) {
  const { children, triggerKey, onConsumed } = props;
  const candidatesRef = useRef<AutoPreviewCandidate[]>([]);
  const selectTimerRef = useRef<number | null>(null);
  const expireTimerRef = useRef<number | null>(null);
  const consumedRef = useRef(false);
  const enabled = triggerKey > 0;

  const clearSelectTimer = useCallback(() => {
    if (selectTimerRef.current !== null) {
      window.clearTimeout(selectTimerRef.current);
      selectTimerRef.current = null;
    }
  }, []);

  useLayoutEffect(() => {
    candidatesRef.current = [];
    consumedRef.current = false;
    clearSelectTimer();

    if (expireTimerRef.current !== null) {
      window.clearTimeout(expireTimerRef.current);
      expireTimerRef.current = null;
    }

    if (!enabled) return;

    expireTimerRef.current = window.setTimeout(() => {
      consumedRef.current = true;
      candidatesRef.current = [];
      onConsumed();
    }, 5000);

    return () => {
      clearSelectTimer();
      if (expireTimerRef.current !== null) {
        window.clearTimeout(expireTimerRef.current);
        expireTimerRef.current = null;
      }
    };
  }, [clearSelectTimer, enabled, onConsumed, triggerKey]);

  const register = useCallback(
    (candidate: AutoPreviewCandidate) => {
      if (!enabled || consumedRef.current) return noopUnregister;

      candidatesRef.current.push(candidate);
      clearSelectTimer();
      selectTimerRef.current = window.setTimeout(() => {
        if (consumedRef.current) return;

        const latest = candidatesRef.current[candidatesRef.current.length - 1];
        consumedRef.current = true;
        candidatesRef.current = [];
        latest?.open();
        onConsumed();
      }, 120);

      return () => {
        candidatesRef.current = candidatesRef.current.filter(
          (item) => item !== candidate,
        );
      };
    },
    [clearSelectTimer, enabled, onConsumed],
  );

  const value = useMemo(
    () => ({
      enabled,
      register,
    }),
    [enabled, register],
  );

  return (
    <AutoPreviewHtmlContext.Provider value={value}>
      {children}
    </AutoPreviewHtmlContext.Provider>
  );
}

export function useAutoPreviewHtml() {
  return useContext(AutoPreviewHtmlContext);
}
