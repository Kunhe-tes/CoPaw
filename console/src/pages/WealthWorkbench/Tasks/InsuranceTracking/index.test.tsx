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
import { InsuranceTracking } from "./index";
import { fetchSceneSkills } from "../../api";
import {
  fetchInsuranceTracking,
  InsuranceSyncError,
  removeInsuranceTracking,
  saveInsuranceChange,
  type InsuranceList,
} from "./api";

vi.mock("../../api", async (original) => ({
  ...(await original<typeof import("../../api")>()),
  fetchSceneSkills: vi.fn(),
}));

vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  fetchInsuranceTracking: vi.fn(),
  removeInsuranceTracking: vi.fn(),
  saveInsuranceChange: vi.fn(),
}));
const fixture = (): InsuranceList => ({
  customers: [
    {
      id: "1",
      custUid: "c1",
      skillId: "insurance-skill",
      sceneName: "保险初筛识别",
      name: "林芳",
      branchName: "城南支行",
      assets: "337.34 万",
      insurancePlan: "家庭医疗保障",
      contactPlans: [
        {
          id: "contact-1",
          date: "2026-11-05",
          method: 2,
          content: "预约保障沟通",
        },
      ],
      intention: 2,
    },
    {
      id: "2",
      custUid: "c2",
      skillId: "insurance-skill",
      sceneName: "保险初筛识别",
      name: "王海",
      assets: "80 万",
      intention: 3,
    },
  ],
  counts: { customers: 22, highIntention: 8, tracking: 12 },
});
const originalShowModal = HTMLDialogElement.prototype.showModal;
const originalClose = HTMLDialogElement.prototype.close;
const showScheme = vi.fn();
const execute = vi.fn().mockResolvedValue(undefined);
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchSceneSkills).mockResolvedValue([
    {
      skillId: "insurance-skill",
      senceName: "保险初筛识别",
      category: "insurance",
      mcpRelationList: [],
    },
  ]);
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
  };
  vi.mocked(fetchInsuranceTracking).mockResolvedValue(fixture());
  vi.mocked(saveInsuranceChange).mockResolvedValue(undefined);
  vi.mocked(removeInsuranceTracking).mockResolvedValue(undefined);
});
afterEach(() => {
  cleanup();
  HTMLDialogElement.prototype.showModal = originalShowModal;
  HTMLDialogElement.prototype.close = originalClose;
});
async function show() {
  const result = render(
    <InsuranceTracking
      refreshKey={0}
      onExecute={execute}
      onShowScheme={showScheme}
    />,
  );
  await screen.findByText("林芳");
  return result;
}

function manyRecords() {
  const data = fixture();
  data.customers[0].contactPlans = Array.from({ length: 50 }, (_, index) => ({
    id: `contact-${index}`,
    date: new Date(Date.UTC(2026, 10, 5 - index)).toISOString().slice(0, 10),
    method: 2,
    content: `接触计划${index + 1}`,
  }));
  data.customers[0].followUps = data.customers[0].contactPlans.map((entry) => ({
    ...entry,
    id: `follow-${entry.id}`,
    result: 0 as const,
    skillId: "insurance-skill",
    sceneName: "保险初筛识别",
    method: 3,
    content: `跟进${entry.content}`,
    date: `${entry.date}T14:30`,
  }));
  vi.mocked(fetchInsuranceTracking).mockResolvedValue(data);
  return data;
}

it("两列默认各一条，独立展开最近三条，全部记录可完整阅读并编辑单条", async () => {
  const data = manyRecords();
  await show();
  expect(screen.getByText("接触计划1")).toBeInTheDocument();
  expect(screen.queryByText("接触计划2")).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "展开更多林芳的接触计划" }),
  );
  expect(screen.getByText("接触计划3")).toBeInTheDocument();
  expect(screen.queryByText("接触计划4")).not.toBeInTheDocument();
  expect(screen.queryByText("跟进接触计划2")).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "查看林芳的全部接触计划" }),
  );
  let dialog = screen.getByRole("dialog");
  expect(within(dialog).getByText("接触计划50")).toBeInTheDocument();
  fireEvent.click(
    within(dialog).getByRole("button", {
      name: `编辑林芳的接触计划 ${data.customers[0].contactPlans![40].date}`,
    }),
  );
  dialog = screen.getByRole("dialog");
  expect(within(dialog).getByLabelText("接触安排")).toHaveValue("接触计划41");
  expect(within(dialog).getByLabelText("接触日期")).toHaveValue(
    data.customers[0].contactPlans![40].date,
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
  fireEvent.click(screen.getByRole("button", { name: "收起林芳的接触计划" }));
  expect(screen.queryByText("接触计划2")).not.toBeInTheDocument();
}, 20000);

it("编辑旧跟进按记录ID保存，乐观重排，回填服务端数据且保留其他记录", async () => {
  const data = manyRecords();
  let resolve!: (
    record: NonNullable<(typeof data.customers)[0]["followUps"]>[number],
  ) => void;
  vi.mocked(saveInsuranceChange).mockImplementationOnce(
    () =>
      new Promise((yes) => {
        resolve = yes;
      }),
  );
  await show();
  fireEvent.click(
    screen.getByRole("button", { name: "展开更多林芳的跟进记录" }),
  );
  fireEvent.click(
    screen.getByRole("button", {
      name: `编辑林芳的跟进记录 ${data.customers[0].followUps![1].date}`,
    }),
  );
  expect(screen.getByLabelText("触达结果")).toHaveValue("0");
  expect(screen.getByLabelText("触达方式")).toHaveValue("3");
  fireEvent.change(screen.getByLabelText("触达时间"), {
    target: { value: "2026-11-07T10:00" },
  });
  fireEvent.change(screen.getByLabelText(/沟通记录/), {
    target: { value: "旧记录修改" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
  await screen.findByText("旧记录修改");
  expect(screen.getByText("跟进接触计划1")).toBeInTheDocument();
  expect(saveInsuranceChange).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({
      kind: "followUp",
      recordId: data.customers[0].followUps![1].id,
    }),
  );
  await act(async () =>
    resolve({
      ...data.customers[0].followUps![1],
      date: "2026-11-07T10:00",
      content: "服务端确认的记录",
    }),
  );
  expect(screen.queryByText("旧记录修改")).not.toBeInTheDocument();
  expect(screen.getByText("服务端确认的记录")).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "查看林芳的全部跟进记录" }),
  );
  expect(
    within(screen.getByRole("dialog")).getAllByRole("button", {
      name: /编辑林芳的跟进记录/,
    }),
  ).toHaveLength(50);
}, 20000);

