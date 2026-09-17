import { useState, useEffect, useCallback, useRef } from "react";
import api from "../../../api";
import type {
  SkillScannerConfig,
  BlockedSkillRecord,
  SkillScannerWhitelistEntry,
} from "../../../api/modules/security";

export function useSkillScanner() {
  const [config, setConfig] = useState<SkillScannerConfig | null>(null);
  const [blockedHistory, setBlockedHistory] = useState<BlockedSkillRecord[]>(
    [],
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyMutating, setHistoryMutating] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyPageSize, setHistoryPageSize] = useState(20);
  const [historyTotal, setHistoryTotal] = useState(0);
  const historyRequestIdRef = useRef(0);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const cfg = await api.getSkillScanner();
      setConfig(cfg);
      return true;
    } catch (err) {
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to load skill scanner config";
      console.error("Failed to load skill scanner config:", err);
      setError(msg);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchBlockedHistory = useCallback(async () => {
    const requestId = ++historyRequestIdRef.current;
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const history = await api.getBlockedHistory(historyPage, historyPageSize);
      if (requestId !== historyRequestIdRef.current) return false;
      const lastPage = Math.max(1, Math.ceil(history.total / historyPageSize));
      setHistoryTotal(history.total);
      if (historyPage > lastPage) {
        setBlockedHistory([]);
        setHistoryPage(lastPage);
        return true;
      }
      setBlockedHistory(history.items);
      return true;
    } catch (err) {
      if (requestId !== historyRequestIdRef.current) return false;
      const msg =
        err instanceof Error ? err.message : "Failed to load scan history";
      console.error("Failed to load skill scan history:", err);
      setHistoryError(msg);
      setBlockedHistory([]);
      setHistoryTotal(0);
      return false;
    } finally {
      if (requestId === historyRequestIdRef.current) {
        setHistoryLoading(false);
      }
    }
  }, [historyPage, historyPageSize]);

  const fetchAll = useCallback(
    async () => Promise.all([fetchConfig(), fetchBlockedHistory()]),
    [fetchConfig, fetchBlockedHistory],
  );

  useEffect(() => {
    void fetchConfig();
  }, [fetchConfig]);

  useEffect(() => {
    void fetchBlockedHistory();
  }, [fetchBlockedHistory]);

  const updateConfig = useCallback(
    async (updates: Partial<SkillScannerConfig>) => {
      if (!config) return;
      const newConfig = { ...config, ...updates };
      try {
        const saved = await api.updateSkillScanner(newConfig);
        setConfig(saved);
        return true;
      } catch (err) {
        console.error("Failed to update skill scanner config:", err);
        return false;
      }
    },
    [config],
  );

  const addToWhitelist = useCallback(
    async (skillName: string, contentHash: string = "") => {
      try {
        await api.addToWhitelist(skillName, contentHash);
        await fetchConfig();
        return true;
      } catch (err) {
        console.error("Failed to add to whitelist:", err);
        return false;
      }
    },
    [fetchConfig],
  );

  const removeFromWhitelist = useCallback(
    async (skillName: string) => {
      try {
        await api.removeFromWhitelist(skillName);
        await fetchConfig();
        return true;
      } catch (err) {
        console.error("Failed to remove from whitelist:", err);
        return false;
      }
    },
    [fetchConfig],
  );

  const removeBlockedEntry = useCallback(
    async (recordId: string) => {
      setHistoryMutating(true);
      historyRequestIdRef.current += 1;
      setHistoryLoading(false);
      try {
        await api.removeBlockedEntry(recordId);
        if (blockedHistory.length === 1 && historyPage > 1) {
          setBlockedHistory([]);
          setHistoryPage((current) => current - 1);
        } else {
          await fetchBlockedHistory();
        }
        return true;
      } catch (err) {
        console.error("Failed to remove blocked entry:", err);
        return false;
      } finally {
        setHistoryMutating(false);
      }
    },
    [blockedHistory.length, fetchBlockedHistory, historyPage],
  );

  const clearBlockedHistory = useCallback(async () => {
    setHistoryMutating(true);
    historyRequestIdRef.current += 1;
    setHistoryLoading(false);
    try {
      await api.clearBlockedHistory();
      setBlockedHistory([]);
      setHistoryTotal(0);
      setHistoryError(null);
      setHistoryPage(1);
      return true;
    } catch (err) {
      console.error("Failed to clear blocked history:", err);
      return false;
    } finally {
      setHistoryMutating(false);
    }
  }, []);

  const setHistoryPagination = useCallback(
    (page: number, pageSize: number) => {
      if (pageSize !== historyPageSize) {
        setHistoryPageSize(pageSize);
        setHistoryPage(1);
        return;
      }
      setHistoryPage(page);
    },
    [historyPageSize],
  );

  const whitelist: SkillScannerWhitelistEntry[] = config?.whitelist ?? [];

  return {
    config,
    blockedHistory,
    whitelist,
    loading,
    error,
    historyLoading,
    historyMutating,
    historyError,
    historyPage,
    historyPageSize,
    historyTotal,
    fetchAll,
    fetchBlockedHistory,
    setHistoryPagination,
    updateConfig,
    addToWhitelist,
    removeFromWhitelist,
    removeBlockedEntry,
    clearBlockedHistory,
  };
}
