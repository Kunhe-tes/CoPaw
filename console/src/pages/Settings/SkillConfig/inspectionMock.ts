export interface InspectionMetric {
  label: string;
  value: "--";
  suffix?: string;
  description: string;
}

export interface InspectionSection {
  title: string;
  description: string;
  metrics: InspectionMetric[];
}

export interface InspectionDepthItem {
  label: string;
  value: "--";
}

export interface SkillInspectionPlaceholder {
  sections: InspectionSection[];
  depthItems: InspectionDepthItem[];
}

const PLACEHOLDER_DATA: SkillInspectionPlaceholder = {
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
      description: "名单被点击、被联系的比例",
      metrics: [
        {
          label: "名单采纳率",
          value: "--",
          suffix: "%",
          description: "点击数 / 名单数",
        },
        {
          label: "接触率",
          value: "--",
          suffix: "%",
          description: "接触数 / 名单数",
        },
      ],
    },
    {
      title: "转化",
      description: "客户经营结果",
      metrics: [
        {
          label: "AUM 提升金额",
          value: "--",
          suffix: "万元",
          description: "接触后客户资产提升总额",
        },
        {
          label: "财富产品购买金额",
          value: "--",
          suffix: "万元",
          description: "接触后客户购买财富产品总额",
        },
      ],
    },
  ],
  depthItems: [
    "客户核心信息",
    "到期产品",
    "经营目标与策略",
    "电话邀约话术",
    "常见异议处理",
    "营销小贴士",
  ].map((label) => ({ label, value: "--" })),
};

export async function getSkillInspectionMock(
  skillId: string,
): Promise<SkillInspectionPlaceholder> {
  void skillId;
  return Promise.resolve(PLACEHOLDER_DATA);
}