it("新增计划保留旧记录，成功用服务端ID回填，继续编辑时提交正式ID", async () => {
  const data = manyRecords();
  const saved = {
    id: "server-new",
    date: "2026-11-07",
    method: 2 as const,
    content: "新计划",
  };
  vi.mocked(saveInsuranceChange).mockResolvedValueOnce(saved);
  await show();
  fireEvent.click(screen.getByRole("button", { name: "新增林芳的接触计划" }));
  expect(screen.getByLabelText("接触安排")).toHaveValue("");
  fireEvent.change(screen.getByLabelText("接触日期"), {
    target: { value: saved.date },
  });
  fireEvent.change(screen.getByLabelText("接触安排"), {
    target: { value: saved.content },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await screen.findByText(saved.content);
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: `编辑林芳的接触计划 ${saved.date}` }),
    ).toBeEnabled(),
  );
  fireEvent.click(
    screen.getByRole("button", { name: `编辑林芳的接触计划 ${saved.date}` }),
  );
  fireEvent.change(screen.getByLabelText("接触安排"), {
    target: { value: "继续编辑" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() => expect(saveInsuranceChange).toHaveBeenCalledTimes(2));
  expect(saveInsuranceChange).toHaveBeenLastCalledWith(
    expect.objectContaining({
      contactPlans: expect.arrayContaining([
        data.customers[0].contactPlans![0],
        saved,
      ]),
    }),
    expect.objectContaining({
      recordId: "server-new",
      value: expect.objectContaining({ content: "继续编辑" }),
    }),
  );
}, 20000);

it("旧记录编辑失败后恢复该记录及顺序，重试草稿不会带入另一条", async () => {
  const data = manyRecords();
  vi.mocked(saveInsuranceChange).mockRejectedValueOnce(new Error("保存失败"));
  await show();
  fireEvent.click(
    screen.getByRole("button", { name: "展开更多林芳的接触计划" }),
  );
  const name = `编辑林芳的接触计划 ${data.customers[0].contactPlans![1].date}`;
  fireEvent.click(screen.getByRole("button", { name }));
  fireEvent.change(screen.getByLabelText("接触安排"), {
    target: { value: "未成功的第二条" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await screen.findByRole("alert");
  expect(screen.getByText("接触计划1")).toBeInTheDocument();
  expect(screen.getByText("接触计划2")).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", {
      name: `编辑林芳的接触计划 ${data.customers[0].contactPlans![0].date}`,
    }),
  );
  expect(screen.getByLabelText("接触安排")).toHaveValue("接触计划1");
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  fireEvent.click(screen.getByRole("button", { name }));
  expect(screen.getByLabelText("接触安排")).toHaveValue("未成功的第二条");
}, 20000);
function highCount() {
  return screen.getByText(/高意向客户/).querySelector("b");
}

