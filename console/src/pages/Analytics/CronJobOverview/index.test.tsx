import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import CronJobOverviewPage from "./index";
import styles from "./index.module.less";

const monitorApiMock = vi.hoisted(() => ({
  getCronJobOverviewPageData: vi.fn(),
  getCronBranchTaskBehavior: vi.fn(),
  getBranchSkills: vi.fn(),
  getBranchSkillManagers: vi.fn(),
  getBranchSkillManagerCustomers: vi.fn(),
  getBranchManagerSummary: vi.fn(),
  getManagerSkills: vi.fn(),
  getManagerCustomers: vi.fn(),
  getExecutions: vi.fn(),
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

describe("CronJobOverview summary cards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    monitorApiMock.getCronJobOverviewPageData.mockResolvedValue({
      summaryMetrics: [
        { key: "branches", value: "12" },
        { key: "managers", value: "86" },
        {
          key: "tasks",
          value: "320",
          hintValue: "新增 12 个",
          footerValue: "2,480 次",
        },
        { key: "success", value: "93.20", footerValue: "2,112/154" },
        { key: "read", value: "61.50", footerValue: "1,525" },
        { key: "report", value: "34.80" },
        { key: "report_count", value: "863" },
        { key: "insight_count", value: "512" },
        { key: "phone_count", value: "221" },
      ],
      branchRankingRows: [],
      failureReasons: [],
      anomalySummary: {
        affectedBranches: "0",
        affectedBranchesUnit: "家",
        affectedManagers: "0",
        affectedManagersUnit: "人",
      },
      anomalyRankRows: [],
    });
    monitorApiMock.getCronBranchTaskBehavior.mockResolvedValue({
      start_date: "2026-06-30",
      end_date: "2026-06-30",
      items: [],
    });
    monitorApiMock.getBranchSkills.mockResolvedValue({
      start_date: "2026-06-30",
      end_date: "2026-06-30",
      bbk_id: "100",
      bbk_name: "测试分行",
      items: [],
    });
    monitorApiMock.getBranchSkillManagers.mockResolvedValue({
      start_date: "2026-06-30",
      end_date: "2026-06-30",
      bbk_id: "100",
      skill_name: "skill",
      items: [],
    });
    monitorApiMock.getBranchSkillManagerCustomers.mockResolvedValue({
      start_date: "2026-06-30",
      end_date: "2026-06-30",
      bbk_id: "100",
      skill_name: "skill",
      user_id: "u1",
      items: [],
    });
    monitorApiMock.getBranchManagerSummary.mockResolvedValue({
      start_date: "2026-06-30",
      end_date: "2026-06-30",
      bbk_id: "100",
      bbk_name: "测试分行",
      items: [],
    });
    monitorApiMock.getManagerSkills.mockResolvedValue({
      start_date: "2026-06-30",
      end_date: "2026-06-30",
      bbk_id: "100",
      user_id: "u1",
      user_name: "张三",
      items: [],
    });
    monitorApiMock.getManagerCustomers.mockResolvedValue({
      start_date: "2026-06-30",
      end_date: "2026-06-30",
      bbk_id: "100",
      user_id: "u1",
      user_name: "张三",
      items: [],
    });
    monitorApiMock.getExecutions.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 100,
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the report metric card with footer metrics and no sub-icons", async () => {
    render(
      <MemoryRouter initialEntries={["/analytics/cron-job-overview"]}>
        <Routes>
          <Route
            path="/analytics/cron-job-overview"
            element={<CronJobOverviewPage />}
          />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(monitorApiMock.getCronJobOverviewPageData).toHaveBeenCalledTimes(
        1,
      );
    });

    const reportTitle = await screen.findByText("查看方案任务率");
    const reportCard = reportTitle.closest("article");
    expect(reportCard).not.toBeNull();
    expect(reportCard?.querySelectorAll("svg")).toHaveLength(1);
    expect(screen.getByText("查看方案任务数")).toBeInTheDocument();
    expect(screen.getByText("去洞察任务数")).toBeInTheDocument();
    expect(screen.getByText("去电访任务数")).toBeInTheDocument();
    expect(screen.getByText("863")).toBeInTheDocument();
    expect(screen.getByText("512")).toBeInTheDocument();
    expect(screen.getByText("221")).toBeInTheDocument();
    expect(screen.getByLabelText("概览指标").className).toContain(
      styles.summaryGrid,
    );
  });

  it("renders expanded manager detail without extra drill-down scroll wrapper", async () => {
    monitorApiMock.getCronJobOverviewPageData.mockResolvedValueOnce({
      summaryMetrics: [
        { key: "branches", value: "12" },
        { key: "managers", value: "86" },
        {
          key: "tasks",
          value: "320",
          hintValue: "新增 12 个",
          footerValue: "2,480 次",
        },
        { key: "success", value: "93.20", footerValue: "2,112/154" },
        { key: "read", value: "61.50", footerValue: "1,525" },
        { key: "report", value: "34.80" },
        { key: "report_count", value: "863" },
        { key: "insight_count", value: "512" },
        { key: "phone_count", value: "221" },
      ],
      branchRankingRows: [
        {
          rank: 1,
          branchName: "测试分行",
          bbkId: "100",
          skillCount: 3,
          totalTasks: 20,
          successCount: 18,
          readTasks: 11,
          involvedManagers: 5,
          resultViewManagers: 4,
          planManagers: 3,
          insightManagers: 2,
          phoneManagers: 1,
          recommendedCustomers: 30,
          viewedCustomers: 12,
          insightCustomers: 5,
          phoneCustomers: 2,
        },
      ],
      failureReasons: [],
      anomalySummary: {
        affectedBranches: "0",
        affectedBranchesUnit: "家",
        affectedManagers: "0",
        affectedManagersUnit: "人",
      },
      anomalyRankRows: [],
    });
    monitorApiMock.getBranchManagerSummary.mockResolvedValueOnce({
      start_date: "2026-06-30",
      end_date: "2026-06-30",
      bbk_id: "100",
      bbk_name: "测试分行",
      items: [
        {
          user_id: "u1",
          user_name: "张三",
          skill_count: 2,
          total_tasks: 10,
          success_count: 9,
          read_tasks: 6,
          result_view_customers: 4,
          plan_customers: 3,
          insight_customers: 2,
          phone_customers: 1,
        },
      ],
    });

    const { container } = render(
      <MemoryRouter initialEntries={["/analytics/cron-job-overview"]}>
        <Routes>
          <Route
            path="/analytics/cron-job-overview"
            element={<CronJobOverviewPage />}
          />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByText("测试分行"));

    await waitFor(() => {
      expect(monitorApiMock.getBranchManagerSummary).toHaveBeenCalledTimes(1);
    });

    expect(
      await screen.findByText("当前分行下的客户经理明细"),
    ).toBeInTheDocument();
    expect(
      container.querySelector(`.${styles.drillDownTableScroll}`),
    ).toBeNull();
  });
});
