import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useSkillScanner } from "./useSkillScanner";

const mocks = vi.hoisted(() => ({
  getSkillScanner: vi.fn(),
  getBlockedHistory: vi.fn(),
  removeBlockedEntry: vi.fn(),
  clearBlockedHistory: vi.fn(),
  updateSkillScanner: vi.fn(),
  addToWhitelist: vi.fn(),
  removeFromWhitelist: vi.fn(),
}));

vi.mock("../../../api", () => ({
  default: mocks,
}));

const config = {
  mode: "block" as const,
  timeout: 30,
  whitelist: [],
};

const record = {
  id: "record-1",
  skill_name: "unsafe-skill",
  blocked_at: "2026-08-03T08:00:00+00:00",
  max_severity: "HIGH",
  findings: [],
  content_hash: "",
  action: "blocked" as const,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolver) => {
    resolve = resolver;
  });
  return { promise, resolve };
}

function historyPage(
  page: number,
  pageSize: number,
  items = [record],
  total = items.length,
) {
  return { items, total, page, page_size: pageSize };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getSkillScanner.mockResolvedValue(config);
  mocks.getBlockedHistory.mockImplementation(
    async (page: number, pageSize: number) => ({
      items:
        page === 2
          ? [record]
          : Array.from({ length: 10 }, (_, index) => ({
              ...record,
              id: `record-${index + 2}`,
            })),
      total: 11,
      page,
      page_size: pageSize,
    }),
  );
  mocks.removeBlockedEntry.mockResolvedValue({ removed: true });
  mocks.clearBlockedHistory.mockResolvedValue({ cleared: true });
});

describe("useSkillScanner history pagination", () => {
  it("loads only the active backend page and changes page size", async () => {
    const { result } = renderHook(() => useSkillScanner());

    await waitFor(() => {
      expect(result.current.blockedHistory).toHaveLength(10);
    });
    expect(mocks.getBlockedHistory).toHaveBeenCalledWith(1, 20);

    act(() => result.current.setHistoryPagination(1, 10));

    await waitFor(() => {
      expect(mocks.getBlockedHistory).toHaveBeenLastCalledWith(1, 10);
    });
    expect(result.current.historyPage).toBe(1);
    act(() => result.current.setHistoryPagination(2, 10));
    await waitFor(() => {
      expect(mocks.getBlockedHistory).toHaveBeenLastCalledWith(2, 10);
    });
    expect(result.current.historyPage).toBe(2);
    expect(result.current.historyPageSize).toBe(10);
    expect(result.current.historyTotal).toBe(11);
  });

  it("moves to the preceding page after deleting its final item", async () => {
    const { result } = renderHook(() => useSkillScanner());
    await waitFor(() => expect(result.current.config).toEqual(config));

    act(() => result.current.setHistoryPagination(1, 10));
    await waitFor(() => expect(result.current.historyPageSize).toBe(10));
    act(() => result.current.setHistoryPagination(2, 10));
    await waitFor(() => expect(result.current.historyPage).toBe(2));
    await waitFor(() => expect(result.current.blockedHistory).toHaveLength(1));

    await act(async () => {
      await result.current.removeBlockedEntry("record-1");
    });

    expect(mocks.removeBlockedEntry).toHaveBeenCalledWith("record-1");
    await waitFor(() => {
      expect(result.current.historyPage).toBe(1);
      expect(mocks.getBlockedHistory).toHaveBeenLastCalledWith(1, 10);
    });
  });

  it("keeps scanner controls available when history loading fails", async () => {
    mocks.getBlockedHistory.mockRejectedValueOnce(new Error("database down"));

    const { result } = renderHook(() => useSkillScanner());

    await waitFor(() => expect(result.current.config).toEqual(config));
    await waitFor(() =>
      expect(result.current.historyError).toBe("database down"),
    );
    expect(result.current.loading).toBe(false);
    expect(result.current.blockedHistory).toEqual([]);
  });

  it("ignores a stale response that arrives after the active page", async () => {
    const firstPage = deferred<ReturnType<typeof historyPage>>();
    mocks.getBlockedHistory
      .mockImplementationOnce(() => firstPage.promise)
      .mockResolvedValueOnce(
        historyPage(2, 20, [{ ...record, id: "page-2" }], 40),
      );
    const { result } = renderHook(() => useSkillScanner());

    await waitFor(() => expect(result.current.config).toEqual(config));
    act(() => result.current.setHistoryPagination(2, 20));
    await waitFor(() =>
      expect(result.current.blockedHistory[0]?.id).toBe("page-2"),
    );

    await act(async () => {
      firstPage.resolve(
        historyPage(1, 20, [{ ...record, id: "stale-page-1" }], 40),
      );
      await firstPage.promise;
    });

    expect(result.current.historyPage).toBe(2);
    expect(result.current.blockedHistory[0]?.id).toBe("page-2");
  });

  it("clamps a page invalidated by concurrent deletion", async () => {
    mocks.getBlockedHistory.mockImplementation(
      async (page: number, pageSize: number) => {
        if (page === 3) return historyPage(3, pageSize, [], 11);
        if (page === 2) return historyPage(2, pageSize, [record], 11);
        return historyPage(page, pageSize, [{ ...record, id: "page-1" }], 11);
      },
    );
    const { result } = renderHook(() => useSkillScanner());
    await waitFor(() => expect(result.current.blockedHistory).toHaveLength(1));

    act(() => result.current.setHistoryPagination(1, 10));
    await waitFor(() => expect(result.current.historyPageSize).toBe(10));
    act(() => result.current.setHistoryPagination(3, 10));

    await waitFor(() => {
      expect(result.current.historyPage).toBe(2);
      expect(result.current.blockedHistory[0]?.id).toBe("record-1");
    });
    expect(mocks.getBlockedHistory).toHaveBeenCalledWith(3, 10);
    expect(mocks.getBlockedHistory).toHaveBeenLastCalledWith(2, 10);
  });

  it("exposes a pending state while a history mutation is running", async () => {
    const removal = deferred<{ removed: boolean }>();
    mocks.removeBlockedEntry.mockReturnValueOnce(removal.promise);
    const { result } = renderHook(() => useSkillScanner());
    await waitFor(() => expect(result.current.blockedHistory).not.toEqual([]));

    let operation!: Promise<boolean>;
    act(() => {
      operation = result.current.removeBlockedEntry("record-1");
    });
    await waitFor(() => expect(result.current.historyMutating).toBe(true));

    await act(async () => {
      removal.resolve({ removed: true });
      await operation;
    });
    expect(result.current.historyMutating).toBe(false);
  });
});
