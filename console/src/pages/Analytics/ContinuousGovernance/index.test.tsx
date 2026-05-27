import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ContinuousGovernancePage from "./index";

const mocks = vi.hoisted(() => ({
  dreamLogsApi: {
    report: vi.fn(),
    reportUserRecords: vi.fn(),
  },
}));

vi.mock("../../../api/modules/dreamLogs", () => ({
  dreamLogsApi: mocks.dreamLogsApi,
}));

describe("ContinuousGovernancePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.dreamLogsApi.report.mockResolvedValue({
      summary: {
        covered_users: 10,
        governed_users: 7,
        ungoverned_users: 3,
        total_executions: 18,
        success_count: 15,
        failed_count: 3,
        success_rate: 83.33,
        total_files_changed: 44,
        total_size_saved: 2048,
        avg_duration_ms: 3200,
        last_execution: "2026-05-25T09:00:00Z",
      },
      trends: [
        {
          date: "2026-05-24",
          executions: 8,
          success_count: 7,
          failed_count: 1,
          total_size_saved: 1024,
        },
        {
          date: "2026-05-25",
          executions: 10,
          success_count: 8,
          failed_count: 2,
          total_size_saved: 1024,
        },
      ],
      status_distribution: [
        { status: "success", count: 15 },
        { status: "failed", count: 3 },
      ],
      bbk_distribution: [
        {
          bbk_id: "bbk-1",
          user_count: 6,
          governed_users: 5,
          executions: 12,
          success_rate: 90,
        },
      ],
      users: [
        {
          user_id: "alice",
          user_name: "Alice",
          bbk_id: "bbk-1",
          agents: ["default"],
          executions: 4,
          success_rate: 75,
          failed_count: 1,
          total_files_changed: 8,
          total_size_saved: 1024,
          last_execution: "2026-05-25T09:00:00Z",
          latest_error: "model timeout",
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    mocks.dreamLogsApi.reportUserRecords.mockResolvedValue({
      records: [
        {
          id: "record-1",
          timestamp: "2026-05-25T09:00:00Z",
          trigger: "manual",
          status: "failed",
          agent_id: "default",
          files_optimized: ["MEMORY.md"],
          total_size_saved: 0,
          total_files_changed: 0,
          duration_ms: 1200,
          model_used: "gpt-test",
          input_tokens: 10,
          output_tokens: 20,
          summary: "failed",
          error: "model timeout",
        },
      ],
      total: 1,
      page: 1,
      page_size: 10,
    });
  });

  it("shows report KPIs and user rows", async () => {
    render(<ContinuousGovernancePage />);

    expect(await screen.findByText("持续治理分析")).toBeInTheDocument();
    expect(
      screen.getByTestId("governance-kpi-covered_users"),
    ).toHaveTextContent("10");
    expect(screen.getByTestId("governance-kpi-success_rate")).toHaveTextContent(
      "83.33%",
    );
    expect(await screen.findByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("model timeout")).toBeInTheDocument();
  });

  it("loads readonly user governance records in a drawer", async () => {
    render(<ContinuousGovernancePage />);

    await screen.findByText("Alice");
    fireEvent.click(screen.getAllByRole("button", { name: "查看 alice" })[0]);

    await waitFor(() => {
      expect(mocks.dreamLogsApi.reportUserRecords).toHaveBeenCalledWith(
        "alice",
        expect.objectContaining({ page: 1, page_size: 10 }),
      );
    });

    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByText("record-1")).toBeInTheDocument();
    expect(within(drawer).getByText("model timeout")).toBeInTheDocument();
  });
});