it.each([0, 1] as const)(
  "触达方式 %s 和待跟进以 number 保存，零值可校验通过",
  async (method) => {
    await show();
    fireEvent.click(screen.getByRole("button", { name: "新增林芳的跟进记录" }));
    expect(screen.getByLabelText("触达方式")).toHaveValue("0");
    fireEvent.change(screen.getByLabelText("触达时间"), {
      target: { value: "2026-11-05T15:00" },
    });
    fireEvent.change(screen.getByLabelText("触达方式"), {
      target: { value: String(method) },
    });
    fireEvent.change(screen.getByLabelText("触达结果"), {
      target: { value: "0" },
    });
    fireEvent.change(screen.getByLabelText(/沟通记录/), {
      target: { value: "数值字段验证" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
    await waitFor(() =>
      expect(saveInsuranceChange).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({
          kind: "followUp",
          value: {
            date: "2026-11-05T15:00",
            method,
            result: 0,
            skillId: "insurance-skill",
            sceneName: "保险初筛识别",
            content: "数值字段验证",
          },
        }),
      ),
    );
    expect(screen.getByText("林芳").closest("tr")).toHaveTextContent(
      method === 0 ? "企微" : "招乎",
    );
  },
  10000,
);

it("待了解提交 number 0，退出高意向时更新人数，失败恢复 number 3", async () => {
  let reject!: (error: Error) => void;
  vi.mocked(saveInsuranceChange).mockImplementationOnce(
    () =>
      new Promise((_, no) => {
        reject = no;
      }),
  );
  await show();
  await chooseIntention("王海", "待了解");
  expect(highCount()).toHaveTextContent("7");
  expect(saveInsuranceChange).toHaveBeenCalledWith(fixture().customers[1], {
    kind: "intention",
    value: 0,
  });
  await act(async () => reject(new Error("保存失败")));
  expect(highCount()).toHaveTextContent("8");
  expect(
    within(screen.getByText("王海").closest("tr")!).getByText("高意向"),
  ).toBeInTheDocument();
}, 10000);
async function chooseIntention(name: string, option: string) {
  fireEvent.mouseDown(
    screen.getByRole("combobox", { name: `${name}的客户意向度` }),
  );
  const choices = screen.getAllByText(option, {
    selector:
      ".ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option-content",
  });
  fireEvent.click(choices[choices.length - 1]);
  fireEvent.mouseDown(document.body);
}

it("展示九列且经营方案紧邻执行列，统计使用服务端全量人数，执行复用现有入口", async () => {
  await show();
  expect(
    screen.getAllByRole("columnheader").map((el) => el.textContent),
  ).toEqual([
    "客户姓名",
    "资产",
    "保险计划",
    "接触计划",
    "最后跟进记录",
    "触达方式",
    "客户意向度",
    "经营方案",
    "执行",
  ]);
  expect(
    within(screen.getByText("林芳").closest("tr")!).getAllByRole("cell")[0]
      .textContent,
  ).toBe("林芳");
  expect(screen.queryByText("城南支行")).not.toBeInTheDocument();
  fireEvent.click(screen.getAllByRole("button", { name: "查看经营方案" })[0]);
  expect(showScheme).toHaveBeenCalledWith(fixture().customers[0]);
  expect(highCount()).toHaveTextContent("8");
  expect(screen.queryByText(/客户数量/)).not.toBeInTheDocument();
  const trackingCount = screen.getByText(/^跟踪客户/, { selector: "span" });
  expect(trackingCount.querySelector("b")).toHaveTextContent("12");
  expect(trackingCount.parentElement?.firstElementChild).toBe(trackingCount);
  expect(trackingCount.nextElementSibling).toHaveTextContent("高意向客户");
  fireEvent.click(screen.getAllByRole("button", { name: /电\s*访/ })[0]);
  expect(execute).toHaveBeenCalledWith("dial", fixture().customers[0]);
});

it("意向度乐观更新人数，保存期间禁用该客户，失败恢复原值和统计", async () => {
  let reject!: (error: Error) => void;
  vi.mocked(saveInsuranceChange).mockImplementation(
    () =>
      new Promise((_, no) => {
        reject = no;
      }),
  );
  await show();
  await chooseIntention("林芳", "高意向");
  expect(highCount()).toHaveTextContent("9");
  expect(
    screen.getByRole("combobox", { name: "林芳的客户意向度" }),
  ).toBeDisabled();
  await act(async () => reject(new Error("失败")));
  expect(highCount()).toHaveTextContent("8");
  expect(screen.getByRole("alert")).toHaveTextContent("已恢复原值");
  expect(
    within(screen.getByText("林芳").closest("tr")!).getByText("中意向"),
  ).toBeInTheDocument();
});

it("不同客户并发修改时，一人的失败不会撤回另一人的成功", async () => {
  let reject!: (error: Error) => void;
  vi.mocked(saveInsuranceChange).mockImplementation((customer) =>
    customer.id === "1"
      ? new Promise((_, no) => {
          reject = no;
        })
      : Promise.resolve(),
  );
  await show();
  await chooseIntention("林芳", "高意向");
  await chooseIntention("王海", "低意向");
  await waitFor(() => expect(highCount()).toHaveTextContent("8"));
  await act(async () => reject(new Error("失败")));
  expect(highCount()).toHaveTextContent("7");
  expect(
    within(screen.getByText("王海").closest("tr")!).getByText("低意向"),
  ).toBeInTheDocument();
});

it("编辑乐观更新并关闭弹窗，失败回滚且重新编辑时恢复填写内容", async () => {
  let reject!: (error: Error) => void;
  vi.mocked(saveInsuranceChange).mockImplementationOnce(
    () =>
      new Promise((_, no) => {
        reject = no;
      }),
  );
  await show();
  fireEvent.click(screen.getByRole("button", { name: "编辑林芳的保险计划" }));
  const dialog = screen.getByRole("dialog");
  const input = within(dialog).getByLabelText("保险计划");
  fireEvent.change(input, { target: { value: "   " } });
  fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
  await within(dialog).findByText("请输入保险计划");
  expect(saveInsuranceChange).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { value: "养老年金计划" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
  await screen.findByText("养老年金计划");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(
    within(screen.getByText("林芳").closest("tr")!).getByRole("status"),
  ).toHaveTextContent("保存中");
  await act(async () => reject(new Error("服务暂不可用")));
  expect(screen.getByText("家庭医疗保障")).toBeInTheDocument();
  expect(screen.queryByText("养老年金计划")).not.toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("已恢复原值");
  fireEvent.click(
    screen.getByRole("button", { name: "修改林芳的保险计划后重试" }),
  );
  const retryDialog = screen.getByRole("dialog");
  expect(within(retryDialog).getByLabelText("保险计划")).toHaveValue(
    "养老年金计划",
  );
  fireEvent.click(within(retryDialog).getByRole("button", { name: "保存" }));
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  await waitFor(() =>
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
  );
  expect(screen.getByText("养老年金计划")).toBeInTheDocument();
  expect(saveInsuranceChange).toHaveBeenLastCalledWith(fixture().customers[0], {
    kind: "insurancePlan",
    value: "养老年金计划",
  });
});

it("新增跟进不带入上一条记录，确认保存后更新最后跟进记录", async () => {
  await show();
  fireEvent.click(screen.getByRole("button", { name: "新增林芳的跟进记录" }));
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("触达时间"), {
    target: { value: "2026-11-04T09:30" },
  });
  fireEvent.change(within(dialog).getByLabelText(/沟通记录/), {
    target: { value: "已沟通保障需求" },
  });
  expect(
    within(dialog).getByRole("combobox", { name: "触达方式" }),
  ).toHaveValue("0");
  expect(
    within(within(dialog).getByRole("combobox", { name: "触达方式" }))
      .getAllByRole("option")
      .map((option) => option.textContent),
  ).toEqual(["企微", "招乎", "电访", "面访"]);
  fireEvent.change(within(dialog).getByRole("combobox", { name: "触达方式" }), {
    target: { value: "3" },
  });
  expect(
    within(within(dialog).getByRole("combobox", { name: "触达结果" }))
      .getAllByRole("option")
      .map((option) => option.textContent),
  ).toEqual(["待跟进", "已完成"]);
  fireEvent.change(within(dialog).getByRole("combobox", { name: "触达结果" }), {
    target: { value: "0" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "保存记录" }));
  await screen.findByText("已沟通保障需求");
  expect(fetchInsuranceTracking).toHaveBeenCalledTimes(1);
  expect(screen.getByText("林芳").closest("tr")).toHaveTextContent(
    "2026-11-04 09:30 · 面访",
  );
  expect(saveInsuranceChange).toHaveBeenCalledWith(fixture().customers[0], {
    kind: "followUp",
    requestId: expect.any(String),
    recordId: undefined,
    value: {
      date: "2026-11-04T09:30",
      method: 3,
      content: "已沟通保障需求",
      result: 0,
      skillId: "insurance-skill",
      sceneName: "保险初筛识别",
    },
  });
});

it("客户超过十条时全部展示且不显示分页，搜索和清空后仍展示完整结果", async () => {
  const data = fixture();
  data.customers.push(
    ...Array.from({ length: 10 }, (_, index) => ({
      id: `extra-${index}`,
      custUid: `extra-customer-${index}`,
      name: `测试客户${index + 1}`,
      assets: "80 万",
      intention: 0 as const,
    })),
  );
  vi.mocked(fetchInsuranceTracking).mockResolvedValue(data);
  await show();
  expect(screen.getAllByRole("row")).toHaveLength(13);
  expect(screen.getByText("测试客户10")).toBeInTheDocument();
  expect(screen.getByText("共 12 条记录")).toBeInTheDocument();
  expect(document.querySelector(".ant-pagination")).toBeNull();
  const search = screen.getByLabelText("搜索保险跟踪客户");
  fireEvent.change(search, { target: { value: "测试客户" } });
  expect(screen.getAllByRole("row")).toHaveLength(11);
  expect(screen.getByText("共 10 条记录")).toBeInTheDocument();
  fireEvent.change(search, { target: { value: "" } });
  expect(screen.getAllByRole("row")).toHaveLength(13);
});

it("本地搜索不改动全量统计，清空搜索后恢复客户", async () => {
  await show();
  fireEvent.change(screen.getByLabelText("搜索保险跟踪客户"), {
    target: { value: "医疗" },
  });
  expect(screen.getByText("林芳")).toBeInTheDocument();
  expect(screen.queryByText("王海")).not.toBeInTheDocument();
  expect(highCount()).toHaveTextContent("8");
  fireEvent.change(screen.getByLabelText("搜索保险跟踪客户"), {
    target: { value: "无此客户" },
  });
  expect(
    screen.getByText("未找到匹配的客户，请调整搜索条件"),
  ).toBeInTheDocument();
  expect(screen.queryByText("暂未添加跟踪客户")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("搜索保险跟踪客户"), {
    target: { value: "" },
  });
  expect(screen.getByText("王海")).toBeInTheDocument();
});

it("加载失败不展示虚构数据，支持重试和真实空名单", async () => {
  vi.mocked(fetchInsuranceTracking).mockRejectedValueOnce(
    new Error("保险跟踪加载失败"),
  );
  render(
    <InsuranceTracking
      refreshKey={0}
      onExecute={execute}
      onShowScheme={showScheme}
    />,
  );
  await screen.findByText("保险跟踪加载失败");
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  vi.mocked(fetchInsuranceTracking).mockResolvedValue({
    customers: [],
    counts: { customers: 0, highIntention: 0, tracking: 0 },
  });
  fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
  await screen.findByText("暂未添加跟踪客户");
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "查看保险任务" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByText("当前暂无保险任务，添加跟踪客户后将在这里展示。"),
  ).toBeInTheDocument();
  expect(highCount()).toHaveTextContent("0");
});

it("较早请求晚返回不能覆盖刷新后的客户", async () => {
  let resolve!: (value: InsuranceList) => void;
  vi.mocked(fetchInsuranceTracking).mockImplementationOnce(
    () =>
      new Promise((yes) => {
        resolve = yes;
      }),
  );
  const { rerender } = render(
    <InsuranceTracking
      refreshKey={0}
      onExecute={execute}
      onShowScheme={showScheme}
    />,
  );
  rerender(
    <InsuranceTracking
      refreshKey={1}
      onExecute={execute}
      onShowScheme={showScheme}
    />,
  );
  await screen.findByText("林芳");
  await act(async () =>
    resolve({
      customers: [],
      counts: { customers: 0, highIntention: 0, tracking: 0 },
    }),
  );
  expect(screen.getByText("林芳")).toBeInTheDocument();
});

it("接触计划回填日期、方式和安排，取消不保存，修改后按字段提交", async () => {
  const data = fixture();
  data.customers[0].contactPlans = [
    {
      id: "contact-1",
      date: "2026-11-05",
      method: 0,
      content: "原接触安排",
    },
  ];
  vi.mocked(fetchInsuranceTracking).mockResolvedValue(data);
  await show();
  fireEvent.click(screen.getByRole("button", { name: /编辑林芳的接触计划/ }));
  let dialog = screen.getByRole("dialog");
  expect(within(dialog).getByLabelText("接触日期")).toHaveValue("2026-11-05");
  expect(within(dialog).getByLabelText("触达方式")).toHaveValue("0");
  expect(within(dialog).getByLabelText("接触安排")).toHaveValue("原接触安排");
  fireEvent.change(within(dialog).getByLabelText("接触安排"), {
    target: { value: "未保存安排" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
  expect(saveInsuranceChange).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: /编辑林芳的接触计划/ }));
  dialog = screen.getByRole("dialog");
  expect(within(dialog).getByLabelText("接触安排")).toHaveValue("原接触安排");
  fireEvent.change(within(dialog).getByLabelText("接触日期"), {
    target: { value: "2026-11-06" },
  });
  fireEvent.change(within(dialog).getByLabelText("触达方式"), {
    target: { value: "3" },
  });
  fireEvent.change(within(dialog).getByLabelText("接触安排"), {
    target: { value: "预约了解家庭保障需求" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
  await screen.findByText("预约了解家庭保障需求");
  expect(saveInsuranceChange).toHaveBeenCalledWith(data.customers[0], {
    kind: "contactPlan",
    requestId: expect.any(String),
    recordId: "contact-1",
    value: {
      date: "2026-11-06",
      method: 3,
      content: "预约了解家庭保障需求",
    },
  });
});

it("新增记录展示客户和场景，时间与沟通记录必填，不回填旧跟进内容", async () => {
  const data = fixture();
  data.customers[0].sceneName = "家庭保险保障";
  data.customers[0].followUps = [
    {
      id: "follow-1",
      date: "2026-11-04T10:00",
      method: 2,
      content: "上次沟通内容",
      result: 1,
      skillId: "insurance-skill",
      sceneName: "保险初筛识别",
    },
  ];
  vi.mocked(fetchInsuranceTracking).mockResolvedValue(data);
  await show();
  fireEvent.click(screen.getByRole("button", { name: "新增林芳的跟进记录" }));
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByLabelText("跟进客户信息")).toHaveTextContent(
    "林芳",
  );
  expect(within(dialog).getByLabelText("跟进客户信息")).toHaveTextContent(
    "家庭保险保障",
  );
  expect(within(dialog).getByLabelText("触达时间")).toHaveValue("");
  expect(within(dialog).getByLabelText(/沟通记录/)).toHaveValue("");
  expect(within(dialog).getByLabelText("触达结果")).toHaveValue("1");
  fireEvent.click(within(dialog).getByRole("button", { name: "保存记录" }));
  await within(dialog).findByText("请选择触达时间");
  await within(dialog).findByText("请输入沟通记录");
  expect(saveInsuranceChange).not.toHaveBeenCalled();
});

it("提交后立即关闭弹窗，在途锁定客户行且重复提交只保存一次", async () => {
  let resolve!: () => void;
  vi.mocked(saveInsuranceChange).mockImplementation(
    () =>
      new Promise((yes) => {
        resolve = yes;
      }),
  );
  await show();
  fireEvent.click(screen.getByRole("button", { name: "编辑林芳的保险计划" }));
  const dialog = screen.getByRole("dialog");
  fireEvent.submit(dialog.querySelector("form")!);
  fireEvent.submit(dialog.querySelector("form")!);
  await waitFor(() => expect(saveInsuranceChange).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "编辑林芳的保险计划" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: /编辑林芳的接触计划/ }),
  ).toBeDisabled();
  expect(
    screen.getByRole("combobox", { name: "林芳的客户意向度" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "编辑王海的保险计划" }),
  ).toBeEnabled();
  expect(screen.getByRole("button", { name: "刷新保险跟踪" })).toBeDisabled();
  await act(async () => resolve());
  expect(screen.queryByText("保存中…")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "编辑林芳的保险计划" }),
  ).toBeEnabled();
});

