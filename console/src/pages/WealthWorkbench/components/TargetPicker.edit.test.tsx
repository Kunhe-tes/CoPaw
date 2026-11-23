import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { request } from "../../../api/request";
import { useIframeStore } from "../../../stores/iframeStore";
import { fetchBootstrap } from "../api";
import { useWealthStore } from "../store";
import { resetInstitutionCache } from "../distribution/institutionCache";
import { TargetPicker } from "./TargetPicker";

vi.mock("../../../api/request", () => ({ request: vi.fn() }));
const mockRequest = vi.mocked(request);
const planView = {
  id: "edit-plan",
  name: "待修改规划",
  publishStatus: "published",
  boardStatus: "已自动下发",
  editable: true,
  scenes: [],
  targets: [
    { sapId: "0001", name: "张三" },
    { sapId: "0002", name: "李四" },
  ],
};

beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  mockRequest.mockReset();
  resetInstitutionCache();
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async (path: string, options?: RequestInit) =>
        new Response(
          JSON.stringify(await mockRequest(path.split("?")[0], options)),
        ),
    ),
  );
  useIframeStore.getState().setContext({
    bbk: "110",
    orgCode: "755480",
    orgLvl: "70",
    sysId: "retail",
  });
  useWealthStore.setState({
    accountId: "middle",
    plans: [],
    targets: [],
    targetSapIds: [],
    targetsLoaded: false,
    targetBranch: null,
    branchTargetSapIds: [],
    editingId: null,
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function openEditPlan() {
  mockRequest.mockResolvedValueOnce({
    code: "200",
    data: { items: [planView] },
  });
  const { plans } = await fetchBootstrap("middle");
  useWealthStore.setState({ plans });
  useWealthStore.getState().editPlan("edit-plan");
}

describe("修改规划分发人员回显", () => {
  it("机构查询保留历史人员，从未匹配汇总移除时不受当前支行影响", async () => {
    await openEditPlan();
    mockRequest.mockResolvedValueOnce({
      code: "200",
      message: "ok",
      success: true,
      data: {
        mOrgCode: "110",
        mOrgName: "北京分行",
        mOrgLvl: 30,
        children: [{ mOrgCode: "b", mOrgName: "南山支行", mOrgLvl: 70 }],
      },
    });
    mockRequest.mockResolvedValueOnce({
      code: "200",
      data: [{ sapID: "0003", userName: "王五" }],
    });
    render(<TargetPicker />);
    expect(
      await screen.findByRole("button", { name: "移除张三" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "移除李四" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("未匹配机构")).toBeInTheDocument(),
    );
    expect(useWealthStore.getState().targetSapIds).toEqual(["0001", "0002"]);
    fireEvent.click(screen.getByRole("button", { name: "南山支行" }));
    await screen.findByText(/共 1 人/);
    expect(useWealthStore.getState().targetSapIds).toEqual(["0001", "0002"]);
    fireEvent.click(screen.getByRole("button", { name: "移除张三" }));
    expect(useWealthStore.getState().targetSapIds).toEqual(["0002"]);
    expect(
      screen.queryByText("张三", { exact: false }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "移除李四" })).toBeVisible();
  });

  it("历史人员覆盖分行完整名单时，下级继承全选并可直接取消", async () => {
    await openEditPlan();
    mockRequest
      .mockResolvedValueOnce({
        code: "200",
        data: {
          mOrgCode: "110",
          mOrgName: "北京分行",
          mOrgLvl: 30,
          children: [
            { mOrgCode: "a", mOrgName: "罗湖支行", mOrgLvl: 70 },
            { mOrgCode: "b", mOrgName: "南山支行", mOrgLvl: 70 },
          ],
        },
      })
      .mockResolvedValueOnce({
        code: "200",
        data: [
          { sapID: "0001", userName: "张三" },
          { sapID: "0002", userName: "李四" },
        ],
      })
      .mockResolvedValueOnce({
        code: "200",
        data: [{ sapID: "0001", userName: "张三" }],
      });
    render(<TargetPicker />);

    const branch = await screen.findByRole("checkbox", {
      name: "选择罗湖支行全部人员",
    });
    const sibling = screen.getByRole("checkbox", {
      name: "选择南山支行全部人员",
    });
    expect(branch).not.toBeChecked();
    expect(sibling).not.toBeChecked();
    expect(mockRequest).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole("button", { name: "北京分行" }));
    await screen.findByText(/共 2 人/);
    const root = screen.getByRole("checkbox", { name: "选择北京分行全部人员" });
    expect(root).toBeChecked();
    expect(branch).toBeChecked();
    expect(sibling).toBeChecked();
    expect(mockRequest).toHaveBeenCalledTimes(3);

    fireEvent.click(branch);
    expect(root).toBePartiallyChecked();
    expect(branch).not.toBeChecked();
    expect(sibling).toBeChecked();
    await waitFor(() =>
      expect(useWealthStore.getState().targetSapIds).toEqual(["0002"]),
    );
    expect(root).toBePartiallyChecked();
    expect(sibling).toBeChecked();
    expect(
      JSON.parse(mockRequest.mock.calls[3][1]!.body as string).orgList,
    ).toEqual([{ bbkOrgId: "110", mmOrgCode: "a", mmOrgLvl: 70 }]);
    expect(mockRequest).toHaveBeenCalledTimes(4);
  });

  it("行长加载当前人员后保留其他已保存人员及姓名", async () => {
    await openEditPlan();
    useWealthStore.setState({ accountId: "president" });
    mockRequest.mockResolvedValueOnce({
      code: "200",
      message: "ok",
      success: true,
      data: [
        {
          sapID: "0001",
          userName: "张三新姓名",
          branchName: "某分行",
          subBranchName: null,
        },
      ],
    });
    render(<TargetPicker />);
    await screen.findByRole("button", { name: "移除张三新姓名" });
    expect(
      screen.getByRole("button", { name: "移除李四" }),
    ).toBeInTheDocument();
    expect(useWealthStore.getState().targetSapIds).toEqual(["0001", "0002"]);
  });

  it("无姓名的历史目标用 ID 回显，并清除上一份计划的人员缓存", async () => {
    await openEditPlan();
    useWealthStore.setState({
      plans: [
        {
          ...useWealthStore.getState().plans[0],
          id: "old-plan",
          targetSapIds: ["0003"],
          targets: undefined,
        },
      ],
    });
    useWealthStore.getState().editPlan("old-plan");
    mockRequest.mockResolvedValueOnce({
      code: "200",
      message: "ok",
      success: true,
      data: {
        mOrgCode: "110",
        mOrgName: "北京分行",
        mOrgLvl: 30,
        children: [],
      },
    });
    render(<TargetPicker />);
    expect(
      await screen.findByRole("button", { name: "移除0003" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "移除张三" }),
    ).not.toBeInTheDocument();
  });
});
