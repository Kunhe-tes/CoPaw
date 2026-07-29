import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  CronScheduleDistributionDetailsResponse,
  CronScheduleDistributionResponse,
} from "../../../../api/modules/monitor";
import CronScheduleDistribution from "./index";

const mocks = vi.hoisted(() => ({
  dispatchAction: vi.fn(),
  getScheduleDistribution: vi.fn(),
  getScheduleDistributionDetails: vi.fn(),
}));

vi.mock("antd", async (importOriginal) => {
  const actual = await importOriginal<typeof import("antd")>();
  const dayjsModule = await import("dayjs");
  return {
    ...actual,
    DatePicker: (props: {
      value?: { format: (pattern: string) => string } | null;
      onChange?: (value: ReturnType<typeof dayjsModule.default> | null) => void;
      status?: "error";
    }) => (
      <input
        data-testid="schedule-date-picker"
        aria-invalid={props.status === "error"}
        value={props.value?.format("YYYY-MM-DD HH:mm") || ""}
        onChange={(event) =>
          props.onChange?.(
            event.currentTarget.value
              ? dayjsModule.default(event.currentTarget.value)
              : null,
          )
        }
      />
    ),
  };
});

vi.mock("../../../../api/modules/monitor", () => ({
  monitorApi: mocks,
}));

vi.mock("echarts-for-react", () => ({
  default: (props: {
    option?: {
      xAxis?: { data?: string[] };
      series?: Array<{ name?: string }>;
      tooltip?: { axisPointer?: { type?: string } };
    };
    onEvents?: {
      click?: (
        params: { componentType: string; dataIndex: number },
        instance: { dispatchAction: typeof mocks.dispatchAction },
      ) => void;
      mouseover?: (
        params: { componentType: string; dataIndex: number },
        instance: { dispatchAction: typeof mocks.dispatchAction },
      ) => void;
      mouseout?: (
        params: { componentType: string; dataIndex: number },
        instance: { dispatchAction: typeof mocks.dispatchAction },
      ) => void;
    };
  }) => (
    <div data-testid="schedule-chart">
      {(props.option?.xAxis?.data || []).map((label, index) => (
        <button
          key={`${label}-${index}`}
          type="button"
          aria-label={`查看图表时段 ${label}`}
          onMouseOver={() =>
            props.onEvents?.mouseover?.(
              {
                componentType: "series",
                dataIndex: index,
              },
              { dispatchAction: mocks.dispatchAction },
            )
          }
          onMouseOut={() =>
            props.onEvents?.mouseout?.(
              {
                componentType: "series",
                dataIndex: index,
              },
              { dispatchAction: mocks.dispatchAction },
            )
          }
          onClick={() =>
            props.onEvents?.click?.(
              {
                componentType: "series",
                dataIndex: index,
              },
              { dispatchAction: mocks.dispatchAction },
            )
          }
        >
          {label}
        </button>
      ))}
      <span data-testid="chart-series">
        {(props.option?.series || []).map((series) => series.name).join(",")}
      </span>
      <span data-testid="chart-axis-pointer">
        {String(props.option?.tooltip?.axisPointer?.type ?? "")}
      </span>
    </div>
  ),
}));

const aggregateResponse: CronScheduleDistributionResponse = {
  start_time: "2026-07-27T02:00:00Z",
  end_time: "2026-07-28T02:00:00Z",
  bucket_minutes: 15,
  calculated_at: "2026-07-27T01:59:00Z",
  definition_revision: "revision-1",
  eligible_job_count: 3,
  text_count: 2,
  agent_count: 3,
  total_count: 5,
  buckets: [
    {
      start_time: "2026-07-27T02:00:00Z",
      end_time: "2026-07-27T02:15:00Z",
      text_count: 2,
      agent_count: 1,
      total_count: 3,
    },
    {
      start_time: "2026-07-27T02:15:00Z",
      end_time: "2026-07-27T02:30:00Z",
      text_count: 0,
      agent_count: 2,
      total_count: 2,
    },
  ],
  diagnostics: {
    invalid_cron_jobs: 0,
    invalid_timezone_jobs: 0,
    unsupported_task_type_jobs: 0,
    invalid_metadata_jobs: 0,
    managed_child_jobs: 0,
  },
};

