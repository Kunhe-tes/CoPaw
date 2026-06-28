import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { Modal as DesignModal } from "@agentscope-ai/design";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CronJobSpecOutput } from "@/api/types";
import { BroadcastChildrenModal } from "./BroadcastChildrenModal";

const mocks = vi.hoisted(() => ({
  listCronBroadcastChildren: vi.fn(),
  refreshCronBroadcastChildren: vi.fn(),
  deleteCronBroadcastChildren: vi.fn(),
  runCronBroadcastChildren: vi.fn(),
}));

vi.mock("../../../../api", () => ({
  default: mocks,
}));

function buildJob(): CronJobSpecOutput {
  return {
    id: "job-source",
    name: "ark",
    enabled: true,
    schedule: {
      type: "cron",
      cron: "0 5 * * thu,fri,sat,sun",
      timezone: "Asia/Shanghai",
    },
    dispatch: {
      type: "channel",
      target: {
        user_id: "source-user",
        session_id: "session-1",
      },
    },
  };
}

function buildChild(jobId = "child-1") {
  return {
    tenant_id: "tenant-b",
    tenant_name: "Bob",
    bbk_id: "100",
    job_id: jobId,
    job_name: "ark",
    enabled: true,
    cron: "0 5 * * thu,fri,sat,sun",
    timezone: "Asia/Shanghai",
    offset_minutes: 240,
    last_status: null,
    last_run_at: null,
    last_error: null,
  };
}