it("不同客户同时编辑时，一人的失败不会撤回另一人的计划和意向度", async () => {
  let reject!: (error: Error) => void;
  vi.mocked(saveInsuranceChange).mockImplementation((customer) =>
    customer.id === "1"
      ? new Promise((_, no) => {
          reject = no;
        })
      : Promise.resolve(),
  );
  await show();
  fireEvent.click(screen.getByRole("button", { name: "编辑林芳的保险计划" }));
  fireEvent.change(screen.getByLabelText("保险计划"), {
    target: { value: "未保存计划" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await screen.findByText("未保存计划");
  fireEvent.click(screen.getByRole("button", { name: "编辑王海的保险计划" }));
  fireEvent.change(screen.getByLabelText("保险计划"), {
    target: { value: "王海的新计划" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "编辑王海的保险计划" }),
    ).toBeEnabled(),
  );
  await chooseIntention("王海", "低意向");
  await waitFor(() => expect(highCount()).toHaveTextContent("7"));
  await act(async () => reject(new Error("保存失败")));
  expect(screen.getByText("家庭医疗保障")).toBeInTheDocument();
  expect(screen.queryByText("未保存计划")).not.toBeInTheDocument();
  expect(screen.getByText("王海的新计划")).toBeInTheDocument();
  expect(highCount()).toHaveTextContent("7");
}, 10000);

it("新增跟进失败恢复上一条记录，草稿完整保留并可直接重试，重试不覆盖其他字段", async () => {
  let reject!: (error: Error) => void;
  const data = fixture();
  data.customers[0].followUps = [
    {
      id: "follow-1",
      date: "2026-11-03T10:00",
      method: 2,
      content: "上次跟进",
      result: 1,
      skillId: "insurance-skill",
      sceneName: "保险初筛识别",
    },
  ];
  vi.mocked(fetchInsuranceTracking).mockResolvedValue(data);
  vi.mocked(saveInsuranceChange).mockImplementationOnce(
    () =>
      new Promise((_, no) => {
        reject = no;
      }),
  );
  await show();
  fireEvent.click(screen.getByRole("button", { name: "新增林芳的跟进记录" }));
  fireEvent.change(screen.getByLabelText("触达时间"), {
    target: { value: "2026-11-05T14:30" },
  });
  fireEvent.change(screen.getByLabelText("触达方式"), {
    target: { value: "3" },
  });
  fireEvent.change(screen.getByLabelText("触达结果"), {
    target: { value: "0" },
  });
  fireEvent.change(screen.getByLabelText(/沟通记录/), {
    target: { value: "本次跟进" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
  await screen.findByText("本次跟进");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.queryByText("上次跟进")).not.toBeInTheDocument();
  await act(async () => reject(new Error("暂时不可用")));
  expect(screen.getByText("上次跟进")).toBeInTheDocument();
  expect(screen.queryByText("本次跟进")).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "修改林芳的跟进记录后重试" }),
  );
  expect(screen.getByLabelText("触达时间")).toHaveValue("2026-11-05T14:30");
  expect(screen.getByLabelText("触达方式")).toHaveValue("3");
  expect(screen.getByLabelText("触达结果")).toHaveValue("0");
  expect(screen.getByLabelText(/沟通记录/)).toHaveValue("本次跟进");
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  fireEvent.click(screen.getByRole("button", { name: "编辑林芳的保险计划" }));
  fireEvent.change(screen.getByLabelText("保险计划"), {
    target: { value: "已经成功的新保险计划" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "编辑林芳的保险计划" }),
    ).toBeEnabled(),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "重试保存林芳的跟进记录" }),
  );
  await waitFor(() =>
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
  );
  expect(screen.getByText("本次跟进")).toBeInTheDocument();
  expect(screen.getByText("已经成功的新保险计划")).toBeInTheDocument();
  expect(fetchInsuranceTracking).toHaveBeenCalledTimes(1);
  expect(saveInsuranceChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ id: "1" }),
    {
      kind: "followUp",
      requestId: expect.any(String),
      recordId: undefined,
      value: {
        date: "2026-11-05T14:30",
        method: 3,
        result: 0,
        skillId: "insurance-skill",
        sceneName: "保险初筛识别",
        content: "本次跟进",
      },
    },
  );
}, 20000);

