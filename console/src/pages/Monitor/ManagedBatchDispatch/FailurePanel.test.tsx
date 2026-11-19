import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import FailurePanel from "./FailurePanel";

const api = vi.hoisted(() => ({ failures: vi.fn(), retry: vi.fn() }));
vi.mock("../../../api/modules/managedBatchBoard", async () => ({
  ...(await vi.importActual("../../../api/modules/managedBatchBoard")),
  managedBatchBoard: api,
}));
const candidate = {
  member_id: "member",
  execution_id: "execution",
  member_version: 1,
  execution_version: 5,
  definition_version: 1,
  business_attempt: 1,
};
const command = {
  request_id: "saved-request",
  candidates: [candidate],
  confirm_stopped: true,
};
beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  api.failures.mockResolvedValue({
    items: [],
    counts: [],
    has_more: false,
    matched_count: 0,
  });
});
afterEach(cleanup);
it("长错误采用单行省略且悬停可查看完整内容，不撑高分页行", async () => {
  const message = "子任务执行失败：" + "完整错误详情。".repeat(40);
  api.failures.mockResolvedValue({
    counts: [{ failure_type: "other", label: "其他错误", count: 1 }],
    items: [
      {
        ...candidate,
        execution_id: "execution",
        tenant_id: "user",
        failure_type: "other",
        error_code: "cron_async_subtasks_failed",
        error_message: message,
      },
    ],
    has_more: false,
    matched_count: 1,
  });
  render(
    <FailurePanel
      source="bank"
      actor="manager"
      batchId="batch"
      onQueued={() => {}}
    />,
  );
  const error = await screen.findByText(message);
  expect(getComputedStyle(error.closest("td")!).whiteSpace).toBe("nowrap");
  const kind = screen.getByText("业务重试（新快照）");
  expect(getComputedStyle(kind.closest("td")!).whiteSpace).toBe("nowrap");
  fireEvent.mouseOver(error);
  expect(await screen.findByRole("tooltip")).toHaveTextContent(message);
});

it("响应丢失时保留并重提原始请求，不按新预览换请求ID", async () => {
  const key = `managed-batch-retry:${JSON.stringify([
    "bank",
    "manager",
    "batch",
  ])}`;
  sessionStorage.setItem(key, JSON.stringify(command));
  api.retry
    .mockRejectedValueOnce(new Error("response_lost"))
    .mockResolvedValueOnce({ queued: 1, skipped: 0, reused: true });
  const onQueued = vi.fn();
  render(
    <FailurePanel
      source="bank"
      actor="manager"
      batchId="batch"
      onQueued={onQueued}
    />,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "核对并重提原请求" }),
  );
  await screen.findByText(/response_lost/);
  expect(JSON.parse(sessionStorage.getItem(key)!)).toEqual(command);
  fireEvent.click(screen.getByRole("button", { name: "核对并重提原请求" }));
  await waitFor(() => expect(onQueued).toHaveBeenCalledOnce());
  expect(api.retry.mock.calls[0]).toEqual(["bank", "batch", command]);
  expect(api.retry.mock.calls[1]).toEqual(api.retry.mock.calls[0]);
  expect(sessionStorage.getItem(key)).toBeNull();
});

it("切换页大小并翻过 200 条后，只重试当前组的候选", async () => {
  let items = Array.from({ length: 201 }, (_, index) => ({
    ...candidate,
    member_id: `member-${index + 1}`,
    execution_id: `exec-${index + 1}`,
    failure_type: "configuration",
  }));
  api.failures.mockImplementation(
    (_source, _batch, _types, _signal, offset = 0) =>
      Promise.resolve({
        counts: [
          {
            failure_type: "configuration",
            label: "配置错误",
            count: items.length,
          },
        ],
        items: items.slice(offset, offset + 200),
        matched_count: items.length,
        has_more: offset + 200 < items.length,
        offset,
      }),
  );
  api.retry.mockImplementation(async () => {
    items = items.slice(0, -1);
    return { queued: 1, skipped: 0 };
  });
  render(
    <FailurePanel
      source="bank"
      actor="manager"
      batchId="batch"
      onQueued={() => {}}
    />,
  );
  await screen.findByText("exec-5");
  expect(screen.queryByText("exec-6")).toBeNull();
  fireEvent.mouseDown(
    screen.getByRole("combobox", { name: "选择重试失败类型" }),
  );
  fireEvent.click(await screen.findByText("配置错误 (201)"));
  await waitFor(() =>
    expect(api.failures).toHaveBeenLastCalledWith(
      "bank",
      "batch",
      ["configuration"],
      expect.any(AbortSignal),
      0,
    ),
  );
  const sizeControl = screen.getAllByRole("combobox")[1];
  fireEvent.mouseDown(sizeControl);
  fireEvent.click(await screen.findByTitle(/^100\s*\/\s*page$/));
  expect(await screen.findByText("exec-100")).toBeInTheDocument();
  fireEvent.click(screen.getByTitle("3"));
  expect(await screen.findByText("exec-201")).toBeInTheDocument();
  expect(screen.queryByText("exec-1")).toBeNull();
  fireEvent.click(
    screen.getByRole("button", { name: "重试本组的 1 个失败成员" }),
  );
  await waitFor(() =>
    expect(api.retry).toHaveBeenCalledWith(
      "bank",
      "batch",
      expect.objectContaining({
        candidates: [
          { ...candidate, member_id: "member-201", execution_id: "exec-201" },
        ],
      }),
    ),
  );
  expect(await screen.findByText("exec-101")).toBeInTheDocument();
  expect(screen.queryByText("exec-201")).toBeNull();
});

it("失败预览展示原始错误说明，而不只是公开错误码", async () => {
  api.failures.mockResolvedValue({
    counts: [{ failure_type: "configuration", label: "配置错误", count: 1 }],
    matched_count: 1,
    items: [
      {
        ...candidate,
        tenant_id: "user",
        failure_type: "configuration",
        error_code: "cron_execution_failed",
        error_message: "workflow secret value missing: auth_token",
        error_type: "BusinessError",
      },
    ],
  });
  render(
    <FailurePanel
      source="bank"
      actor="manager"
      batchId="batch"
      onQueued={() => {}}
    />,
  );
  expect(
    await screen.findByText("workflow secret value missing: auth_token"),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("columnheader", { name: "原始失败原因" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("columnheader", { name: "重试次数" }),
  ).toBeInTheDocument();
  expect(screen.queryByRole("columnheader", { name: "业务尝试" })).toBeNull();
  expect(screen.getByText("BusinessError")).toBeInTheDocument();
});
