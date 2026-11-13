import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import type { CronDispatchWorkersResponse } from "@/api/modules/monitor";
import SharedWorkers from "./SharedWorkers";

afterEach(cleanup);
it.each([true, false])(
  "Worker 调整详情展示样本明细（有明细：%s）",
  (hasBreakdown) => {
    const value = {
      policies: [],
      current_capacity: [],
      capacity_events: [
        {
          id: 1,
          worker_id: "worker-one",
          source_id: "bank",
          provider_id: "provider",
          model_id: "model",
          strategy_id: "adaptive",
          previous_workers: 3,
          effective_workers: 2,
          min_workers: 1,
          baseline_workers: 2,
          max_workers: 5,
          pending_count: 10,
          claimed_count: 1,
          running_count: 2,
          success_count: 8,
          failure_count: 2,
          subtask_success_count: hasBreakdown ? 5 : null,
          subtask_failure_count: hasBreakdown ? 2 : null,
          error_rate: 0.2,
          avg_latency_ms: 1200,
          decision_reason: "错误率升高",
          matched_rule: { threshold: 0.1 },
          created_at: "2026-10-19T12:00:00+08:00",
        },
      ],
    } as unknown as CronDispatchWorkersResponse;
    render(<SharedWorkers value={value} loading={false} />);
    fireEvent.click(screen.getByText("错误率升高"));
    expect(screen.getByText("Worker ID")).toBeInTheDocument();
    expect(screen.getByText("worker-one")).toBeInTheDocument();
    expect(screen.getByText("等待 / 已领取 / 运行")).toBeInTheDocument();
    expect(
      screen.getByText("主任务 成功 / 失败").nextElementSibling,
    ).toHaveTextContent(hasBreakdown ? "3 / 0" : "—");
    expect(
      screen.getByText("子任务 成功 / 失败").nextElementSibling,
    ).toHaveTextContent(hasBreakdown ? "5 / 2" : "—");
    expect(
      screen.getByText("合计 成功 / 失败").nextElementSibling,
    ).toHaveTextContent("8 / 2");
    expect(screen.getByText("失败率")).toBeInTheDocument();
    expect(screen.getByText("20.00%")).toBeInTheDocument();
    expect(screen.getByText("平均耗时")).toBeInTheDocument();
    expect(screen.getByText("1200 ms")).toBeInTheDocument();
    expect(screen.getByText("命中规则")).toBeInTheDocument();
  },
);
