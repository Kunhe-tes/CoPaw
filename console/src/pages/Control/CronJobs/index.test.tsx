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
  TenantSelector: () => <div>分发目标</div>,
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
    executeNow: vi.fn(),
  }),
  createColumns: (handlers: { onBroadcast: (job: CronJobSpecOutput) => void }) => [
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
});
