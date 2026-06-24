import { Tag, Tooltip } from "antd";
import {
  Clock3,
  ChevronDown,
  ChevronUp,
  Database,
  Download,
  Layers3,
  MessageSquareText,
  Upload,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  MCPToolUsage,
  ModelUsage,
  SessionResourceFilter,
  SessionStats,
  SkillUsage,
  UserStats,
} from "../../../../../api/modules/tracing";
import styles from "./index.module.less";

const COLLAPSED_USAGE_ITEM_THRESHOLD = 4;

interface UserStatsHeaderProps {
  userStats: UserStats;
  sessionStats?: SessionStats | null;
  collapsed?: boolean;
  activeResourceFilter?: SessionResourceFilter | null;
  onResourceFilterChange?: (filter: SessionResourceFilter) => void;
  onToggleCollapsed?: () => void;
}

interface UsageItem {
  name: string;
  count: number;
  error_count?: number;
  filter: SessionResourceFilter;
}

function isSameResourceFilter(
  current: SessionResourceFilter | null | undefined,
  candidate: SessionResourceFilter,
): boolean {
  if (!current || current.type !== candidate.type || current.name !== candidate.name) {
    return false;
  }
  return (
    current.type !== "mcp_tool" ||
    candidate.type !== "mcp_tool" ||
    current.mcp_server === candidate.mcp_server
  );
}

function getActiveUsageStats(
  sessionStats: SessionStats | null | undefined,
  userStats: UserStats,
): {
  model_usage: ModelUsage[];
  mcp_tools_used: MCPToolUsage[];
  skills_used: SkillUsage[];
} {
  const active = sessionStats || userStats;
  return {
    model_usage: active.model_usage || [],
    mcp_tools_used: active.mcp_tools_used || [],
    skills_used: active.skills_used || [],
  };
}

function formatTokens(tokens: number): string {
  if (!tokens) return "0";
  if (tokens < 1000) return tokens.toString();
  if (tokens < 1000000) return `${(tokens / 1000).toFixed(1)}K`;
  return `${(tokens / 1000000).toFixed(2)}M`;
}

function formatDuration(ms: number): string {
  if (!ms) return "-";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value || 0);
}

