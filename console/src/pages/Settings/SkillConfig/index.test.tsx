import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SkillConfigPage from "./index";

const mocks = vi.hoisted(() => ({
  listSkillConfigs: vi.fn(),
  getSkillConfigDetail: vi.fn(),
  createSkillConfig: vi.fn(),
  updateSkillConfig: vi.fn(),
  listActivityClasses: vi.fn(),
  listCronJobs: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
}));

vi.mock("@/api/modules/skillConfig", async () => {
  const actual = await vi.importActual<
    typeof import("@/api/modules/skillConfig")
  >("@/api/modules/skillConfig");
  return {
    ...actual,
    skillConfigApi: {
      listSkillConfigs: mocks.listSkillConfigs,
      getSkillConfigDetail: mocks.getSkillConfigDetail,
      createSkillConfig: mocks.createSkillConfig,
      updateSkillConfig: mocks.updateSkillConfig,
      listActivityClasses: mocks.listActivityClasses,
    },
  };
});

vi.mock("@/api/modules/cronjob", () => ({
  cronJobApi: { listCronJobs: mocks.listCronJobs },
}));

vi.mock("@/hooks/useAppMessage", () => {
  const message = {
    success: mocks.success,
    error: mocks.error,
    warning: mocks.warning,
  };
  return { useAppMessage: () => ({ message }) };
});

describe("SkillConfigPage", () => {
  afterEach(cleanup);

  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.listCronJobs.mockResolvedValue([]);
    mocks.listActivityClasses.mockResolvedValue([]);
  });

  it("centers the create action when no SKILL exists and reveals the workspace", async () => {
    mocks.listSkillConfigs.mockResolvedValue([]);
    render(<SkillConfigPage />);

    const createButton = await screen.findByRole("button", {
      name: "新增 SKILL",
    });
    fireEvent.click(createButton);

    expect(
      await screen.findByRole("heading", { name: "SKILL 触发规则" }),
    ).toBeTruthy();
    expect(screen.getByRole("heading", { name: "回检" })).toBeTruthy();
    expect(screen.getAllByText("--").length).toBeGreaterThan(5);
    expect(screen.getByText("暂无 SKILL 数据")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /新\s*增/ })).toBeNull();
    expect(screen.getByText("创建模式")).toBeTruthy();
    expect(screen.getByText("请选择SKILL名称（定时任务）")).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "SKILL ID" })).toBeDisabled();
    const sortInput = screen.getByRole("spinbutton", { name: "排序" });
    expect(sortInput).toHaveValue("1");
    fireEvent.keyDown(sortInput, { key: "ArrowDown" });
    expect(sortInput).toHaveValue("1");
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "SKILL名称" })).toHaveFocus(),
    );
  });

  it("loads details and exposes save only after clicking the edit icon", async () => {
    const item = {
      skillId: "job-1",
      name: "存款到期续接",
      sort: 1,
      businessCenterEnabled: true,
      customerInsightEnabled: false,
      outboundCallEnabled: false,
      enabled: true,
      source: { skillId: "job-1", name: "存款到期续接" },
    };
    mocks.listSkillConfigs.mockResolvedValue([item]);
    mocks.getSkillConfigDetail.mockResolvedValue(item);
    mocks.listCronJobs.mockResolvedValue([
      { id: "job-1", name: "存款到期续接" },
    ]);

    render(<SkillConfigPage />);
    await waitFor(() =>
      expect(mocks.getSkillConfigDetail).toHaveBeenCalledWith("job-1", ""),
    );
    expect(screen.getByText("查看模式")).toBeTruthy();
    expect(screen.getByText(/点击左侧 SKILL 的编辑图标后可修改/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /保\s*存/ })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "编辑 存款到期续接" }));

    expect(await screen.findByRole("button", { name: /保\s*存/ })).toBeTruthy();
    expect(screen.getByText("编辑模式")).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "SKILL名称" })).toBeDisabled();
    expect(screen.getByText(/SKILL名称不可修改/)).toBeTruthy();
  });

  it("shows an explicit retry state when the SKILL list fails to load", async () => {
    mocks.listSkillConfigs
      .mockRejectedValueOnce(new Error("网络异常"))
      .mockResolvedValueOnce([]);

    render(<SkillConfigPage />);

    expect(await screen.findByText("SKILL 配置加载失败")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "新增 SKILL" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));

    expect(
      await screen.findByRole("button", { name: "新增 SKILL" }),
    ).toBeTruthy();
    expect(mocks.listSkillConfigs).toHaveBeenCalledTimes(2);
  });

  it("treats a 500 SKILL list response as an empty list", async () => {
    mocks.listSkillConfigs.mockRejectedValue(
      Object.assign(new Error("Request failed: 500 Internal Server Error"), {
        status: 500,
      }),
    );

    render(<SkillConfigPage />);

    expect(
      await screen.findByRole("button", { name: "新增 SKILL" }),
    ).toBeTruthy();
    expect(screen.queryByText("SKILL 配置加载失败")).toBeNull();
    expect(mocks.error).not.toHaveBeenCalled();
  });

  it("exits edit mode when save succeeds even if the list refresh fails", async () => {
    const item = {
      skillId: "job-1",
      name: "存款到期续接",
      sort: 1,
      businessCenterEnabled: true,
      customerInsightEnabled: false,
      outboundCallEnabled: false,
      enabled: true,
      source: { skillId: "job-1", name: "存款到期续接" },
    };
    mocks.listSkillConfigs
      .mockResolvedValueOnce([item])
      .mockRejectedValueOnce(new Error("刷新失败"));
    mocks.getSkillConfigDetail.mockResolvedValue(item);
    mocks.listCronJobs.mockResolvedValue([
      { id: "job-1", name: "存款到期续接" },
    ]);
    mocks.updateSkillConfig.mockResolvedValue({});

    render(<SkillConfigPage />);
    await waitFor(() =>
      expect(mocks.getSkillConfigDetail).toHaveBeenCalledWith("job-1", ""),
    );
    fireEvent.click(screen.getByRole("button", { name: "编辑 存款到期续接" }));
    fireEvent.click(await screen.findByRole("button", { name: /保\s*存/ }));

    await waitFor(() => expect(mocks.updateSkillConfig).toHaveBeenCalled());
    await waitFor(() => expect(mocks.warning).toHaveBeenCalled());
    expect(mocks.success).toHaveBeenCalledWith("SKILL 触发规则更新成功");
    expect(screen.queryByRole("button", { name: /保\s*存/ })).toBeNull();
  });
});
