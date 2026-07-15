import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ArchiveGovernance from "./ArchiveGovernance";

const mocks = vi.hoisted(() => ({
  dreamLogsApi: {
    archiveReport: vi.fn(),
    listArchiveAdminAudits: vi.fn(),
    listArchiveItems: vi.fn(),
    listProtectedFiles: vi.fn(),
    purgeArchiveItems: vi.fn(),
    purgeExpiredArchiveItems: vi.fn(),
    removeProtectedFile: vi.fn(),
    restoreArchiveItem: vi.fn(),
  },
}));

vi.mock("../../../../api/modules/dreamLogs", () => ({
  dreamLogsApi: mocks.dreamLogsApi,
}));

function archiveItem(page: number) {
  return {
    id: `archive-${page}`,
    original_path: `static/index-${page}.html`,
    archive_path: `governance/archive/archive-${page}`,
    size_bytes: 1024,
    mtime: "2026-07-15T08:00:00Z",
    archived_at: "2026-07-15T09:00:00Z",
    archived_by: "admin",
    archive_reason: "manual",
    target_user_id: "tenant-a",
    target_agent_id: "default",
    expired: false,
  };
}

function archivePageResponse(page: number, pageSize = 10) {
  return {
    items: [archiveItem(page)],
    total: 1774,
    page,
    page_size: pageSize,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

describe("ArchiveGovernance", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.dreamLogsApi.archiveReport.mockResolvedValue({
      summary: {
        archived_files: 1774,
        archived_size_bytes: 1024,
        pending_purge_files: 0,
        protected_files: 0,
        purged_size_bytes: 0,
      },
    });
    mocks.dreamLogsApi.listArchiveItems.mockImplementation(
      async ({ page, page_size }: { page: number; page_size: number }) =>
        archivePageResponse(page, page_size),
    );
    mocks.dreamLogsApi.listProtectedFiles.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
    });
    mocks.dreamLogsApi.listArchiveAdminAudits.mockResolvedValue({
      summary: {},
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("requests archive pages from the server using the reported total", async () => {
    render(<ArchiveGovernance />);

    expect(await screen.findByText("static/index-1.html")).toBeInTheDocument();
    expect(mocks.dreamLogsApi.listArchiveItems).toHaveBeenCalledWith({
      page: 1,
      page_size: 10,
    });

    fireEvent.click(screen.getByTitle("2"));

    await waitFor(() => {
      expect(mocks.dreamLogsApi.listArchiveItems).toHaveBeenLastCalledWith({
        page: 2,
        page_size: 10,
      });
    });
    expect(await screen.findByText("static/index-2.html")).toBeInTheDocument();
  });

  it("keeps the latest archive page when requests resolve out of order", async () => {
    const pageTwo = deferred<ReturnType<typeof archivePageResponse>>();
    const pageThree = deferred<ReturnType<typeof archivePageResponse>>();
    mocks.dreamLogsApi.listArchiveItems.mockImplementation(
      ({ page, page_size }: { page: number; page_size: number }) => {
        if (page === 2) return pageTwo.promise;
        if (page === 3) return pageThree.promise;
        return Promise.resolve(archivePageResponse(page, page_size));
      },
    );

    render(<ArchiveGovernance />);
    expect(await screen.findByText("static/index-1.html")).toBeInTheDocument();

    fireEvent.click(screen.getByTitle("2"));
    await waitFor(() => {
      expect(mocks.dreamLogsApi.listArchiveItems).toHaveBeenCalledWith({
        page: 2,
        page_size: 10,
      });
    });
    fireEvent.click(screen.getByTitle("3"));
    await waitFor(() => {
      expect(mocks.dreamLogsApi.listArchiveItems).toHaveBeenCalledWith({
        page: 3,
        page_size: 10,
      });
    });

    await act(async () => {
      pageThree.resolve(archivePageResponse(3));
    });
    expect(await screen.findByText("static/index-3.html")).toBeInTheDocument();

    await act(async () => {
      pageTwo.resolve(archivePageResponse(2));
    });
    await waitFor(() => {
      expect(screen.getByText("static/index-3.html")).toBeInTheDocument();
      expect(screen.queryByText("static/index-2.html")).not.toBeInTheDocument();
    });
  });
});
