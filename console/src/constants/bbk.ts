export const BBK_ID_MAP = [
  { label: "总行", value: "100" },
  { label: "北京分行", value: "110" },
  { label: "广州分行", value: "120" },
  { label: "上海分行", value: "121" },
  { label: "天津分行", value: "122" },
  { label: "重庆分行", value: "123" },
  { label: "沈阳分行", value: "124" },
  { label: "南京分行", value: "125" },
  { label: "武汉分行", value: "127" },
  { label: "成都分行", value: "128" },
  { label: "西安分行", value: "129" },
  { label: "石家庄分行", value: "311" },
  { label: "唐山分行", value: "315" },
  { label: "太原分行", value: "351" },
  { label: "郑州分行", value: "371" },
  { label: "大连分行", value: "411" },
  { label: "长春分行", value: "431" },
  { label: "哈尔滨分行", value: "451" },
  { label: "呼和浩特分行", value: "471" },
  { label: "无锡分行", value: "510" },
  { label: "苏州分行", value: "512" },
  { label: "南通分行", value: "513" },
  { label: "济南分行", value: "531" },
  { label: "青岛分行", value: "532" },
  { label: "烟台分行", value: "535" },
  { label: "合肥分行", value: "551" },
  { label: "杭州分行", value: "571" },
  { label: "宁波分行", value: "574" },
  { label: "温州分行", value: "577" },
  { label: "福州分行", value: "591" },
  { label: "厦门分行", value: "592" },
  { label: "泉州分行", value: "595" },
  { label: "长沙分行", value: "731" },
  { label: "深圳分行", value: "755" },
  { label: "佛山分行", value: "757" },
  { label: "东莞分行", value: "769" },
  { label: "南宁分行", value: "771" },
  { label: "南昌分行", value: "791" },
  { label: "贵阳分行", value: "851" },
  { label: "昆明分行", value: "871" },
  { label: "海口分行", value: "898" },
  { label: "兰州分行", value: "931" },
  { label: "银川分行", value: "951" },
  { label: "西宁分行", value: "972" },
  { label: "乌鲁木齐分行", value: "991" },
];

// 机构 ID 到名称的映射（用于快速查找显示）
export const BBK_ID_TO_NAME_MAP: Record<string, string> = BBK_ID_MAP.reduce(
  (acc, item) => {
    acc[item.value] = item.label;
    return acc;
  },
  {} as Record<string, string>,
);

/**
 * 获取机构显示名称
 * @param bbkId 机构 ID
 * @returns 机构名称，如果未找到则返回原 bbkId
 */
export function getBbkDisplayName(bbkId?: string): string {
  if (!bbkId) return "-";
  if (bbkId === "other" || bbkId === "unassigned") return "其他";
  return BBK_ID_TO_NAME_MAP[bbkId] || bbkId;
}