it("接触计划失败只恢复该字段，正常编辑按钮也会回填失败草稿", async () => {
  let reject!: (error: Error) => void;
  const data = fixture();
  data.customers[0].contactPlans = [
    {
      id: "contact-1",
      date: "2026-11-03",
      method: 2,
      content: "原接触安排",
    },
  ];
  vi.mocked(fetchInsuranceTracking).mockResolvedValue(data);
  vi.mocked(saveInsuranceChange).mockImplementationOnce(
    () =>
      new Promise((_, no) => {
        reject = no;
      }),
  );
  await show();
  fireEvent.click(screen.getByRole("button", { name: /编辑林芳的接触计划/ }));
  fireEvent.change(screen.getByLabelText("接触日期"), {
    target: { value: "2026-11-06" },
  });
  fireEvent.change(screen.getByLabelText("触达方式"), {
    target: { value: "3" },
  });
  fireEvent.change(screen.getByLabelText("接触安排"), {
    target: { value: "新接触安排" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await screen.findByText("新接触安排");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await act(async () => reject(new Error("暂时不可用")));
  expect(screen.getByText("原接触安排")).toBeInTheDocument();
  expect(screen.getByText("家庭医疗保障")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /编辑林芳的接触计划/ }));
  expect(screen.getByLabelText("接触日期")).toHaveValue("2026-11-06");
  expect(screen.getByLabelText("触达方式")).toHaveValue("3");
  expect(screen.getByLabelText("接触安排")).toHaveValue("新接触安排");
});

it.each([
  { button: "编辑林芳的保险计划", field: "保险计划", kind: "insurancePlan" },
  { button: /编辑林芳的接触计划/, field: "接触安排", kind: "contactPlan" },
  { button: "新增林芳的跟进记录", field: /沟通记录/, kind: "followUp" },
])(
  "$kind 显示实时字数，拒绝超长提交并允许恰好1000字",
  async ({ button, field, kind }) => {
    await show();
    fireEvent.click(screen.getByRole("button", { name: button }));
    const dialog = screen.getByRole("dialog");
    const input = within(dialog).getByLabelText(field);
    expect(input).toHaveAttribute("maxlength", "1000");
    if (kind === "contactPlan")
      fireEvent.change(within(dialog).getByLabelText("接触日期"), {
        target: { value: "2026-11-06" },
      });
    if (kind === "followUp")
      fireEvent.change(within(dialog).getByLabelText("触达时间"), {
        target: { value: "2026-11-05T14:30" },
      });
    // 程序化输入绕过浏览器 maxlength，仍须被提交校验拦截。
    fireEvent.change(input, { target: { value: "保".repeat(1001) } });
    await within(dialog).findByText("1001 / 1000");
    fireEvent.click(
      within(dialog).getByRole("button", {
        name: kind === "followUp" ? "保存记录" : "保存",
      }),
    );
    await within(dialog).findByText("最多只能输入1000字");
    expect(saveInsuranceChange).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    const valid = "保".repeat(1000);
    fireEvent.change(input, { target: { value: valid } });
    await within(dialog).findByText("1000 / 1000");
    expect(within(dialog).getByText("已达1000字上限")).toBeInTheDocument();
    fireEvent.click(
      within(dialog).getByRole("button", {
        name: kind === "followUp" ? "保存记录" : "保存",
      }),
    );
    await waitFor(() => expect(saveInsuranceChange).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(saveInsuranceChange).toHaveBeenCalledWith(
      expect.objectContaining({ id: "1" }),
      kind === "insurancePlan"
        ? { kind, value: valid }
        : expect.objectContaining({
            kind,
            value: expect.objectContaining({ content: valid }),
          }),
    );
  },
  10000,
);

it("历史超长内容不静默截断，必须删减到1000字以内才能提交", async () => {
  const data = fixture();
  const original = "原".repeat(1001);
  data.customers[0].insurancePlan = original;
  vi.mocked(fetchInsuranceTracking).mockResolvedValue(data);
  await show();
  fireEvent.click(screen.getByRole("button", { name: "编辑林芳的保险计划" }));
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByLabelText("保险计划")).toHaveValue(original);
  expect(within(dialog).getByText("1001 / 1000")).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
  await within(dialog).findByText("最多只能输入1000字");
  expect(saveInsuranceChange).not.toHaveBeenCalled();
});

it("取消移除不发请求；确认移除成功前保留客户，成功后移除行和高意向人数", async () => {
  let resolve!: () => void;
  vi.mocked(removeInsuranceTracking).mockImplementation(
    () =>
      new Promise<void>((yes) => {
        resolve = yes;
      }),
  );
  await show();
  fireEvent.click(screen.getByRole("button", { name: "移除王海的跟踪" }));
  let dialog = screen.getByRole("dialog", { name: "移除跟踪" });
  expect(dialog).toHaveTextContent("王海");
  fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
  expect(removeInsuranceTracking).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "移除王海的跟踪" }));
  dialog = screen.getByRole("dialog", { name: "移除跟踪" });
  fireEvent.click(within(dialog).getByRole("button", { name: "确认移除" }));
  fireEvent.click(within(dialog).getByRole("button", { name: "正在移除…" }));
  expect(removeInsuranceTracking).toHaveBeenCalledTimes(1);
  expect(within(dialog).getByRole("button", { name: "取消" })).toBeDisabled();
  expect(screen.getByText("王海")).toBeInTheDocument();
  expect(highCount()).toHaveTextContent("8");
  await act(async () => resolve());
  expect(screen.queryByText("王海")).not.toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(highCount()).toHaveTextContent("7");
  expect(
    screen.getByText(/^跟踪客户/, { selector: "span" }).querySelector("b"),
  ).toHaveTextContent("11");
  expect(screen.getByText("林芳")).toBeInTheDocument();
});

