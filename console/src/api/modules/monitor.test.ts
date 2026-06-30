import { describe, expect, it } from "vitest";
import {
  mapCronJobOverviewPageData,
  type CronBranchErrorResponse,
  type CronBranchRankingResponse,
  type CronOverviewStatsResponse,
} from "./monitor";

describe("mapCronJobOverviewPageData", () => {
  it("maps report rate and report detail counts into summary metrics", () => {
    const stats: CronOverviewStatsResponse = {
      start_date: "2026-06-30",
      end_date: "2026-06-30",
      total_tasks: 320,
      new_cron_tasks: 12,
      total_executions: 2480,
      branch_count: 12,
      tenant_count: 86,
      success_rate: 93.2,
      success_count: 2112,
      running_count: 24,
      read_tasks: 1525,
      read_rate: 61.5,
      error_count: 154,
      error_rate: 6.2,
      report_rate: 34.8,
      report_count: 863,
      insight_count: 512,
      phone_count: 221,
    };
    const ranking: CronBranchRankingResponse = {
      start_date: "2026-06-30",
      end_date: "2026-06-30",
      items: [],
    };
    const branchError: CronBranchErrorResponse = {
      start_date: "2026-06-30",
      end_date: "2026-06-30",
      affected_branch_count: 0,
      affected_manager_count: 0,
      error_reasons: [],
      branch_error_rank: [],
    };

    const result = mapCronJobOverviewPageData(stats, ranking, branchError);

    expect(result.summaryMetrics).toEqual(
      expect.arrayContaining([
        { key: "report", value: "34.80" },
        { key: "report_count", value: "863" },
        { key: "insight_count", value: "512" },
        { key: "phone_count", value: "221" },
      ]),
    );
  });
});
