import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { JoinTracking } from "./JoinTracking";
import { joinInsuranceTracking } from "./api";
import type { Customer } from "../../types";

vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  joinInsuranceTracking: vi.fn(),
}));
const customer: Customer = {
  id: "insurance|c1",
  custUid: "c1",
  skillId: "insurance",
  name: "林芳",
  task: "保险初筛识别",
  category: "保险",
  traced: 0,
  label: "",
  reason: "",
  done: false,
  channel: "",
  time: "",
  note: "",
};
const onAdded = vi.fn();
const originalShowModal = HTMLDialogElement.prototype.showModal;
const originalClose = HTMLDialogElement.prototype.close;
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(joinInsuranceTracking).mockResolvedValue(undefined);
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
  };
});
afterEach(() => {
  cleanup();
  HTMLDialogElement.prototype.showModal = originalShowModal;
  HTMLDialogElement.prototype.close = originalClose;
});

it.each([1, undefined, null])(
  "traced=%s 禁止加入，未知状态不当作未追踪",
  (traced) => {
    render(
      <JoinTracking customer={{ ...customer, traced }} onAdded={onAdded} />,
    );
    const button = screen.getByRole("button", {
      name: traced === 1 ? "已加入跟踪" : "加入跟踪",
    });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(joinInsuranceTracking).not.toHaveBeenCalled();
  },
);

it("未追踪可打开确认弹窗，取消不保存", () => {
  render(<JoinTracking customer={customer} onAdded={onAdded} />);
  fireEvent.click(screen.getByRole("button", { name: "加入跟踪" }));
  fireEvent.change(screen.getByLabelText(/保险计划/), {
    target: { value: "家庭保障计划" },
  });
  expect(screen.getByRole("dialog")).toHaveTextContent("林芳");
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(joinInsuranceTracking).not.toHaveBeenCalled();
});

it("等待成功才通知列表更新，在途防重复提交并阻止关闭", async () => {
  let resolve!: () => void;
  vi.mocked(joinInsuranceTracking).mockImplementationOnce(
    () =>
      new Promise((yes) => {
        resolve = yes;
      }),
  );
  const { rerender } = render(
    <JoinTracking customer={customer} onAdded={onAdded} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "加入跟踪" }));
  fireEvent.change(screen.getByLabelText(/保险计划/), {
    target: { value: "家庭保障计划" },
  });
  const confirm = screen.getByRole("button", { name: "确认添加" });
  fireEvent.click(confirm);
  fireEvent.click(confirm);
  await waitFor(() => expect(joinInsuranceTracking).toHaveBeenCalledTimes(1));
  expect(onAdded).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "取消" })).toBeDisabled();
  fireEvent(
    screen.getByRole("dialog"),
    new Event("cancel", { cancelable: true }),
  );
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  await act(async () => resolve());
  expect(onAdded).toHaveBeenCalledExactlyOnceWith("c1");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  rerender(
    <JoinTracking customer={{ ...customer, traced: 1 }} onAdded={onAdded} />,
  );
  expect(screen.getByRole("button", { name: "已加入跟踪" })).toBeDisabled();
});

it("失败保留确认弹窗，重试沿用同一请求ID，成功只通知一次", async () => {
  vi.mocked(joinInsuranceTracking).mockRejectedValueOnce(new Error("服务失败"));
  render(<JoinTracking customer={customer} onAdded={onAdded} />);
  fireEvent.click(screen.getByRole("button", { name: "加入跟踪" }));
  fireEvent.change(screen.getByLabelText(/保险计划/), {
    target: { value: "家庭保障计划" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认添加" }));
  await screen.findByRole("alert");
  expect(onAdded).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "确认添加" }));
  await waitFor(() => expect(onAdded).toHaveBeenCalledTimes(1));
  const calls = vi.mocked(joinInsuranceTracking).mock.calls;
  expect(calls[0][0]).toEqual(customer);
  expect(calls[0][2]).toBe(calls[1][2]);
  expect(calls[0][2]).toMatch(/^[\da-f-]{36}$/);
});

