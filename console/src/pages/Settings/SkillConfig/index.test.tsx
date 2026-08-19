import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useIframeStore } from "@/stores/iframeStore";
import SkillConfigPage from "./index";

const mocks = vi.hoisted(() => ({
  listSkillConfigs: vi.fn(),
  getSkillConfigDetail: vi.fn(),
  createSkillConfig: vi.fn(),
  updateSkillConfig: vi.fn(),
  listActivityClasses: vi.fn(),
  listSweSkills: vi.fn(),
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

vi.mock("@/api/modules/mySkills", () => ({
  mySkillsApi: { listSweSkills: mocks.listSweSkills },
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
  afterEach(() => {
    cleanup();
    useIframeStore.setState({ bbk: null, source: null });
  });

  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.listSweSkills.mockResolvedValue({
      source_id: "RMASSIST",
      count: 0,
      skills: [],
    });
    mocks.listActivityClasses.mockResolvedValue([]);
  });

  it("loads SKILL name options from the market API and prefers cn_name", async () => {
    const createdItem = {
      skillId: "skill-cn",
      bbkId: "571",
      bbkName: "杭州分行",
      name: "存款到期续接",
      sort: 1,
      businessCenterEnabled: false,
      customerInsightEnabled: false,
      outboundCallEnabled: false,
      enabled: true,
      source: { skill_id: "skill-cn", skill_name: "存款到期续接" },
    };
    useIframeStore.setState({ bbk: "571" });
    mocks.listSkillConfigs
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([createdItem]);
    mocks.createSkillConfig.mockResolvedValue(createdItem);
    mocks.getSkillConfigDetail.mockResolvedValue(createdItem);
    mocks.listSweSkills.mockResolvedValue({
      source_id: "RMASSIST",
      count: 2,
      skills: [
        {
          skill_id: "skill-cn",
          skill_name: "deposit_maturity",
          cn_name: "存款到期续接",
        },
        {
          skill_id: "skill-en",
          skill_name: "customer_insight",
          cn_name: null,
        },
      ],
    });

    render(<SkillConfigPage />);
    fireEvent.click(
      await screen.findByRole("button", { name: "新增 SKILL" }),
    );

    expect(mocks.listSweSkills).toHaveBeenCalledWith("RMASSIST");
    const skillSelect = screen.getByRole("combobox", {
      name: /SKILL\s*名称/,
    });
    fireEvent.mouseDown(skillSelect);
    expect(
      await screen.findByRole("option", { name: "存款到期续接" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("option", { name: "customer_insight" }),
    ).toBeTruthy();

    fireEvent.click(
      screen.getByText("存款到期续接", {
        selector: ".ant-select-item-option-content",
      }),
    );
    expect(screen.getByRole("textbox", { name: "SKILL ID" })).toHaveValue(
      "skill-cn",
    );

    fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));
    await waitFor(() =>
      expect(mocks.createSkillConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          skill_id: "skill-cn",
          skill_name: "存款到期续接",
        }),
      ),
    );
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
    expect(screen.getByText("请选择SKILL名称")).toBeTruthy();
    expect(screen.getByRole("button", { name: /保\s*存/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /创\s*建/ })).toBeNull();
    expect(screen.getByRole("textbox", { name: "SKILL ID" })).toBeDisabled();
    const sortInput = screen.getByRole("spinbutton", { name: "排序" });
    expect(sortInput).toHaveValue("1");
    expect(sortInput).toHaveAttribute("aria-valuemax", "9999");
    fireEvent.keyDown(sortInput, { key: "ArrowDown" });
    expect(sortInput).toHaveValue("1");
    await waitFor(() =>
      expect(
        screen.getByRole("combobox", { name: /SKILL\s*名称/ }),
      ).toHaveFocus(),
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
    mocks.listSweSkills.mockResolvedValue({
      source_id: "RMASSIST",
      count: 1,
      skills: [
        {
          skill_id: "job-1",
          skill_name: "deposit_maturity",
          cn_name: "存款到期续接",
        },
      ],
    });

    render(<SkillConfigPage />);
    await waitFor(() =>
      expect(mocks.getSkillConfigDetail).toHaveBeenCalledWith("job-1", ""),
    );
    expect(screen.getByText("查看模式")).toBeTruthy();
    expect(screen.getByText(/点击左侧编辑图标后可修改/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /保\s*存/ })).toBeNull();
    expect(
      screen.getByRole("combobox", { name: /SKILL\s*名称/ }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "刷新 SKILL 列表" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /新\s*增/ }).querySelector("svg"),
    ).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "编辑 存款到期续接" }));

    expect(await screen.findByRole("button", { name: /保\s*存/ })).toBeTruthy();
    expect(screen.getByText("编辑模式")).toBeTruthy();
    expect(
      screen.getByRole("combobox", { name: /SKILL\s*名称/ }),
    ).toBeDisabled();
  });

  it("refreshes the SKILL list and selects the first refreshed item", async () => {
    const firstItem = {
      skillId: "job-1",
      name: "第一条",
      sort: 1,
      businessCenterEnabled: false,
      customerInsightEnabled: false,
      outboundCallEnabled: false,
      enabled: true,
      source: { skillId: "job-1", name: "第一条" },
    };
    const secondItem = {
      ...firstItem,
      skillId: "job-2",
      name: "第二条",
      source: { skillId: "job-2", name: "第二条" },
    };
    const refreshedFirstItem = {
      ...firstItem,
      skillId: "job-3",
      name: "刷新后的第一条",
      source: { skillId: "job-3", name: "刷新后的第一条" },
    };
    mocks.listSkillConfigs
      .mockResolvedValueOnce([firstItem, secondItem])
      .mockResolvedValueOnce([refreshedFirstItem]);
    mocks.getSkillConfigDetail.mockImplementation(async (skillId: string) =>
      [firstItem, secondItem, refreshedFirstItem].find(
        (item) => item.skillId === skillId,
      ),
    );

    render(<SkillConfigPage />);
    await waitFor(() =>
      expect(mocks.getSkillConfigDetail).toHaveBeenCalledWith("job-1", ""),
    );
    fireEvent.click(screen.getByRole("button", { name: "第二条" }));
    await waitFor(() =>
      expect(mocks.getSkillConfigDetail).toHaveBeenCalledWith("job-2", ""),
    );

    fireEvent.click(screen.getByRole("button", { name: "刷新 SKILL 列表" }));

    await waitFor(() =>
      expect(mocks.getSkillConfigDetail).toHaveBeenCalledWith("job-3", ""),
    );
    expect(
      screen.getByRole("button", { name: "刷新后的第一条" }),
    ).toHaveAttribute("aria-current", "page");
  });

  it("exposes a long SKILL list as a keyboard-accessible scroll region", async () => {
    const items = Array.from({ length: 20 }, (_, index) => ({
      skillId: `skill-${index + 1}`,
      name: `SKILL ${index + 1}`,
      sort: index + 1,
      businessCenterEnabled: false,
      customerInsightEnabled: false,
      outboundCallEnabled: false,
      enabled: true,
      source: { skillId: `skill-${index + 1}`, name: `SKILL ${index + 1}` },
    }));
    mocks.listSkillConfigs.mockResolvedValue(items);
    mocks.getSkillConfigDetail.mockResolvedValue(items[0]);

    render(<SkillConfigPage />);

    const listRegion = await screen.findByRole("region", {
      name: "SKILL 列表内容",
    });
    expect(listRegion).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("button", { name: "SKILL 20" })).toBeTruthy();
  });

  it("keeps the SKILL name locked while submitting its fallback name on edit", async () => {
    const currentItem = {
      skillId: "skill-en",
      bbkId: "571",
      bbkName: "杭州分行",
      name: "旧名称",
      sort: 1,
      businessCenterEnabled: false,
      customerInsightEnabled: false,
      outboundCallEnabled: false,
      enabled: true,
      source: { skillId: "job-1", name: "旧名称" },
    };
    const updatedItem = { ...currentItem, name: "customer_insight", sort: 2 };
    mocks.listSkillConfigs
      .mockResolvedValueOnce([currentItem])
      .mockResolvedValueOnce([updatedItem]);
    mocks.getSkillConfigDetail.mockResolvedValue(currentItem);
    mocks.updateSkillConfig.mockResolvedValue(updatedItem);
    mocks.listSweSkills.mockResolvedValue({
      source_id: "RMASSIST",
      count: 1,
      skills: [
        {
          skill_id: "skill-en",
          skill_name: "customer_insight",
          cn_name: null,
        },
      ],
    });

    render(<SkillConfigPage />);
    await waitFor(() =>
      expect(mocks.getSkillConfigDetail).toHaveBeenCalledWith("skill-en", ""),
    );
    fireEvent.click(screen.getByRole("button", { name: "编辑 旧名称" }));
    const skillSelect = await screen.findByRole("combobox", {
      name: /SKILL\s*名称/,
    });
    expect(skillSelect).toBeDisabled();
    fireEvent.change(screen.getByRole("spinbutton", { name: "排序" }), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));

    await waitFor(() =>
      expect(mocks.updateSkillConfig).toHaveBeenCalledWith(
        expect.objectContaining({
          skill_id: "skill-en",
          skill_name: "customer_insight",
        }),
      ),
    );
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
    mocks.listSweSkills.mockResolvedValue({
      source_id: "RMASSIST",
      count: 1,
      skills: [
        {
          skill_id: "job-1",
          skill_name: "deposit_maturity",
          cn_name: "存款到期续接",
        },
      ],
    });
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
