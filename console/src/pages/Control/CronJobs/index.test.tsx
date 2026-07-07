import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CronJobSpecOutput } from "@/api/types";
import CronJobsPage from "./index";

const mocks = vi.hoisted(() => {
  const job: CronJobSpecOutput = {
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
  return {
    job,
    getUserTimezone: vi.fn(),
    getCurrentCronBroadcastTask: vi.fn(),
    getCronBroadcastTask: vi.fn(),
    broadcastCronJob: vi.fn(),
    message: {
      error: vi.fn(),
      info: vi.fn(),
      success: vi.fn(),
      warning: vi.fn(),
    },
  };
});

vi.mock("../../../api", () => ({
  default: {
    getUserTimezone: mocks.getUserTimezone,
    getCurrentCronBroadcastTask: mocks.getCurrentCronBroadcastTask,
    getCronBroadcastTask: mocks.getCronBroadcastTask,
    broadcastCronJob: mocks.broadcastCronJob,
  },
}));

vi.mock("../../../hooks/useAppMessage", () => ({
  useAppMessage: () => ({ message: mocks.message }),
}));

vi.mock("../../../utils/identity", () => ({
  getUserId: () => "current-tenant",
}));

vi.mock("@/hooks/useExecutionModelOptions", () => ({
  buildExecutionModelKey: () => "tenant-default",
  useExecutionModelOptions: () => ({
    loading: false,
    options: [],
    tenantDefaultLabel: "Tenant default",
  }),
}));

vi.mock("@/components/PageHeader", () => ({
  PageHeader: ({ extra }: { extra?: React.ReactNode }) => <div>{extra}</div>,
}));

vi.mock("@/components/TenantSelector", () => ({
  TenantSelector: ({
    onChange,
    onSelectionInfoChange,
  }: {
    onChange: (tenantIds: string[]) => void;
    onSelectionInfoChange?: (
      targets: Array<{
        tenant_id: string;
        tenant_name?: string | null;
        bbk_id?: string | null;
      }>,
    ) => void;
  }) => (
    <button
      type="button"
      onClick={() => {
        onChange(["tenant-a"]);
        onSelectionInfoChange?.([
          {
            tenant_id: "tenant-a",
            tenant_name: "Tenant A",
            bbk_id: "bbk-a",
          },
        ]);
      }}
    >
      Select tenant
    </button>
  ),
}));

vi.mock("./components", () => ({
  DEFAULT_FORM_VALUES: {
    schedule: {},
  },
  JobDrawer: () => null,
  BroadcastChildrenModal: () => null,
  isBroadcastChildJob: () => false,
  useCronJobs: () => ({
    jobs: [mocks.job],
    loading: false,
    createJob: vi.fn(),
    updateJob: vi.fn(),
    deleteJob: vi.fn(),
    toggleEnabled: vi.fn(),
    toggleBatchDispatch: vi.fn(),
    executeNow: vi.fn(),
  }),
  createColumns: (handlers: {
    onBroadcast: (job: CronJobSpecOutput) => void;
  }) => [
    {
      title: "名称",
      dataIndex: "name",
      key: "name",
    },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, job: CronJobSpecOutput) => (
        <button type="button" onClick={() => handlers.onBroadcast(job)}>
          广播到租户
        </button>
      ),
    },
  ],
}));

describe("CronJobsPage broadcast task refresh", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getUserTimezone.mockResolvedValue({ timezone: "UTC" });
    mocks.getCurrentCronBroadcastTask.mockResolvedValue({
      task: {
        task_id: "task-1",
        status: "running",
        tenant_count: 5,
        completed_count: 2,
        failed_count: 0,
        results: [],
        reused: true,
      },
    });
    mocks.getCronBroadcastTask.mockResolvedValue({
      task_id: "task-1",
      status: "running",
      tenant_count: 5,
      completed_count: 4,
      failed_count: 0,
      results: [],
      reused: true,
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("refreshes the visible progress for a running broadcast task", async () => {
    render(<CronJobsPage />);

    fireEvent.click(screen.getByRole("button", { name: "广播到租户" }));

    expect(
      await screen.findByText("Broadcasting 2/5 tenants"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "刷新进度" }));

    await waitFor(() => {
      expect(mocks.getCronBroadcastTask).toHaveBeenCalledWith(
        "job-source",
        "task-1",
      );
    });
    expect(
      await screen.findByText("Broadcasting 4/5 tenants"),
    ).toBeInTheDocument();
  });

  it("prevents a second broadcast from the visible completed result", async () => {
    mocks.getCurrentCronBroadcastTask.mockResolvedValue({ task: null });
    mocks.broadcastCronJob.mockResolvedValue({
      task_id: "task-completed",
      status: "completed",
      tenant_count: 1,
      completed_count: 1,
      failed_count: 0,
      results: [
        {
          tenant_id: "tenant-a",
          success: true,
          job_id: "job-copy",
          cron: "0 5 * * thu,fri,sat,sun",
          timezone: "Asia/Shanghai",
          offset_minutes: 0,
          notification_timezone: "Asia/Shanghai",
          error: "",
          warning: "",
        },
      ],
      reused: false,
    });

    render(<CronJobsPage />);

    fireEvent.click(screen.getByRole("button", { name: "广播到租户" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Select tenant" }),
    );

    const confirmButton = screen.getByRole("button", { name: /OK/ });
    await waitFor(() => {
      expect(confirmButton).not.toBeDisabled();
    });
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(mocks.broadcastCronJob).toHaveBeenCalledTimes(1);
    });
    expect(
      await screen.findByText("Broadcast completed 1/1 tenants"),
    ).toBeInTheDocument();
    const disabledConfirmButton = screen.getByRole("button", { name: /OK/ });
    expect(disabledConfirmButton).toBeDisabled();

    fireEvent.click(disabledConfirmButton);

    expect(mocks.broadcastCronJob).toHaveBeenCalledTimes(1);
  }, 10000);
});
