import { useMemo } from "react";
import { Empty } from "antd";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import dayjs from "dayjs";
import type { CronDispatchCapacityItem } from "../../../api/modules/monitor";
import {
  buildWorkerSeries,
  sampledOccupancy,
  type WorkerPoint,
} from "./workerHistory";

export default function WorkerHistoryChart({
  items,
  showOccupancy = false,
}: {
  items: CronDispatchCapacityItem[];
  showOccupancy?: boolean;
}) {
  const series = useMemo(
    () => buildWorkerSeries(items, showOccupancy),
    [items, showOccupancy],
  );
  const option = useMemo<EChartsOption>(
    () => ({
      animation: false,
      aria: {
        enabled: true,
        label: {
          description: showOccupancy
            ? "模型 Worker 调整图，展示有效 Worker 和采样时点的占用 Worker 数量。"
            : `模型 Worker 调整图，共 ${series.length} 个模型、${items.length} 条记录。横轴为调整时间，纵轴为有效 Worker 数量。详细调整原因可在下方记录中查看。`,
        },
      },
      legend: { show: showOccupancy, top: 0 },
      grid: {
        left: 36,
        right: 16,
        top: showOccupancy ? 58 : 36,
        bottom: 72,
        containLabel: true,
      },
      tooltip: {
        trigger: "axis",
        renderMode: "richText",
        confine: true,
        formatter: (params) => {
          const entries = Array.isArray(params) ? params : [params];
          return (showOccupancy ? entries.slice(0, 1) : entries)
            .map((entry) => {
              const point = entry.data as WorkerPoint;
              if (!point?.record) return "";
              const r = point.record;
              if (showOccupancy)
                return `${dayjs(r.created_at).format(
                  "MM-DD HH:mm:ss",
                )}\n有效 Worker：${r.effective_workers}\n占用 Worker：${
                  sampledOccupancy(r) ?? "无采样"
                }\n${r.decision_reason || "未记录原因"}`;
              return `${dayjs(r.created_at).format("MM-DD HH:mm:ss")}\n${
                entry.seriesName
              }\nWorker ${r.previous_workers} → ${r.effective_workers}\n${
                r.decision_reason || "未记录原因"
              }`;
            })
            .join("\n\n");
        },
      },
      xAxis: {
        type: "time",
        axisLabel: { hideOverlap: true },
        name: "调整时间",
        nameLocation: "middle",
        nameGap: 30,
      },
      yAxis: {
        type: "value",
        min: 0,
        minInterval: 1,
        name: showOccupancy ? "Worker 数量" : "有效 Worker",
      },
      dataZoom: [
        { type: "inside", filterMode: "none" },
        { type: "slider", bottom: 8, height: 22, filterMode: "none" },
      ],
      series,
    }),
    [series, items.length, showOccupancy],
  );
  return (
    <section aria-label="模型 Worker 调整折线图">
      {series.length ? (
        <ReactECharts
          option={option}
          notMerge
          style={{ height: 320, width: "100%" }}
        />
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="当前时间范围内暂无可绘制的调整记录"
        />
      )}
    </section>
  );
}