function UsageBlock({
  title,
  items,
  colorFn,
  activeResourceFilter,
  onResourceFilterChange,
}: {
  title: string;
  items: UsageItem[];
  colorFn?: (item: UsageItem) => string;
  activeResourceFilter?: SessionResourceFilter | null;
  onResourceFilterChange?: (filter: SessionResourceFilter) => void;
}) {
  const tagRowRef = useRef<HTMLDivElement | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [heightOverflow, setHeightOverflow] = useState(false);

  const orderedItems = useMemo(() => {
    if (expanded) return items;

    const selectedIndex = items.findIndex((item) =>
      isSameResourceFilter(activeResourceFilter, item.filter),
    );
    if (selectedIndex <= 0) return items;

    const selectedItem = items[selectedIndex];
    return [
      selectedItem,
      ...items.slice(0, selectedIndex),
      ...items.slice(selectedIndex + 1),
    ];
  }, [activeResourceFilter, expanded, items]);

  const canExpand =
    items.length > COLLAPSED_USAGE_ITEM_THRESHOLD || heightOverflow;

  useEffect(() => {
    setExpanded(false);
  }, [items]);

  useEffect(() => {
    const node = tagRowRef.current;
    if (!node) return;

    const measureOverflow = () => {
      setHeightOverflow(node.scrollHeight > node.clientHeight + 1);
    };

    measureOverflow();
    if (typeof ResizeObserver === "undefined") return;
    const resizeObserver = new ResizeObserver(measureOverflow);
    resizeObserver.observe(node);
    return () => resizeObserver.disconnect();
  }, [orderedItems, expanded]);

  return (
    <div className={styles.usageBlock}>
      <div className={styles.usageBlockHeader}>
        <span>{title}</span>
        <div className={styles.usageBlockHeaderMeta}>
          <strong>{formatNumber(items.length)}</strong>
          {canExpand ? (
            <button
              type="button"
              className={styles.usageExpandButton}
              aria-label={`${expanded ? "收起" : "展开"}${title}标签`}
              aria-expanded={expanded}
              onClick={() => setExpanded((current) => !current)}
            >
              {expanded ? "收起" : "展开"}
              {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
          ) : null}
        </div>
      </div>
      <div
        className={`${styles.compactTagRow} ${
          canExpand && !expanded ? styles.compactTagRowCollapsed : ""
        }`}
        ref={tagRowRef}
      >
        {items.length > 0 ? (
          orderedItems.map((item) => {
            const selected = isSameResourceFilter(
              activeResourceFilter,
              item.filter,
            );
            return (
              <button
                type="button"
                key={`${item.filter.type}-${item.name}`}
                className={`${styles.usageTagButton} ${
                  selected ? styles.usageTagButtonSelected : ""
                }`}
                aria-label={`${selected ? "取消" : "筛选"}${title}：${item.name}`}
                aria-pressed={selected}
                onClick={() => onResourceFilterChange?.(item.filter)}
              >
                <Tag
                  color={colorFn ? colorFn(item) : "default"}
                  className={styles.usageTag}
                >
                  {item.name} · {item.count}
                </Tag>
              </button>
            );
          })
        ) : (
          <span className={styles.emptyUsageText}>暂无记录</span>
        )}
      </div>
    </div>
  );
}

export default function UserStatsHeader({
  userStats,
  sessionStats,
  collapsed = false,
  activeResourceFilter,
  onResourceFilterChange,
  onToggleCollapsed,
}: UserStatsHeaderProps) {
  const { t } = useTranslation();
  const isSessionSelected = Boolean(sessionStats);
  const activeUsageStats = getActiveUsageStats(sessionStats, userStats);

  const modelItems = useMemo(
    () =>
      activeUsageStats.model_usage.map((model) => ({
        name: model.model_name,
        count: model.count,
        filter: { type: "model" as const, name: model.model_name },
      })),
    [activeUsageStats.model_usage],
  );

  const mcpToolItems = useMemo(
    () =>
      activeUsageStats.mcp_tools_used.map((tool) => ({
        name: `${tool.tool_name} (${tool.mcp_server})`,
        count: tool.count,
        error_count: tool.error_count,
        filter: {
          type: "mcp_tool" as const,
          name: tool.tool_name,
          mcp_server: tool.mcp_server,
        },
      })),
    [activeUsageStats.mcp_tools_used],
  );

  const skillItems = useMemo(
    () =>
      activeUsageStats.skills_used.map((skill) => ({
        name: skill.skill_name,
        count: skill.count,
        filter: { type: "skill" as const, name: skill.skill_name },
      })),
    [activeUsageStats.skills_used],
  );

  const kpis = [
    {
      label: t("analytics.totalSessions", "总会话"),
      value: formatNumber(userStats.total_sessions),
      icon: <Database size={16} />,
      tone: "blue",
    },
    {
      label: t("analytics.conversations", "对话数"),
      value: formatNumber(userStats.total_conversations),
      icon: <MessageSquareText size={16} />,
      tone: "green",
    },
    {
      label: t("analytics.totalTokens", "总 Token"),
      value: formatTokens(userStats.total_tokens),
      icon: <Layers3 size={16} />,
      tone: "violet",
    },
    {
      label: t("analytics.avgDuration", "平均时长"),
      value: formatDuration(userStats.avg_duration_ms),
      icon: <Clock3 size={16} />,
      tone: "amber",
    },
    {
      label: t("analytics.inputTokens", "输入 Token"),
      value: formatTokens(userStats.input_tokens),
      icon: <Upload size={16} />,
      tone: "cyan",
    },
    {
      label: t("analytics.outputTokens", "输出 Token"),
      value: formatTokens(userStats.output_tokens),
      icon: <Download size={16} />,
      tone: "rose",
    },
  ];

  return (
    <section
      className={`${styles.statsHeader} ${
        collapsed ? styles.statsHeaderCollapsed : ""
      }`}
    >
      <div className={styles.statsHeaderTop}>
        <div>
          <div className={styles.statsEyebrow}>
            {isSessionSelected ? "当前会话洞察" : "用户全局洞察"}
          </div>
        </div>
        <div className={styles.statsHeaderActions}>
          <Tag
            color={
              activeResourceFilter
                ? "processing"
                : isSessionSelected
                  ? "processing"
                  : "default"
            }
          >
            {activeResourceFilter
              ? "已筛选会话"
              : isSessionSelected
                ? "已选中会话"
                : "未筛选会话"}
          </Tag>
          <Tooltip title={collapsed ? "展开洞察" : "收起洞察"}>
            <button
              type="button"
              className={styles.statsCollapseButton}
              onClick={onToggleCollapsed}
              aria-label={collapsed ? "展开洞察" : "收起洞察"}
            >
              {collapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
            </button>
          </Tooltip>
        </div>
      </div>

      {!collapsed && (
        <>
          <div className={styles.kpiGrid}>
            {kpis.map((item) => (
              <div className={styles.kpiItem} key={item.label}>
                <div
                  className={`${styles.kpiIcon} ${styles[`tone_${item.tone}`]}`}
                >
                  {item.icon}
                </div>
                <div className={styles.kpiContent}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              </div>
            ))}
          </div>

          <div className={styles.usageSummary}>
            <UsageBlock
              title="模型"
              items={modelItems}
              activeResourceFilter={activeResourceFilter}
              onResourceFilterChange={onResourceFilterChange}
            />
            <UsageBlock
              title="MCP 工具"
              items={mcpToolItems}
              colorFn={(item) =>
                item.error_count && item.error_count > 0 ? "error" : "default"
              }
              activeResourceFilter={activeResourceFilter}
              onResourceFilterChange={onResourceFilterChange}
            />
            <UsageBlock
              title="技能"
              items={skillItems}
              activeResourceFilter={activeResourceFilter}
              onResourceFilterChange={onResourceFilterChange}
            />
          </div>
        </>
      )}
    </section>
  );
}