const detailResponse: CronScheduleDistributionDetailsResponse = {
  start_time: aggregateResponse.buckets[0].start_time,
  end_time: aggregateResponse.buckets[0].end_time,
  task_type: null,
  calculated_at: "2026-07-27T02:00:10Z",
  definition_revision: "revision-1",
  items: [
    {
      scheduled_at: "2026-07-27T02:05:00Z",
      job_id: "job-1",
      job_name: "晨间提醒",
      user_name: "张三",
      user_id: "user-001",
      task_type: "text",
      cron_expr: "5 * * * *",
      timezone: "Asia/Shanghai",
    },
    {
      scheduled_at: "2026-07-27T02:10:00Z",
      job_id: "job-1",
      job_name: "晨间提醒",
      user_name: "张三",
      user_id: "user-001",
      task_type: "text",
      cron_expr: "*/5 * * * *",
      timezone: "Asia/Shanghai",
    },
  ],
  total: 2,
  page: 1,
  page_size: 20,
  diagnostics: aggregateResponse.diagnostics,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolver) => {
    resolve = resolver;
  });
  return { promise, resolve };
}

describe("CronScheduleDistribution", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getScheduleDistribution.mockResolvedValue(aggregateResponse);
    mocks.getScheduleDistributionDetails.mockResolvedValue(detailResponse);
  });

  it("loads a fixed next-24-hour snapshot with a 15-minute bucket", async () => {
    render(<CronScheduleDistribution />);

    await waitFor(() => {
      expect(mocks.getScheduleDistribution).toHaveBeenCalledTimes(1);
    });
    const params = mocks.getScheduleDistribution.mock.calls[0][0];
    expect(params.bucket_minutes).toBe(15);
    expect(
      new Date(params.end_time).getTime() -
        new Date(params.start_time).getTime(),
    ).toBe(24 * 60 * 60 * 1000);

    expect(await screen.findByTestId("schedule-kpi-total")).toHaveTextContent(
      "5",
    );
    expect(screen.getByTestId("schedule-kpi-text")).toHaveTextContent("2");
    expect(screen.getByTestId("schedule-kpi-text")).toHaveTextContent(
      "Text型任务",
    );
    expect(screen.getByTestId("schedule-kpi-agent")).toHaveTextContent("3");
    expect(screen.getByTestId("schedule-kpi-agent")).toHaveTextContent(
      "Agent型任务",
    );
    expect(screen.getByTestId("schedule-kpi-peak")).toHaveTextContent("3");
    expect(screen.getByTestId("chart-series")).toHaveTextContent("Text,Agent");
    expect(screen.getByTestId("chart-axis-pointer")).toHaveTextContent("none");
    expect(
      screen.getByRole("img", { name: /计划触发次数分布，共 5 次/ }),
    ).toBeInTheDocument();
  });

  it("highlights both stacked bars for only the hovered bucket", async () => {
    render(<CronScheduleDistribution />);
    const [firstBucket] = await screen.findAllByRole("button", {
      name: /查看图表时段/,
    });

    fireEvent.mouseOver(firstBucket);

    expect(mocks.dispatchAction).toHaveBeenNthCalledWith(1, {
      type: "downplay",
    });
    expect(mocks.dispatchAction).toHaveBeenNthCalledWith(2, {
      type: "highlight",
      seriesIndex: [0, 1],
      dataIndex: 0,
    });

    fireEvent.mouseOut(firstBucket);

    expect(mocks.dispatchAction).toHaveBeenNthCalledWith(3, {
      type: "downplay",
    });
  });

  it("keeps interval edits as draft until Query is clicked", async () => {
    render(<CronScheduleDistribution />);
    await screen.findByTestId("schedule-kpi-total");

    fireEvent.click(screen.getByText("30 分钟"));
    expect(mocks.getScheduleDistribution).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "查询" }));
    await waitFor(() => {
      expect(mocks.getScheduleDistribution).toHaveBeenCalledTimes(2);
    });
    expect(mocks.getScheduleDistribution.mock.calls[1][0].bucket_minutes).toBe(
      30,
    );
  });

  it.each([
    ["5 分钟", 5],
    ["10 分钟", 10],
    ["15 分钟", 15],
    ["30 分钟", 30],
    ["1 小时", 60],
  ] as const)("maps %s to a %i-minute query", async (label, minutes) => {
    render(<CronScheduleDistribution />);
    await screen.findByTestId("schedule-kpi-total");

    fireEvent.click(screen.getByText(label));
    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    await waitFor(() => {
      expect(mocks.getScheduleDistribution).toHaveBeenCalledTimes(2);
    });
    expect(mocks.getScheduleDistribution.mock.calls[1][0].bucket_minutes).toBe(
      minutes,
    );
  });

  it.each([
    {
      name: "missing datetime",
      start: "",
      end: "2026-07-28 10:00",
      warning: "请选择完整的开始时间和结束时间",
    },
    {
      name: "reversed datetime",
      start: "2026-07-29 10:00",
      end: "2026-07-28 10:00",
      warning: "结束时间必须晚于开始时间",
    },
    {
      name: "range over seven days",
      start: "2026-07-20 10:00",
      end: "2026-07-28 10:01",
      warning: "统计时间范围不能超过 7 天",
    },
  ])(
    "rejects $name without sending a request",
    async ({ start, end, warning }) => {
      render(<CronScheduleDistribution />);
      await screen.findByTestId("schedule-kpi-total");
      const [startInput, endInput] = screen.getAllByTestId(
        "schedule-date-picker",
      );

      fireEvent.change(startInput, { target: { value: start } });
      fireEvent.change(endInput, { target: { value: end } });
      fireEvent.click(screen.getByRole("button", { name: "查询" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(warning);
      expect(mocks.getScheduleDistribution).toHaveBeenCalledTimes(1);
      expect(startInput).toHaveAttribute("aria-invalid", "true");
      expect(endInput).toHaveAttribute("aria-invalid", "true");
    },
  );

  it("opens occurrence details from a chart bucket without deduplicating jobs", async () => {
    render(<CronScheduleDistribution />);

    fireEvent.click(
      (
        await screen.findAllByRole("button", {
          name: /查看图表时段/,
        })
      )[0],
    );

    await waitFor(() => {
      expect(mocks.getScheduleDistributionDetails).toHaveBeenCalledWith({
        start_time: aggregateResponse.buckets[0].start_time,
        end_time: aggregateResponse.buckets[0].end_time,
        page: 1,
        page_size: 20,
      });
    });
    expect(await screen.findByRole("dialog")).toHaveAccessibleName(
      /计划触发明细/,
    );
    expect(screen.getAllByText("晨间提醒")).toHaveLength(2);
    expect(
      screen.getByRole("columnheader", { name: "用户/账号" }),
    ).toBeVisible();
    expect(screen.getAllByText("张三")).toHaveLength(2);
    expect(screen.getAllByText("user-001")).toHaveLength(2);
  });

  it("does not let an older detail response overwrite a newer bucket", async () => {
    const older = deferred<typeof detailResponse>();
    const newer = deferred<typeof detailResponse>();
    mocks.getScheduleDistributionDetails
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise);

    render(<CronScheduleDistribution />);
    const chartButtons = await screen.findAllByRole("button", {
      name: /查看图表时段/,
    });
    fireEvent.click(chartButtons[0]);
    fireEvent.click(chartButtons[1]);

    newer.resolve({
      ...detailResponse,
      start_time: aggregateResponse.buckets[1].start_time,
      end_time: aggregateResponse.buckets[1].end_time,
      items: [
        {
          ...detailResponse.items[0],
          job_id: "job-new",
          job_name: "最新时段任务",
          task_type: "agent",
        },
      ],
      total: 1,
    });
    expect(await screen.findByText("最新时段任务")).toBeInTheDocument();

    older.resolve(detailResponse);
    await waitFor(() => {
      expect(screen.queryByText("晨间提醒")).not.toBeInTheDocument();
    });
  });

  it("restarts detail pagination after a definition revision conflict", async () => {
    mocks.getScheduleDistributionDetails
      .mockResolvedValueOnce({
        ...detailResponse,
        total: 25,
      })
      .mockRejectedValueOnce(
        Object.assign(new Error("definitions changed"), {
          status: 409,
          data: {
            detail: {
              code: "schedule_definition_revision_conflict",
              message: "definitions changed",
              actual_revision: "revision-2",
            },
          },
        }),
      )
      .mockResolvedValueOnce({
        ...detailResponse,
        definition_revision: "revision-2",
      });

    render(<CronScheduleDistribution />);
    fireEvent.click(
      (
        await screen.findAllByRole("button", {
          name: /查看图表时段/,
        })
      )[0],
    );
    expect(await screen.findAllByText("晨间提醒")).toHaveLength(2);

    fireEvent.click(screen.getByTitle("2"));

    await waitFor(() => {
      expect(mocks.getScheduleDistributionDetails).toHaveBeenNthCalledWith(2, {
        start_time: aggregateResponse.buckets[0].start_time,
        end_time: aggregateResponse.buckets[0].end_time,
        page: 2,
        page_size: 20,
        definition_revision: "revision-1",
      });
    });
    await waitFor(() => {
      expect(mocks.getScheduleDistributionDetails).toHaveBeenLastCalledWith({
        start_time: aggregateResponse.buckets[0].start_time,
        end_time: aggregateResponse.buckets[0].end_time,
        page: 1,
        page_size: 20,
      });
    });
  });

  it("hides old detail rows when a task-type request fails", async () => {
    render(<CronScheduleDistribution />);
    fireEvent.click(
      (
        await screen.findAllByRole("button", {
          name: /查看图表时段/,
        })
      )[0],
    );
    expect(await screen.findAllByText("晨间提醒")).toHaveLength(2);

    mocks.getScheduleDistributionDetails.mockRejectedValueOnce(
      new Error("filter failed"),
    );
    fireEvent.click(screen.getByRole("radio", { name: "Agent" }));

    expect(screen.queryByText("晨间提醒")).not.toBeInTheDocument();
    expect(await screen.findByText("filter failed")).toBeInTheDocument();
    expect(screen.queryByText("晨间提醒")).not.toBeInTheDocument();
  });

  it("hides old detail rows when a pagination request fails", async () => {
    mocks.getScheduleDistributionDetails.mockResolvedValueOnce({
      ...detailResponse,
      total: 25,
    });
    render(<CronScheduleDistribution />);
    fireEvent.click(
      (
        await screen.findAllByRole("button", {
          name: /查看图表时段/,
        })
      )[0],
    );
    expect(await screen.findAllByText("晨间提醒")).toHaveLength(2);

    mocks.getScheduleDistributionDetails.mockRejectedValueOnce(
      new Error("page failed"),
    );
    fireEvent.click(screen.getByTitle("2"));

    expect(screen.queryByText("晨间提醒")).not.toBeInTheDocument();
    expect(await screen.findByText("page failed")).toBeInTheDocument();
    expect(screen.queryByText("晨间提醒")).not.toBeInTheDocument();
  });

  it("shows only the request error when the initial aggregate request fails", async () => {
    mocks.getScheduleDistribution.mockRejectedValueOnce(
      new Error("aggregate failed"),
    );

    render(<CronScheduleDistribution />);

    expect(await screen.findByText("aggregate failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
    expect(screen.queryByTestId("schedule-kpi-total")).not.toBeInTheDocument();
    expect(screen.queryByTestId("schedule-chart")).not.toBeInTheDocument();
  });

  it("keeps the last successful aggregate visible when a later query fails", async () => {
    render(<CronScheduleDistribution />);
    expect(await screen.findByTestId("schedule-kpi-total")).toHaveTextContent(
      "5",
    );

    mocks.getScheduleDistribution.mockRejectedValueOnce(
      new Error("refresh failed"),
    );
    fireEvent.click(screen.getByText("30 分钟"));
    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    expect(await screen.findByText("refresh failed")).toBeInTheDocument();
    expect(screen.getByTestId("schedule-kpi-total")).toHaveTextContent("5");
    expect(screen.getByTestId("schedule-chart")).toBeInTheDocument();
  });

  it("distinguishes empty task definitions from a range with no firings", async () => {
    mocks.getScheduleDistribution.mockResolvedValueOnce({
      ...aggregateResponse,
      eligible_job_count: 0,
      text_count: 0,
      agent_count: 0,
      total_count: 0,
      buckets: aggregateResponse.buckets.map((bucket) => ({
        ...bucket,
        text_count: 0,
        agent_count: 0,
        total_count: 0,
      })),
    });
    const { unmount } = render(<CronScheduleDistribution />);
    expect(
      await screen.findByText("当前没有可统计的定时任务"),
    ).toBeInTheDocument();
    unmount();

    vi.clearAllMocks();
    mocks.getScheduleDistribution.mockResolvedValueOnce({
      ...aggregateResponse,
      eligible_job_count: 3,
      text_count: 0,
      agent_count: 0,
      total_count: 0,
      buckets: aggregateResponse.buckets.map((bucket) => ({
        ...bucket,
        text_count: 0,
        agent_count: 0,
        total_count: 0,
      })),
    });
    render(<CronScheduleDistribution />);

    expect(
      await screen.findByText("所选时间段内没有计划触发"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("schedule-kpi-peak")).toHaveTextContent("-");
    expect(screen.getByTestId("schedule-kpi-peak")).not.toHaveTextContent(
      "07-27",
    );
  });

  it("keeps only the newest aggregate response", async () => {
    render(<CronScheduleDistribution />);
    await screen.findByTestId("schedule-kpi-total");
    const older = deferred<CronScheduleDistributionResponse>();
    const newer = deferred<CronScheduleDistributionResponse>();
    mocks.getScheduleDistribution
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise);

    fireEvent.click(screen.getByText("30 分钟"));
    fireEvent.click(screen.getByRole("button", { name: "查询" }));
    fireEvent.click(screen.getByText("1 小时"));
    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    newer.resolve({
      ...aggregateResponse,
      bucket_minutes: 60,
      text_count: 4,
      agent_count: 5,
      total_count: 9,
    });
    expect(await screen.findByTestId("schedule-kpi-total")).toHaveTextContent(
      "9",
    );

    older.resolve({
      ...aggregateResponse,
      bucket_minutes: 30,
      text_count: 3,
      agent_count: 4,
      total_count: 7,
    });
    await waitFor(() => {
      expect(screen.getByTestId("schedule-kpi-total")).toHaveTextContent("9");
    });
  });

  it("resets detail pagination and maps Agent, Text and All filters", async () => {
    mocks.getScheduleDistributionDetails.mockResolvedValueOnce({
      ...detailResponse,
      total: 25,
    });
    render(<CronScheduleDistribution />);
    fireEvent.click(
      (
        await screen.findAllByRole("button", {
          name: /查看图表时段/,
        })
      )[0],
    );
    expect(await screen.findAllByText("晨间提醒")).toHaveLength(2);

    fireEvent.click(screen.getByTitle("2"));
    await waitFor(() => {
      expect(mocks.getScheduleDistributionDetails).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2 }),
      );
    });

    fireEvent.click(screen.getByRole("radio", { name: "Agent" }));
    await waitFor(() => {
      expect(mocks.getScheduleDistributionDetails).toHaveBeenLastCalledWith({
        start_time: aggregateResponse.buckets[0].start_time,
        end_time: aggregateResponse.buckets[0].end_time,
        task_type: "agent",
        page: 1,
        page_size: 20,
      });
    });

    fireEvent.click(screen.getByRole("radio", { name: "Text" }));
    await waitFor(() => {
      expect(mocks.getScheduleDistributionDetails).toHaveBeenLastCalledWith(
        expect.objectContaining({ task_type: "text", page: 1 }),
      );
    });

    fireEvent.click(screen.getByRole("radio", { name: "全部" }));
    await waitFor(() => {
      expect(mocks.getScheduleDistributionDetails).toHaveBeenLastCalledWith({
        start_time: aggregateResponse.buckets[0].start_time,
        end_time: aggregateResponse.buckets[0].end_time,
        page: 1,
        page_size: 20,
      });
    });
  });

  it("shows only nonzero definition diagnostics", async () => {
    mocks.getScheduleDistribution.mockResolvedValueOnce({
      ...aggregateResponse,
      diagnostics: {
        ...aggregateResponse.diagnostics,
        invalid_cron_jobs: 2,
        invalid_timezone_jobs: 3,
        managed_child_jobs: 1,
      },
    });

    render(<CronScheduleDistribution />);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "时区回退 UTC 3",
    );
    expect(screen.getByRole("status")).toHaveTextContent("批调度托管子任务 1");
    expect(screen.queryByText(/无效 Cron/)).not.toBeInTheDocument();
    expect(screen.queryByText(/不支持的任务类型 0/)).not.toBeInTheDocument();
    expect(screen.queryByText(/元数据异常 0/)).not.toBeInTheDocument();
  });

  it("windows every populated bucket while preserving global ranks and details", async () => {
    const bucketCount = 2016;
    const firstBucketStart = Date.parse("2026-07-27T02:00:00Z");
    const buckets = Array.from({ length: bucketCount }, (_, index) => {
      const permutedCount = ((index * 97) % bucketCount) + 1;
      const totalCount =
        index === 3 || index === 17 ? bucketCount + 1000 : permutedCount;
      return {
        start_time: new Date(
          firstBucketStart + index * 15 * 60 * 1000,
        ).toISOString(),
        end_time: new Date(
          firstBucketStart + (index + 1) * 15 * 60 * 1000,
        ).toISOString(),
        text_count: totalCount,
        agent_count: 0,
        total_count: totalCount,
      };
    });
    const sortedBuckets = [...buckets].sort(
      (left, right) =>
        right.total_count - left.total_count ||
        left.start_time.localeCompare(right.start_time),
    );
    mocks.getScheduleDistribution.mockResolvedValueOnce({
      ...aggregateResponse,
      text_count: buckets.reduce(
        (total, bucket) => total + bucket.total_count,
        0,
      ),
      agent_count: 0,
      total_count: buckets.reduce(
        (total, bucket) => total + bucket.total_count,
        0,
      ),
      buckets,
    });

    render(<CronScheduleDistribution />);

    const rankedList = await screen.findByTestId("schedule-ranked-buckets");
    const virtualContent = rankedList.querySelector('[role="list"]');
    expect(rankedList).toHaveAttribute("aria-label", "全部非空触发区段排名");
    expect(rankedList).toHaveAttribute("tabindex", "0");
    expect(rankedList.style.height).toBe("344px");
    expect(rankedList.style.overflowY).toBe("auto");
    const firstRank = rankedList.querySelector('[aria-posinset="1"]');
    const secondRank = rankedList.querySelector('[aria-posinset="2"]');
    const renderedRowHeight = Number.parseFloat(
      (firstRank as HTMLElement).style.height,
    );
    expect(renderedRowHeight).toBeGreaterThan(0);
    expect(virtualContent).toHaveStyle({
      height: `${bucketCount * renderedRowHeight}px`,
    });
    expect(sortedBuckets[0]).toBe(buckets[3]);
    expect(sortedBuckets[1]).toBe(buckets[17]);
    expect(firstRank).toHaveTextContent("07-27 10:45");
    expect(secondRank).toHaveTextContent("07-27 14:15");
    expect(
      rankedList.querySelectorAll('[role="listitem"]').length,
    ).toBeLessThan(20);

    const targetRank = 1001;
    const targetBucket = sortedBuckets[targetRank - 1];
    expect(targetBucket).not.toBe(buckets[targetRank - 1]);
    rankedList.scrollTop = (targetRank - 1) * renderedRowHeight;
    fireEvent.scroll(rankedList);

    await waitFor(() => {
      expect(
        rankedList.querySelector(`[aria-posinset="${targetRank}"]`),
      ).not.toBeNull();
    });
    expect(rankedList.querySelector('[aria-posinset="1"]')).toBeNull();
    expect(
      rankedList.querySelectorAll('[role="listitem"]').length,
    ).toBeLessThan(20);

    const laterRow = rankedList.querySelector(
      `[aria-posinset="${targetRank}"]`,
    );
    const laterDetailButton = laterRow?.querySelector("button");
    expect(laterDetailButton).not.toBeNull();
    fireEvent.click(laterDetailButton!);

    await waitFor(() => {
      expect(mocks.getScheduleDistributionDetails).toHaveBeenCalledWith({
        start_time: targetBucket.start_time,
        end_time: targetBucket.end_time,
        page: 1,
        page_size: 20,
      });
    });
  });

  it("resets a deeply scrolled ranking before rendering replacement data", async () => {
    const bucketCount = 120;
    const firstBucketStart = Date.parse("2026-07-27T02:00:00Z");
    const buckets = Array.from({ length: bucketCount }, (_, index) => ({
      start_time: new Date(
        firstBucketStart + index * 15 * 60 * 1000,
      ).toISOString(),
      end_time: new Date(
        firstBucketStart + (index + 1) * 15 * 60 * 1000,
      ).toISOString(),
      text_count: bucketCount - index,
      agent_count: 0,
      total_count: bucketCount - index,
    }));
    mocks.getScheduleDistribution.mockResolvedValueOnce({
      ...aggregateResponse,
      text_count: buckets.reduce(
        (total, bucket) => total + bucket.total_count,
        0,
      ),
      agent_count: 0,
      total_count: buckets.reduce(
        (total, bucket) => total + bucket.total_count,
        0,
      ),
      buckets,
    });

    render(<CronScheduleDistribution />);

    const rankedList = await screen.findByTestId("schedule-ranked-buckets");
    const firstRenderedRow = rankedList.querySelector(
      '[role="listitem"]',
    ) as HTMLElement;
    const renderedRowHeight = Number.parseFloat(firstRenderedRow.style.height);
    expect(renderedRowHeight).toBeGreaterThan(0);
    let scrollTop = 0;
    const setSizesWhenReset: Array<string | null> = [];
    Object.defineProperty(rankedList, "scrollTop", {
      configurable: true,
      get: () => scrollTop,
      set: (value: number) => {
        scrollTop = value;
        if (value === 0) {
          setSizesWhenReset.push(
            rankedList
              .querySelector('[role="listitem"]')
              ?.getAttribute("aria-setsize") ?? null,
          );
        }
      },
    });

    rankedList.scrollTop = 80 * renderedRowHeight;
    fireEvent.scroll(rankedList);
    await waitFor(() => {
      expect(rankedList.querySelector('[aria-posinset="81"]')).not.toBeNull();
    });

    mocks.getScheduleDistribution.mockResolvedValueOnce({
      ...aggregateResponse,
      bucket_minutes: 30,
    });
    fireEvent.click(screen.getByText("30 分钟"));
    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    await waitFor(() => {
      expect(
        rankedList.querySelector('[aria-posinset="1"][aria-setsize="2"]'),
      ).not.toBeNull();
    });
    expect(setSizesWhenReset).toEqual([String(bucketCount)]);
    expect(rankedList.scrollTop).toBe(0);
    expect(rankedList.querySelector('[aria-posinset="81"]')).toBeNull();
  });

  it("retries the same aggregate query after a failure", async () => {
    mocks.getScheduleDistribution.mockRejectedValueOnce(
      new Error("aggregate failed"),
    );
    render(<CronScheduleDistribution />);
    const retry = await screen.findByRole("button", { name: "重试" });
    const failedQuery = mocks.getScheduleDistribution.mock.calls[0][0];

    fireEvent.click(retry);

    expect(await screen.findByTestId("schedule-kpi-total")).toHaveTextContent(
      "5",
    );
    expect(mocks.getScheduleDistribution).toHaveBeenNthCalledWith(
      2,
      failedQuery,
    );
  });

  it("retries the same detail query after a failure", async () => {
    mocks.getScheduleDistributionDetails.mockRejectedValueOnce(
      new Error("detail failed"),
    );
    render(<CronScheduleDistribution />);
    fireEvent.click(
      (
        await screen.findAllByRole("button", {
          name: /查看图表时段/,
        })
      )[0],
    );
    const retry = await screen.findByRole("button", { name: "重试" });
    const failedQuery = mocks.getScheduleDistributionDetails.mock.calls[0][0];

    fireEvent.click(retry);

    expect(await screen.findAllByText("晨间提醒")).toHaveLength(2);
    expect(mocks.getScheduleDistributionDetails).toHaveBeenNthCalledWith(
      2,
      failedQuery,
    );
  });

  it("opens details from a focusable ranking button and restores focus", async () => {
    render(<CronScheduleDistribution />);
    const detailButton = await screen.findByRole("button", {
      name: /查看 07-27 10:00.*计划触发明细/,
    });
    detailButton.focus();
    expect(detailButton).toHaveFocus();

    fireEvent.click(detailButton);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    await waitFor(() => {
      expect(detailButton).toHaveFocus();
    });
  });
});
