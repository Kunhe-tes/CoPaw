import { describe, expect, it, vi } from "vitest";
import type { CronJobSpecOutput } from "@/api/types";
import { createColumns } from "./columns";

function buildCronJob(
  overrides: Partial<CronJobSpecOutput> = {},
): CronJobSpecOutput {
  return {
    id: "job-1",
    name: "test job",
    enabled: true,
    schedule: {
      type: "cron",
      cron: "0 9 * * *",
      timezone: "UTC",
    },
    task_type: "agent",
    request: {
      input: [{ role: "user", content: [{ type: "text", text: "hello" }] }],
      session_id: "session-1",
      user_id: "user-1",
    },
    dispatch: {
      type: "channel",
      channel: "console",
      target: {
        user_id: "user-1",
        session_id: "session-1",
      },
      mode: "final",
    },
    runtime: {
      max_concurrency: 1,
    },
    meta: {},
    ...overrides,
  };
}

describe("CronJobs columns", () => {
  it("displays notification delay", () => {
    const columns = createColumns({
      onToggleEnabled: vi.fn(),
      onExecuteNow: vi.fn(),
      onBroadcast: vi.fn(),
      onManageChildren: vi.fn(),
      onEdit: vi.fn(),
      onDelete: vi.fn(),
      onCopySuccess: vi.fn(),
      onCopyError: vi.fn(),
      executionModelOptions: [],
      tenantDefaultModelLabel: "Tenant default",
      t: ((key: string) => key) as any,
    });
    const column = columns.find((item) => item.key === "notification_delay");
    const job = buildCronJob({
      meta: {
        notification_delay_minutes: 120,
      },
    });

    expect(column?.render?.(undefined, job, 0)).toBe("2 小时");
  });
});