it("移除失败保留客户和人数，可重试；非高意向客户移除不改变高意向人数", async () => {
  vi.mocked(removeInsuranceTracking)
    .mockRejectedValueOnce(new Error("服务异常"))
    .mockResolvedValueOnce(undefined);
  await show();
  fireEvent.click(screen.getByRole("button", { name: "移除林芳的跟踪" }));
  const dialog = screen.getByRole("dialog", { name: "移除跟踪" });
  fireEvent.click(within(dialog).getByRole("button", { name: "确认移除" }));
  await within(dialog).findByRole("alert");
  expect(screen.getByText("林芳")).toBeInTheDocument();
  expect(highCount()).toHaveTextContent("8");
  expect(
    screen.getByText(/^跟踪客户/, { selector: "span" }).querySelector("b"),
  ).toHaveTextContent("12");
  fireEvent.click(within(dialog).getByRole("button", { name: "确认移除" }));
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(screen.queryByText("林芳")).not.toBeInTheDocument();
  expect(highCount()).toHaveTextContent("8");
  const calls = vi.mocked(removeInsuranceTracking).mock.calls;
  expect(calls[0][0]).toEqual(fixture().customers[0]);
  expect(calls[0][1]).toBeInstanceOf(AbortSignal);
});

it("资产和接触计划列头切换升序、降序、默认，切换列时只保留一个排序", async () => {
  const data = fixture();
  data.customers[0].assets = 337.34;
  data.customers[1].assets = "80";
  data.customers[1].contactPlans = [
    { id: "plan-wang", date: "2026-11-06", method: 0, content: "预约王海" },
  ];
  vi.mocked(fetchInsuranceTracking).mockResolvedValue(data);
  await show();
  const names = () =>
    screen
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell")[0].textContent);
  fireEvent.click(screen.getByRole("button", { name: /^资产排序/ }));
  expect(names()).toEqual(["王海", "林芳"]);
  expect(screen.getAllByRole("columnheader")[1]).toHaveAttribute(
    "aria-sort",
    "ascending",
  );
  fireEvent.click(screen.getByRole("button", { name: /^资产排序/ }));
  expect(names()).toEqual(["林芳", "王海"]);
  fireEvent.click(screen.getByRole("button", { name: /^资产排序/ }));
  expect(screen.getAllByRole("columnheader")[1]).toHaveAttribute(
    "aria-sort",
    "none",
  );
  fireEvent.click(screen.getByRole("button", { name: /^接触计划排序/ }));
  expect(names()).toEqual(["林芳", "王海"]);
  fireEvent.click(screen.getByRole("button", { name: /^接触计划排序/ }));
  expect(names()).toEqual(["王海", "林芳"]);
  fireEvent.click(screen.getByRole("button", { name: /^资产排序/ }));
  expect(screen.getAllByRole("columnheader")[3]).toHaveAttribute(
    "aria-sort",
    "none",
  );
});

