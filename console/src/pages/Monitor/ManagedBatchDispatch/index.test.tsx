import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ManagedBatchDispatchPage from "./index";

const api = vi.hoisted(() => ({
  batches: vi.fn(),
  detail: vi.fn(),
  workers: vi.fn(),
  workerOccupants: vi.fn(),
  failures: vi.fn(),
}));
const context = vi.hoisted(() => ({
  source: "bank",
  userId: "manager",
  manager: true,
  isSuperManager: false,
}));
vi.mock("../../../api/modules/managedBatchBoard", () => ({
  managedBatchBoard: api,
}));
vi.mock("../../../stores/iframeStore", () => ({
  useIframeStore: (selector: (state: typeof context) => unknown) =>
    selector(context),
}));
vi.mock("../CronBatchDispatch/WorkerHistoryChart", () => ({
  default: () => <div>测试容量曲线</div>,
}));
beforeEach(() => {
  vi.clearAllMocks();
  api.workerOccupants.mockResolvedValue({
    total: 0,
    page: 1,
    page_size: 10,
    sampled_at: "2026-11-12T01:00:00Z",
    items: [],
  });
  context.manager = true;
  api.batches.mockResolvedValue({
    items: [],
    total: 0,
    stats: {
      total_batches: 0,
      total_members: 0,
      done_members: 0,
      failed_members: 0,
      running_batches: 0,
    },
  });
  api.workers.mockResolvedValue({
    source_id: "bank",
    policies: [],
    current_capacity: [],
    capacity_events: [],
    capacity_events_next_cursor: null,
  });
});
afterEach(cleanup);
it("非管理员不加载跨用户看板数据", () => {
  context.manager = false;
  render(<ManagedBatchDispatchPage />);
  expect(screen.getByText("仅管理员可访问批调度看板（新）")).toBeTruthy();
  expect(api.batches).not.toHaveBeenCalled();
  expect(api.workers).not.toHaveBeenCalled();
  expect(api.workerOccupants).not.toHaveBeenCalled();
});

it("当前 Worker 占用独立查询并展示任务明细", async () => {
  api.workerOccupants.mockResolvedValue({
    total: 1,
    page: 1,
    page_size: 10,
    sampled_at: "2026-11-12T01:00:00Z",
    items: [
      {
        id: "managed:one",
        provider_id: "provider",
        model_id: "model",
        tenant_id: "80074361",
        tenant_name: "测试人员",
        job_id: "worker-job",
        job_name: "日报定时任务",
        started_at: null,
        status: "accepted",
        execution_type: "daily_failure_retry",
      },
    ],
  });
  render(<ManagedBatchDispatchPage />);
  expect(
    await screen.findByRole("heading", { name: "当前 Worker 占用（1）" }),
  ).toBeVisible();
  expect(screen.getByText("测试人员")).toBeInTheDocument();
  expect(screen.getByText("80074361")).toBeInTheDocument();
  expect(screen.getByText("日报定时任务")).toBeInTheDocument();
  expect(screen.getByText("worker-job")).toBeInTheDocument();
  expect(screen.getByText("尚未开始")).toBeInTheDocument();
  expect(screen.getByText("整点补跑")).toBeInTheDocument();
  expect(api.workerOccupants).toHaveBeenCalledWith(
    "bank",
    { page: 1, page_size: 10 },
    expect.any(AbortSignal),
  );
});
it("零成员不伪造百分之百完成率，空数据没有旧接口回退", async () => {
  render(<ManagedBatchDispatchPage />);
  await waitFor(() => expect(api.batches).toHaveBeenCalled());
  const overview = screen.getByRole("region", { name: "新版批调度概览" });
  await waitFor(() =>
    expect(
      within(overview).getByText("任务完成率").parentElement?.textContent,
    ).toContain("-"),
  );
  expect(within(overview).queryByText("100%")).toBeNull();
  expect(await screen.findByText("当前范围内暂无 Batch")).toBeTruthy();
  expect(api.detail).not.toHaveBeenCalled();
});
it("共享容量中途失败明确标记不完整，不显示成功曲线", async () => {
  api.workers
    .mockResolvedValueOnce({
      source_id: "bank",
      policies: [],
      current_capacity: [],
      capacity_events: [],
      capacity_events_next_cursor: "next-page",
    })
    .mockRejectedValueOnce(new Error("history_unavailable"));
  render(<ManagedBatchDispatchPage />);
  expect(
    await screen.findByText("容量历史不完整：history_unavailable"),
  ).toBeTruthy();
  expect(screen.queryByText("测试容量曲线")).toBeNull();
});

it("批次列表显示父任务模型、入口暂停、成功失败及跳过数量", async () => {
  const batch = {
    batch_id: "batch",
    job_id: "parent",
    job_name: "日报",
    member_count: 4,
    done_count: 4,
    failed_count: 1,
    success_count: 2,
    skipped_count: 1,
    status: "failed",
    completion_rate: 1,
    dispatch_paused: true,
    provider_id: "provider",
    model_id: "model",
  };
  api.batches.mockResolvedValue({ items: [batch], total: 1, stats: {} });
  api.detail.mockResolvedValue({
    batch,
    members: [],
    member_total: 4,
    events: [],
    event_total: 0,
  });
  render(<ManagedBatchDispatchPage />);
  const row = await screen.findByRole("button", { name: /日报.*parent/ });
  expect(within(row).getByText("provider / model")).toBeInTheDocument();
  expect(within(row).getByText("成功 2 个")).toBeInTheDocument();
  expect(within(row).getByText("失败 1 个")).toBeInTheDocument();
  expect(within(row).getByText("跳过／取消 1 个")).toBeInTheDocument();
});

it("运行中批次只提示入口暂停，不误称已入队任务暂停", async () => {
  const batch = {
    batch_id: "batch",
    job_id: "parent",
    job_name: "日报",
    member_count: 4,
    done_count: 1,
    failed_count: 0,
    success_count: 1,
    skipped_count: 0,
    status: "running",
    completion_rate: 0.25,
    dispatch_paused: true,
  };
  api.batches.mockResolvedValue({ items: [batch], total: 1, stats: {} });
  api.detail.mockResolvedValue({
    batch,
    members: [],
    member_total: 4,
    events: [],
    event_total: 0,
  });
  render(<ManagedBatchDispatchPage />);
  expect(await screen.findByText("批调度入口已暂停")).toBeInTheDocument();
  expect(screen.queryByText("后续调度已暂停")).toBeNull();
});
