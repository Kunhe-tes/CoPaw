import type {
  SkillExposureStats,
  SkillValueReturnStats,
} from "@/api/modules/skillConfig";

export interface InspectionMetric {
  label: string;
  value: string;
  suffix?: string;
  description: string;
}

export interface InspectionSection {
  title: string;
  description: string;
  metrics: InspectionMetric[];
}

export interface InspectionDepthItem {
  id?: string;
  sequence?: number;
  label: string;
  value: string;
  exposureCount?: number;
  ratePercent?: number;
}

export interface SkillInspectionPlaceholder {
  sections: InspectionSection[];
  depthItems: InspectionDepthItem[];
  depthTotalCount?: number;
}

const DEPTH_ITEM_LABELS = [
  "客户核心信息",
  "到期产品",
  "经营目标与策略",
  "电话邀约话术",
  "常见异议处理",
  "营销小贴士",
];

function formatMetricValue(value: number | undefined): string {
  return Number.isFinite(value) ? String(value) : "--";
}

function formatCountDescription(
  countLabel: string,
  count: number | undefined,
  listCount: number | undefined,
): string {
  if (!Number.isFinite(count) || !Number.isFinite(listCount)) {
    return `${countLabel} / 名单数`;
  }
  return `${countLabel} ${count} / 名单数 ${listCount}`;
}

function parseExposurePercent(value: string): number {
  const parsed = Number.parseFloat(value.replace("%", ""));
  return Number.isFinite(parsed) ? Math.min(100, Math.max(0, parsed)) : 0;
}

function buildInspectionData(
  stats?: SkillValueReturnStats,
  exposureStats?: SkillExposureStats,
): SkillInspectionPlaceholder {
  return {
    sections: [
      {
        title: "查看",
        description: "L1 盘户名单触达",
        metrics: [
          { label: "整体 UV", value: "--", description: "浏览人数" },
          { label: "整体 PV", value: "--", description: "名单页总浏览次数" },
        ],
      },
      {
        title: "采纳",
        description: "名单被采纳、被联系的比例",
        metrics: [
          {
            label: "名单采纳率",
            value: formatMetricValue(stats?.acceptRate),
            suffix: "%",
            description: formatCountDescription(
              "采纳数",
              stats?.acceptCount,
              stats?.listCount,
            ),
          },
          {
            label: "接触率",
            value: formatMetricValue(stats?.contactRate),
            suffix: "%",
            description: formatCountDescription(
              "接触数",
              stats?.contactCount,
              stats?.listCount,
            ),
          },
        ],
      },
      {
        title: "转化",
        description: "客户经营结果",
        metrics: [
          {
            label: "AUM 提升金额",
            value: formatMetricValue(stats?.aumIncrease),
            suffix: "万元",
            description: "接触后客户资产提升总额",
          },
          {
            label: "财富产品购买金额",
            value: formatMetricValue(stats?.wealthProductAmount),
            suffix: "万元",
            description: "接触后客户购买财富产品总额",
          },
        ],
      },
    ],
    depthItems: exposureStats
      ? [...exposureStats.items]
          .sort((left, right) => left.sequence - right.sequence)
          .map((item) => ({
            id: item.targetId,
            sequence: item.sequence,
            label: item.targetName || item.targetId,
            value: item.exposureRate || "--",
            exposureCount: item.exposureCount,
            ratePercent: parseExposurePercent(item.exposureRate),
          }))
      : DEPTH_ITEM_LABELS.map((label) => ({ label, value: "--" })),
    depthTotalCount: exposureStats?.totalCount,
  };
}

export async function getSkillInspectionMock(
  skillId: string,
  stats?: SkillValueReturnStats,
  exposureStats?: SkillExposureStats,
): Promise<SkillInspectionPlaceholder> {
  void skillId;
  return Promise.resolve(buildInspectionData(stats, exposureStats));
}