it("卸载中止请求，迟到成功不污染新页面", async () => {
  let resolve!: () => void;
  vi.mocked(joinInsuranceTracking).mockImplementationOnce(
    () =>
      new Promise((yes) => {
        resolve = yes;
      }),
  );
  const { unmount } = render(
    <JoinTracking customer={customer} onAdded={onAdded} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "加入跟踪" }));
  fireEvent.change(screen.getByLabelText(/保险计划/), {
    target: { value: "家庭保障计划" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认添加" }));
  await waitFor(() => expect(joinInsuranceTracking).toHaveBeenCalledTimes(1));
  const signal = vi.mocked(joinInsuranceTracking).mock.calls[0][3];
  unmount();
  expect(signal?.aborted).toBe(true);
  await act(async () => resolve());
  expect(onAdded).not.toHaveBeenCalled();
});

it("多条接触计划独立增删、校验并以 number 枚举提交，资产零值保留", async () => {
  render(
    <JoinTracking
      customer={{
        ...customer,
        dynamicFields: [{ name: "aum", label: "资产", value: "0" }],
      }}
      onAdded={onAdded}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "加入跟踪" }));
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByText("0")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "确认添加" }));
  await screen.findByText("请输入保险计划");
  fireEvent.change(screen.getByLabelText(/保险计划/), {
    target: { value: " 家庭保障计划 " },
  });
  fireEvent.click(screen.getByRole("button", { name: "新增接触计划" }));
  let plan = screen.getByRole("group", { name: "接触计划1" });
  fireEvent.change(within(plan).getByLabelText("接触日期"), {
    target: { value: "2026-11-06" },
  });
  fireEvent.change(within(plan).getByLabelText("接触安排"), {
    target: { value: "第一条" },
  });
  fireEvent.click(screen.getByRole("button", { name: "新增接触计划" }));
  plan = screen.getByRole("group", { name: "接触计划2" });
  fireEvent.change(within(plan).getByLabelText("接触日期"), {
    target: { value: "2026-11-07" },
  });
  fireEvent.change(within(plan).getByLabelText("触达方式"), {
    target: { value: "3" },
  });
  fireEvent.change(within(plan).getByLabelText("接触安排"), {
    target: { value: " 第二条 " },
  });
  fireEvent.click(screen.getByRole("button", { name: "删除接触计划1" }));
  plan = screen.getByRole("group", { name: "接触计划1" });
  expect(within(plan).getByLabelText("接触安排")).toHaveValue(" 第二条 ");
  expect(within(plan).getByLabelText("触达方式")).toHaveValue("3");
  fireEvent.click(screen.getByRole("button", { name: "新增接触计划" }));
  fireEvent.click(screen.getByRole("button", { name: "确认添加" }));
  await screen.findByText("请选择接触日期");
  await screen.findByText("请输入接触安排");
  expect(joinInsuranceTracking).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "删除接触计划2" }));
  fireEvent.change(screen.getByLabelText("客户意向度"), {
    target: { value: "3" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认添加" }));
  await waitFor(() =>
    expect(joinInsuranceTracking).toHaveBeenCalledWith(
      expect.anything(),
      {
        insurancePlan: "家庭保障计划",
        contactPlans: [{ date: "2026-11-07", method: 3, content: "第二条" }],
        intention: 3,
      },
      expect.any(String),
      expect.any(AbortSignal),
    ),
  );
}, 15000);

it("加入弹窗的保险计划和每条接触安排均限制1000字", async () => {
  render(<JoinTracking customer={customer} onAdded={onAdded} />);
  fireEvent.click(screen.getByRole("button", { name: "加入跟踪" }));
  fireEvent.click(screen.getByRole("button", { name: "新增接触计划" }));
  const input = screen.getByLabelText(/保险计划/);
  const contact = screen.getByLabelText("接触安排");
  expect(input).toHaveAttribute("maxlength", "1000");
  expect(contact).toHaveAttribute("maxlength", "1000");
  fireEvent.change(input, { target: { value: "保".repeat(1001) } });
  fireEvent.change(contact, { target: { value: "访".repeat(1001) } });
  fireEvent.change(screen.getByLabelText("接触日期"), {
    target: { value: "2026-11-07" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认添加" }));
  await waitFor(() =>
    expect(screen.getAllByText("最多只能输入1000字")).toHaveLength(2),
  );
  expect(joinInsuranceTracking).not.toHaveBeenCalled();
});
