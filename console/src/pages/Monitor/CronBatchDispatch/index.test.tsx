import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CronBatchDispatchPage from "./index";

const monitorApiMock = vi.hoisted(() => ({
  getCronDispatchBatches: vi.fn(),
  getCronDispatchBatchDetail: vi.fn(),
  getCronDispatchWorkers: vi.fn(),
}));

const iframeState = vi.hoisted(() => ({
  source: "CMB-MALL",
  isSuperManager: false,
  manager: true,
}));

vi.mock("../../../api/modules/monitor", async () => {
  const actual = await vi.importActual<
    typeof import("../../../api/modules/monitor")
  >("../../../api/modules/monitor");
  return {
    ...actual,
    monitorApi: monitorApiMock,
  };
});

vi.mock("../../../stores/iframeStore", () => ({
  useIframeStore: (selector: (state: typeof iframeState) => unknown) =>
    selector(iframeState),
}));

describe("CronBatchDispatchPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    iframeState.source = "CMB-MALL";
    iframeState.isSuperManager = false;
    iframeState.manager = true;

    monitorApiMock.getCronDispatchBatches.mockResolvedValue({
      source_id: "CMB-MALL",
      start_time: "2026-07-08T00:00:00",
      end_time: "2026-07-08T23:59:59",
      stats: {
        total_batches: 1,
        running_batches: 1,
        completed_batches: 0,
        failed_batches: 0,
        total_intents: 20,
        completed_intents: 12,
        failed_intents: 1,
        pending_intents: 7,
      },
      items: [
        {
          batch_id: "cron:batch-a",
          parent_job_id: "parent-a",
          parent_external_job_id: "external-a",
          tenant_id: "tenant-a",
          source_id: "CMB-MALL",
          provider_id: "aaa",
          model_id: "bbb",
          agent_id: "agent-a",
          scheduled_fire_at: "2026-07-08T12:00:00",
          callback_received_at: "2026-07-08T08:00:00",
          status: "running",
          lock_owner: "worker-a",
          locked_at: "2026-07-08T08:00:20",
          total_count: 20,
          completed_count: 12,
          failed_count: 1,
          error_message: "",
          completed_at: null,
          created_at: "2026-07-08T08:00:00",
          updated_at: "2026-07-08T08:01:00",
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });

    monitorApiMock.getCronDispatchBatchDetail.mockResolvedValue({
      batch: {
        batch_id: "cron:batch-a",
        parent_job_id: "parent-a",
        parent_external_job_id: "external-a",
        tenant_id: "tenant-a",
        source_id: "CMB-MALL",
        provider_id: "aaa",
        model_id: "bbb",
        agent_id: "agent-a",
        scheduled_fire_at: "2026-07-08T12:00:00",
        callback_received_at: "2026-07-08T08:00:00",
        status: "running",
        lock_owner: "worker-a",
        locked_at: "2026-07-08T08:00:20",
        total_count: 20,
        completed_count: 12,
        failed_count: 1,
        error_message: "",
        completed_at: null,
        created_at: "2026-07-08T08:00:00",
        updated_at: "2026-07-08T08:01:00",
      },
      intent_total: 1,
      intents: [
        {
          id: 1001,
          batch_id: "cron:batch-a",
          intent_role: "child",
          status: "pending",
          source_id: "CMB-MALL",
          provider_id: "aaa",
          model_id: "bbb",
          tenant_id: "tenant-a",
          agent_id: "agent-a",
          job_id: "job-a",
          parent_job_id: "parent-a",
          scheduled_fire_at: "2026-07-08T12:00:00",
          due_at: "2026-07-08T08:05:00",
          dispatch_order: 1,
          viewer_heat_score: 0,
          attempt_count: 0,
          max_attempts: 3,
          lock_owner: "",
          locked_at: null,
          acked_at: null,
          completed_at: null,
          error_message: "",
          created_at: "2026-07-08T08:00:00",
          updated_at: "2026-07-08T08:00:00",
        },
      ],
      events: [
        {
          id: 1,
          batch_id: "cron:batch-a",
          intent_id: 1001,
          event_type: "retry_scheduled",
          worker_id: "worker-a",
          job_id: "job-a",
          tenant_id: "tenant-a",
          source_id: "CMB-MALL",
          details: { error: "timeout" },
          created_at: "2026-07-08T08:06:00",
        },
      ],
    });

    monitorApiMock.getCronDispatchWorkers.mockResolvedValue({
      source_id: "CMB-MALL",
      policies: [
        {
          source_id: "CMB-MALL",
          provider_id: "aaa",
          model_id: "bbb",
          default_strategy_id: "strategy-a",
          strategy_schedule: { windows: [] },
          enabled: true,
          strategy: {
            min_workers: 5,
            baseline_workers: 5,
            max_workers: 999,
            adjust_interval_seconds: 20,
            feedback_window_seconds: 20,
            error_rate_rules: { success_100: "double" },
          },
          created_at: "2026-07-08T07:00:00",
          updated_at: "2026-07-08T07:00:00",
        },
      ],
      current_capacity: [
        {
          id: 10,
          worker_id: "worker-a",
          source_id: "CMB-MALL",
          provider_id: "aaa",
          model_id: "bbb",
          strategy_id: "strategy-a",
          previous_workers: 5,
          baseline_workers: 5,
          min_workers: 5,
          max_workers: 999,
          effective_workers: 10,
          pending_count: 7,
          claimed_count: 2,
          running_count: 1,
          success_count: 12,
          failure_count: 1,
          error_rate: 0.08,
          matched_rule: { reason: "success_70_90_add_1" },
          avg_latency_ms: 1200,
          decision_reason: "success_70_90_add_1",
          created_at: "2026-07-08T08:10:00",
        },
      ],
      capacity_events: [],
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders current source, batches, details, policies and workers", async () => {
    render(<CronBatchDispatchPage />);

    expect(screen.getByText("批调度监控")).toBeInTheDocument();
    expect(screen.getByText("当前渠道 CMB-MALL")).toBeInTheDocument();

    await waitFor(() => {
      expect(monitorApiMock.getCronDispatchBatches).toHaveBeenCalledTimes(1);
      expect(monitorApiMock.getCronDispatchWorkers).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(monitorApiMock.getCronDispatchBatchDetail).toHaveBeenCalledWith(
        "cron:batch-a",
      );
    });

    expect(screen.getAllByText("parent-a").length).toBeGreaterThan(0);
    expect(screen.getByText("retry_scheduled")).toBeInTheDocument();
    expect(screen.getAllByText("aaa").length).toBeGreaterThan(0);
    expect(screen.getAllByText("bbb").length).toBeGreaterThan(0);
    expect(screen.getByText("success_70_90_add_1")).toBeInTheDocument();
  });

  it("blocks non-admin users", () => {
    iframeState.manager = false;
    iframeState.isSuperManager = false;

    render(<CronBatchDispatchPage />);

    expect(screen.getByText("仅管理员可访问批调度监控页面")).toBeInTheDocument();
    expect(monitorApiMock.getCronDispatchBatches).not.toHaveBeenCalled();
  });
});
