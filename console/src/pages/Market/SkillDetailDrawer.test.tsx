import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SkillDetailDrawer } from "./SkillDetailDrawer";
import type { MarketSkillDetail } from "../../api/modules/market";
import type { DistributionRecord } from "../../api/types";

const mocks = vi.hoisted(() => ({
  readSkillFile: vi.fn(),
  getSkillDistributions: vi.fn(),
  updateSkillCnName: vi.fn(),
  downloadSkill: vi.fn(),
  updateSkillStatisticsConfig: vi.fn(),
}));

vi.mock("../../api/modules/market", async () => {
  const actual = await vi.importActual<typeof import("../../api/modules/market")>(
    "../../api/modules/market",
  );
  return {
    ...actual,
    marketApi: mocks,
  };
});

function buildSkill(overrides: Partial<MarketSkillDetail> = {}): MarketSkillDetail {
  return {
    item_id: "market-item-1",
    skill_id: "skill-001",
    name: "demo_skill",
    skill_name: "demo_skill",
    chinese_name: "旧名称",
    description: "demo",
    version: "1.0.0",
    creator_id: "admin",
    creator_name: "管理员",
    category_id: null,
    bbk_ids: [],
    status: "active",
    created_at: null,
    updated_at: null,
    call_count: 0,
    user_count: 0,
    user_stats: [],
    ...overrides,
  };
}

function buildDistribution(
  overrides: Partial<DistributionRecord> & { target_user_id: string },
): DistributionRecord {
  return {
    target_user_id: overrides.target_user_id,
    target_user_name: overrides.target_user_name ?? overrides.target_user_id,
    target_bbk_id: overrides.target_bbk_id ?? "1001",
    distributed_at: overrides.distributed_at ?? "2026-08-04T00:00:00.000Z",
  };
}

describe("SkillDetailDrawer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.readSkillFile.mockResolvedValue({
      content: "# demo",
      path: "SKILL.md",
      exists: true,
    });
    mocks.getSkillDistributions.mockResolvedValue([
      buildDistribution({ target_user_id: "user-a", target_user_name: "Alice" }),
      buildDistribution({ target_user_id: "user-b", target_user_name: "Bob" }),
    ]);
    mocks.updateSkillCnName.mockResolvedValue({
      success: true,
      market_updated: true,
      synced_users: 2,
      skipped_users: 0,
      errors: [],
    });
    mocks.downloadSkill.mockResolvedValue({
      blob: new Blob(["demo"]),
      filename: "demo.zip",
    });
    mocks.updateSkillStatisticsConfig.mockResolvedValue({
      success: true,
      message: "",
    });
  });

  it("defaults to syncing all distributed users while showing a readonly user list", async () => {
    const onRefresh = vi.fn();

    render(
      <SkillDetailDrawer
        open
        skill={buildSkill()}
        onClose={vi.fn()}
        isManager
        sourceId="source-1"
        onRefresh={onRefresh}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "编辑中文名" }));
    fireEvent.change(screen.getByPlaceholderText("输入中文名称"), {
      target: { value: "新名称" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await screen.findByRole("dialog", { name: "同步设置" });
    expect(screen.queryByText("全选")).not.toBeInTheDocument();
    expect(screen.queryByText("清空")).not.toBeInTheDocument();
    expect(screen.getByText("已分发用户")).toBeInTheDocument();
    expect(screen.getByText("Alice (user-a)")).toBeInTheDocument();
    expect(screen.getByText("Bob (user-b)")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "确认保存" }));

    await waitFor(() => {
      expect(mocks.updateSkillCnName).toHaveBeenCalledWith("source-1", "market-item-1", {
        skill_id: "skill-001",
        chinese_name: "新名称",
        sync_to_users: true,
        target_user_ids: ["user-a", "user-b"],
      });
    });
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});
