import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CronDispatchBatchDetailResponse,
  CronDispatchBatchesResponse,
} from "../../../api/modules/monitor";
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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve;
  });
  return { promise, resolve };
}

async function selectOption(label: string, option: string) {
  fireEvent.mouseDown(screen.getByLabelText(label));
  const target = (await screen.findAllByText(option)).find((element) =>
    element.closest(".ant-select-item-option"),
  );
  expect(target).toBeDefined();
  fireEvent.click(target!);
}

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
        {
          batch_id: "cron:batch-b",
          parent_job_id: "parent-b",
          parent_external_job_id: "external-b",
          tenant_id: "tenant-b",
          source_id: "CMB-MALL",
          provider_id: "provider-z",
          model_id: "model-z",
          agent_id: "agent-b",
          scheduled_fire_at: "2026-07-08T13:00:00",
          callback_received_at: "2026-07-08T09:00:00",
          status: "failed",
          lock_owner: "worker-b",
          locked_at: "2026-07-08T09:00:20",
          total_count: 5,
          completed_count: 2,
          failed_count: 3,
          error_message: "failed",
          completed_at: "2026-07-08T09:10:00",
          created_at: "2026-07-08T09:00:00",
          updated_at: "2026-07-08T09:10:00",
        },
      ],
      total: 2,
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
      intent_total: 3,
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
        {
          id: 1002,
          batch_id: "cron:batch-a",
          intent_role: "parent",
          status: "completed",
          source_id: "CMB-MALL",
          provider_id: "aaa",
          model_id: "bbb",
          tenant_id: "tenant-parent",
          agent_id: "agent-a",
          job_id: "job-parent",
          parent_job_id: "parent-a",
          scheduled_fire_at: "2026-07-08T12:00:00",
          due_at: "2026-07-08T08:04:00",
          dispatch_order: 0,
          viewer_heat_score: 0,
          attempt_count: 1,
          max_attempts: 3,
          lock_owner: "worker-a",
          locked_at: null,
          acked_at: null,
          completed_at: "2026-07-08T08:04:00",
          error_message: "",
          created_at: "2026-07-08T08:00:00",
          updated_at: "2026-07-08T08:04:00",
        },
        {
          id: 1003,
          batch_id: "cron:batch-a",
          intent_role: "child",
          status: "failed",
          source_id: "CMB-MALL",
          provider_id: "aaa",
          model_id: "bbb",
          tenant_id: "tenant-match",
          agent_id: "agent-a",
          job_id: "job-matching",
          parent_job_id: "parent-a",
          scheduled_fire_at: "2026-07-08T12:00:00",
          due_at: "2026-07-08T08:06:00",
          dispatch_order: 2,
          viewer_heat_score: 0,
          attempt_count: 3,
          max_attempts: 3,
          lock_owner: "worker-a",
          locked_at: null,
          acked_at: null,
          completed_at: "2026-07-08T08:06:00",
          error_message: "timeout",
          created_at: "2026-07-08T08:00:00",
          updated_at: "2026-07-08T08:06:00",
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
          strategy_schedule: [
            { start_time: "16:00", end_time: "21:00", strategy_id: "peak_1" },
          ],
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
        { intent_limit: "500", event_limit: "500" },
      );
    });

    expect(screen.getAllByText("parent-a").length).toBeGreaterThan(0);
    expect(screen.getAllByText("aaa").length).toBeGreaterThan(0);
    expect(screen.getAllByText("bbb").length).toBeGreaterThan(0);
    expect(screen.getByText("success_70_90_add_1")).toBeInTheDocument();
  });

  it("filters the current Batch page and selects the first matching detail", async () => {
    render(<CronBatchDispatchPage />);

    await waitFor(() => {
      expect(monitorApiMock.getCronDispatchBatchDetail).toHaveBeenCalledWith(
        "cron:batch-a",
        { intent_limit: "500", event_limit: "500" },
      );
    });

    fireEvent.change(screen.getByLabelText("筛选当前页 Batch"), {
      target: { value: "model-z" },
    });

    expect(screen.getByText("1 / 2 当前页")).toBeInTheDocument();
    expect(screen.queryByText("external-a")).not.toBeInTheDocument();
    expect(screen.getByText("external-b")).toBeInTheDocument();
    await waitFor(() => {
      expect(monitorApiMock.getCronDispatchBatchDetail).toHaveBeenCalledWith(
        "cron:batch-b",
        { intent_limit: "500", event_limit: "500" },
      );
    });
  });

  it("combines Intent text, role and status filters", async () => {
    render(<CronBatchDispatchPage />);

    await screen.findByText("job-matching");
    fireEvent.change(screen.getByLabelText("筛选 Intent"), {
      target: { value: "job" },
    });
    expect(screen.getByText("3 / 3 条")).toBeInTheDocument();

    await selectOption("Intent 角色", "子任务");
    expect(screen.getByText("2 / 3 条")).toBeInTheDocument();
    expect(screen.queryByText("job-parent")).not.toBeInTheDocument();

    await selectOption("Intent 状态", "失败");

    expect(screen.getByText("1 / 3 条")).toBeInTheDocument();
    expect(screen.getByText("job-matching")).toBeInTheDocument();
    expect(screen.queryByText("job-parent")).not.toBeInTheDocument();
    expect(screen.queryByText("job-a")).not.toBeInTheDocument();
  });

  it("ignores stale Batch responses after the date filter changes", async () => {
    const initialResponse =
      (await monitorApiMock.getCronDispatchBatches()) as CronDispatchBatchesResponse;
    monitorApiMock.getCronDispatchBatches.mockClear();
    const secondBatch = initialResponse.items[1];
    expect(secondBatch).toBeDefined();

    const firstRequest = deferred<CronDispatchBatchesResponse>();
    const secondRequest = deferred<CronDispatchBatchesResponse>();
    let requestCount = 0;
    monitorApiMock.getCronDispatchBatches.mockImplementation(() => {
      requestCount += 1;
      return requestCount === 1 ? firstRequest.promise : secondRequest.promise;
    });

    render(<CronBatchDispatchPage />);
    await waitFor(() => {
      expect(monitorApiMock.getCronDispatchBatches).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(screen.getByText("近24h"));
    await waitFor(() => {
      expect(monitorApiMock.getCronDispatchBatches).toHaveBeenCalledTimes(2);
    });

    secondRequest.resolve({
      ...initialResponse,
      items: [secondBatch!],
      total: 1,
    });
    expect(await screen.findByText("external-b")).toBeInTheDocument();

    firstRequest.resolve(initialResponse);
    await waitFor(() => {
      expect(screen.getByText("external-b")).toBeInTheDocument();
      expect(screen.queryByText("external-a")).not.toBeInTheDocument();
    });
  });

  it("ignores stale detail responses after switching Batch", async () => {
    const batchADetail = (await monitorApiMock.getCronDispatchBatchDetail(
      "cron:batch-a",
    )) as CronDispatchBatchDetailResponse;
    monitorApiMock.getCronDispatchBatchDetail.mockClear();

    const batchARequest = deferred<CronDispatchBatchDetailResponse>();
    const batchBRequest = deferred<CronDispatchBatchDetailResponse>();
    const batchBDetail: CronDispatchBatchDetailResponse = {
      ...batchADetail,
      batch: {
        ...batchADetail.batch,
        batch_id: "cron:batch-b",
        parent_job_id: "parent-b",
        parent_external_job_id: "external-b",
        provider_id: "provider-z",
        model_id: "model-z",
      },
      intents: [],
      intent_total: 0,
      events: [],
    };
    monitorApiMock.getCronDispatchBatchDetail.mockImplementation(
      (batchId: string) =>
        batchId === "cron:batch-a"
          ? batchARequest.promise
          : batchBRequest.promise,
    );

    render(<CronBatchDispatchPage />);
    await waitFor(() => {
      expect(monitorApiMock.getCronDispatchBatchDetail).toHaveBeenCalledWith(
        "cron:batch-a",
        { intent_limit: "500", event_limit: "500" },
      );
    });

    fireEvent.change(screen.getByLabelText("筛选当前页 Batch"), {
      target: { value: "model-z" },
    });
    await waitFor(() => {
      expect(monitorApiMock.getCronDispatchBatchDetail).toHaveBeenCalledWith(
        "cron:batch-b",
        { intent_limit: "500", event_limit: "500" },
      );
    });

    batchBRequest.resolve(batchBDetail);
    expect(
      await screen.findByRole("heading", { name: "external-b" }),
    ).toBeInTheDocument();

    batchARequest.resolve(batchADetail);
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "external-b" }),
      ).toBeInTheDocument();
      expect(
        screen.queryByRole("heading", { name: "external-a" }),
      ).not.toBeInTheDocument();
    });
  }, 10_000);

  it("switches between Intent and dispatch event tabs", async () => {
    render(<CronBatchDispatchPage />);

    await screen.findByText("job-matching");
    expect(screen.queryByText("retry_scheduled")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /调度事件/ }));
    expect(await screen.findByText("retry_scheduled")).toBeInTheDocument();
    expect(screen.queryByText("job-matching")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Intent/ }));
    expect(await screen.findByText("job-matching")).toBeInTheDocument();
  });

  it("allows a super manager without the regular manager flag", async () => {
    iframeState.manager = false;
    iframeState.isSuperManager = true;

    render(<CronBatchDispatchPage />);

    expect(screen.getByText("批调度监控")).toBeInTheDocument();
    await waitFor(() => {
      expect(monitorApiMock.getCronDispatchBatches).toHaveBeenCalledTimes(1);
    });
  });

  it("blocks non-admin users", () => {
    iframeState.manager = false;
    iframeState.isSuperManager = false;

    render(<CronBatchDispatchPage />);

    expect(
      screen.getByText("仅管理员可访问批调度监控页面"),
    ).toBeInTheDocument();
    expect(monitorApiMock.getCronDispatchBatches).not.toHaveBeenCalled();
  });
});