it("意向度列头可筛选零值并与搜索组合，无匹配显示搜索空态且可清除筛选", async () => {
  const data = fixture();
  data.customers[0].intention = 0;
  vi.mocked(fetchInsuranceTracking).mockResolvedValue(data);
  await show();
  fireEvent.click(screen.getByRole("button", { name: "筛选客户意向度" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "待了解" }));
  expect(screen.getByText("林芳")).toBeInTheDocument();
  expect(screen.queryByText("王海")).not.toBeInTheDocument();
  expect(highCount()).toHaveTextContent("8");
  fireEvent.change(screen.getByLabelText("搜索保险跟踪客户"), {
    target: { value: "王海" },
  });
  expect(
    screen.getByText("未找到匹配的客户，请调整搜索或筛选条件"),
  ).toBeInTheDocument();
  expect(screen.queryByText("暂未添加跟踪客户")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "清除客户意向度筛选" }));
  expect(screen.getByText("王海")).toBeInTheDocument();
});

it("新增保存成功但回查失败不回滚、不提供重复保存，只锁定该客户直到刷新", async () => {
  vi.mocked(saveInsuranceChange).mockRejectedValueOnce(
    new InsuranceSyncError(),
  );
  await show();
  fireEvent.click(screen.getByRole("button", { name: "新增林芳的接触计划" }));
  fireEvent.change(screen.getByLabelText("接触日期"), {
    target: { value: "2026-11-10" },
  });
  fireEvent.change(screen.getByLabelText("接触安排"), {
    target: { value: "已保存的新计划" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await screen.findByText(/保存已成功，但列表刷新失败/);
  expect(screen.getByText("已保存的新计划")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /重试保存/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "新增林芳的接触计划" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "新增王海的接触计划" }),
  ).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "刷新保险跟踪" }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "新增林芳的接触计划" }),
    ).toBeEnabled(),
  );
});