describe("BroadcastChildrenModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.listCronBroadcastChildren.mockResolvedValue({
      items: [],
      status: "idle",
      tenant_count: 0,
      failed_tenants: 0,
      failure_summary: null,
      updated_at: null,
    });
    mocks.refreshCronBroadcastChildren.mockResolvedValue({
      items: [],
      status: "running",
      tenant_count: 0,
      failed_tenants: 0,
      failure_summary: null,
      updated_at: null,
      reused: false,
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("keeps the table inside a wide modal", async () => {
    render(<BroadcastChildrenModal open job={buildJob()} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(mocks.listCronBroadcastChildren).toHaveBeenCalledWith(
        "job-source",
      );
    });

    const modal = document.querySelector(".ant-modal");
    expect(modal).toHaveStyle("width: 1280px");
    expect(modal).toHaveStyle("max-width: calc(100vw - 48px)");
  });

  it("shows duplicate tenant names as separate UID rows", async () => {
    const duplicateSnapshot = {
      status: "completed",
      tenant_count: 2,
      failed_tenants: 0,
      failure_summary: null,
      updated_at: "2026-06-24T08:00:00Z",
      items: [
        {
          tenant_id: "80112233",
          tenant_name: "周欣",
          bbk_id: "100",
          job_id: "child-1",
          job_name: "ark",
          enabled: true,
          cron: "0 5 * * thu,fri,sat,sun",
          timezone: "Asia/Shanghai",
          offset_minutes: 240,
          last_status: null,
          last_run_at: null,
          last_error: null,
        },
        {
          tenant_id: "80245604",
          tenant_name: "周欣",
          bbk_id: "100",
          job_id: "child-2",
          job_name: "ark",
          enabled: true,
          cron: "0 5 * * thu,fri,sat,sun",
          timezone: "Asia/Shanghai",
          offset_minutes: 240,
          last_status: null,
          last_run_at: null,
          last_error: null,
        },
      ],
    };
    mocks.listCronBroadcastChildren.mockResolvedValue(duplicateSnapshot);
    mocks.refreshCronBroadcastChildren.mockResolvedValue({
      ...duplicateSnapshot,
      status: "running",
      reused: false,
    });

    render(<BroadcastChildrenModal open job={buildJob()} onClose={vi.fn()} />);

    expect(
      await screen.findByText("存在同名用户，请以 UID 区分"),
    ).toBeInTheDocument();
    expect(screen.getByText("周欣 (2 个 UID)")).toBeInTheDocument();
    expect(screen.getByText("80112233")).toBeInTheDocument();
    expect(screen.getByText("80245604")).toBeInTheDocument();
  });

  it("starts lookup on open and refresh button triggers a live lookup", async () => {
    mocks.listCronBroadcastChildren
      .mockResolvedValueOnce({
        items: [],
        status: "idle",
        tenant_count: 0,
        failed_tenants: 0,
        failure_summary: null,
        updated_at: null,
      })
      .mockResolvedValueOnce({
        items: [],
        status: "running",
        tenant_count: 2,
        failed_tenants: 0,
        failure_summary: null,
        updated_at: null,
      });
    mocks.refreshCronBroadcastChildren.mockResolvedValue({
      items: [],
      status: "running",
      tenant_count: 2,
      failed_tenants: 0,
      failure_summary: null,
      updated_at: null,
      reused: false,
    });

    render(<BroadcastChildrenModal open job={buildJob()} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(mocks.listCronBroadcastChildren).toHaveBeenCalledWith(
        "job-source",
      );
    });
    await waitFor(() => {
      expect(mocks.refreshCronBroadcastChildren).toHaveBeenCalledWith(
        "job-source",
      );
    });
    expect(await screen.findByText("状态：生成中")).toBeInTheDocument();
    expect(screen.getByText("数据时间：正在生成中")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /刷\s*新/ }));

    await waitFor(() => {
      expect(mocks.refreshCronBroadcastChildren).toHaveBeenCalledTimes(2);
    });
    expect(mocks.listCronBroadcastChildren).toHaveBeenCalledTimes(1);
  });

  it("triggers a live lookup after running selected children", async () => {
    const child = buildChild();
    const snapshot = {
      items: [child],
      status: "completed",
      tenant_count: 1,
      failed_tenants: 0,
      failure_summary: null,
      updated_at: "2026-06-24T08:00:00Z",
    };
    mocks.listCronBroadcastChildren.mockResolvedValue(snapshot);
    mocks.refreshCronBroadcastChildren.mockResolvedValue({
      ...snapshot,
      status: "running",
      reused: false,
    });
    mocks.runCronBroadcastChildren.mockResolvedValue({
      results: [
        {
          tenant_id: "tenant-b",
          job_id: "child-1",
          success: true,
          status: "started",
          message: "",
        },
      ],
    });

    render(<BroadcastChildrenModal open job={buildJob()} onClose={vi.fn()} />);

    expect(await screen.findByText("child-1")).toBeInTheDocument();
    const rowCheckboxes = screen.getAllByRole("checkbox");
    fireEvent.click(rowCheckboxes[1]);

    fireEvent.click(screen.getByRole("button", { name: "批量重跑" }));

    await waitFor(() => {
      expect(mocks.runCronBroadcastChildren).toHaveBeenCalledWith(
        "job-source",
        [{ tenant_id: "tenant-b", job_id: "child-1" }],
      );
    });
    await waitFor(() => {
      expect(mocks.refreshCronBroadcastChildren).toHaveBeenCalledTimes(2);
    });
    expect(mocks.listCronBroadcastChildren).toHaveBeenCalledTimes(1);
  });

  it("hides deleted child rows and triggers a live lookup after delete", async () => {
    const child = buildChild();
    const snapshot = {
      items: [child],
      status: "completed",
      tenant_count: 1,
      failed_tenants: 0,
      failure_summary: null,
      updated_at: "2026-06-24T08:00:00Z",
    };
    mocks.listCronBroadcastChildren.mockResolvedValue(snapshot);
    mocks.refreshCronBroadcastChildren.mockResolvedValue({
      ...snapshot,
      status: "running",
      reused: false,
    });
    mocks.deleteCronBroadcastChildren.mockResolvedValue({
      results: [
        {
          tenant_id: "tenant-b",
          job_id: "child-1",
          success: true,
          status: "deleted",
          message: "",
        },
      ],
    });
    const confirmSpy = vi
      .spyOn(DesignModal, "confirm")
      .mockImplementation(
        (config: Parameters<typeof DesignModal.confirm>[0]) => {
          void config.onOk?.();
          return {
            destroy: vi.fn(),
            update: vi.fn(),
          } as ReturnType<typeof DesignModal.confirm>;
        },
      );

    render(<BroadcastChildrenModal open job={buildJob()} onClose={vi.fn()} />);

    expect(await screen.findByText("child-1")).toBeInTheDocument();
    const rowCheckboxes = screen.getAllByRole("checkbox");
    fireEvent.click(rowCheckboxes[1]);

    fireEvent.click(screen.getByRole("button", { name: "批量删除" }));

    await waitFor(() => {
      expect(confirmSpy).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(mocks.deleteCronBroadcastChildren).toHaveBeenCalledWith(
        "job-source",
        [{ tenant_id: "tenant-b", job_id: "child-1" }],
      );
    });
    await waitFor(() => {
      expect(mocks.refreshCronBroadcastChildren).toHaveBeenCalledTimes(2);
    });
    expect(mocks.listCronBroadcastChildren).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("child-1")).not.toBeInTheDocument();

    confirmSpy.mockRestore();
  });
});