it("新增回查取得全量正式记录后替换临时数组，避免把新增记录重复插入", async () => {
  const records = [
    {
      id: "901",
      date: "2026-11-12",
      method: 0 as const,
      content: "已入库计划",
    },
    ...fixture().customers[0].contactPlans!,
  ];
  vi.mocked(saveInsuranceChange).mockResolvedValueOnce({ records });
  await show();
  fireEvent.click(screen.getByRole("button", { name: "新增林芳的接触计划" }));
  fireEvent.change(screen.getByLabelText("接触日期"), {
    target: { value: "2026-11-12" },
  });
  fireEvent.change(screen.getByLabelText("接触安排"), {
    target: { value: "已入库计划" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "新增林芳的接触计划" }),
    ).toBeEnabled(),
  );
  expect(screen.getAllByText("已入库计划")).toHaveLength(1);
  fireEvent.click(
    screen.getByRole("button", { name: "编辑林芳的接触计划 2026-11-12" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() => expect(saveInsuranceChange).toHaveBeenCalledTimes(2));
  expect(vi.mocked(saveInsuranceChange).mock.calls[1][1]).toMatchObject({
    recordId: "901",
  });
});

it("触达方式展示最新跟进的方式，支持零值筛选、与意向度组合及清除，缺少跟进显示占位", async () => {
  const data = fixture();
  data.customers[0].intention = 0;
  data.customers[0].followUps = [
    {
      id: "latest",
      date: "2026-11-05T10:00",
      content: "最新企微",
      method: 0,
      result: 1,
      skillId: "insurance-skill",
      sceneName: "保险初筛识别",
    },
    {
      id: "older",
      date: "2026-11-04T10:00",
      content: "之前面访",
      method: 3,
      result: 1,
      skillId: "insurance-skill",
      sceneName: "保险初筛识别",
    },
  ];
  vi.mocked(fetchInsuranceTracking).mockResolvedValue(data);
  await show();
  const row = screen.getByText("林芳").closest("tr")!;
  expect(within(row).getAllByRole("cell")[5]).toHaveTextContent("企微");
  expect(
    within(screen.getByText("王海").closest("tr")!).getAllByRole("cell")[5],
  ).toHaveTextContent("—");
  fireEvent.click(screen.getByRole("button", { name: "筛选触达方式" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "企微" }));
  expect(screen.getByText("林芳")).toBeInTheDocument();
  expect(screen.queryByText("王海")).not.toBeInTheDocument();
  expect(highCount()).toHaveTextContent("8");
  fireEvent.click(screen.getByRole("button", { name: "筛选客户意向度" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "高意向" }));
  expect(
    screen.getByText("未找到匹配的客户，请调整搜索或筛选条件"),
  ).toBeInTheDocument();
  expect(screen.queryByText("暂未添加跟踪客户")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "清除客户意向度筛选" }));
  expect(screen.getByText("林芳")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "筛选触达方式" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "面访" }));
  expect(
    screen.getByText("未找到匹配的客户，请调整搜索或筛选条件"),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "清除触达方式筛选" }));
  expect(screen.getByText("王海")).toBeInTheDocument();
});

it("缺失触达方式显示占位且不被企微筛选命中，编辑需补选，新建仍默认企微", async () => {
  const data = fixture();
  data.customers[0].followUps = [
    {
      id: "unknown-method",
      date: "2026-11-05T10:00",
      content: "方式未知的跟进",
      result: 1,
      skillId: "insurance-skill",
      sceneName: "保险初筛识别",
    },
  ];
  vi.mocked(fetchInsuranceTracking).mockResolvedValue(data);
  await show();
  expect(
    within(screen.getByText("林芳").closest("tr")!).getAllByRole("cell")[5],
  ).toHaveTextContent("—");
  fireEvent.click(screen.getByRole("button", { name: "筛选触达方式" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "企微" }));
  expect(screen.queryByText("林芳")).not.toBeInTheDocument();
  expect(
    screen.getByText("未找到匹配的客户，请调整搜索或筛选条件"),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "清除触达方式筛选" }));
  fireEvent.click(
    screen.getByRole("button", { name: "编辑林芳的跟进记录 2026-11-05T10:00" }),
  );
  expect(screen.getByLabelText("触达方式")).toHaveValue("");
  fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
  await screen.findByText("请选择触达方式", {
    selector: ".ant-form-item-explain-error",
  });
  expect(saveInsuranceChange).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("触达方式"), {
    target: { value: "0" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
  await waitFor(() =>
    expect(saveInsuranceChange).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        value: expect.objectContaining({ method: 0 }),
      }),
    ),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "新增林芳的跟进记录" }),
    ).toBeEnabled(),
  );
  expect(
    within(screen.getByText("林芳").closest("tr")!).getAllByRole("cell")[5],
  ).toHaveTextContent("企微");
  fireEvent.click(screen.getByRole("button", { name: "新增林芳的跟进记录" }));
  expect(screen.getByLabelText("触达方式")).toHaveValue("0");
});
