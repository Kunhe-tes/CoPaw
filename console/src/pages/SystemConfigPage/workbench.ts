import isEqual from "lodash/isEqual";

import type { SourceSystemConfig } from "@/api/types/sourceSystemConfig";

export type CapabilityId =
  | "conversation"
  | "safety"
  | "model"
  | "cron"
  | "output";

export type CapabilityFilter = "all" | "custom" | "unsaved";
export type CapabilityState = "default" | "custom" | "unsaved";

export interface CapabilitySummary {
  id: CapabilityId;
  title: string;
  description: string;
  state: CapabilityState;
  sourceLabel: string;
  summary: string;
  highImpact?: boolean;
}

interface BuildCapabilitySummariesArgs {
  savedConfig: SourceSystemConfig;
  draftConfig: SourceSystemConfig;
  effectiveConfig: SourceSystemConfig;
}

interface CapabilityDefinition {
  id: CapabilityId;
  title: string;
  description: string;
  paths: readonly (readonly string[])[];
  summary: (config: SourceSystemConfig) => string;
  highImpact?: boolean;
  inheritsAgent?: boolean;
}

const CAPABILITIES: CapabilityDefinition[] = [
  {
    id: "conversation",
    title: "对话与执行",
    description: "任务进度与系统提示词的可见体验。",
    paths: [
      ["feature_switches", "chat_task_progress_enabled"],
      ["feature_switches", "normal_mode_plan_interaction_tools_enabled"],
      ["system_prompt_injections"],
    ],
    summary: (config) => {
      const prompts = Array.isArray(config.system_prompt_injections)
        ? config.system_prompt_injections.length
        : 0;
      return prompts > 0 ? `${prompts} 段提示词` : "任务进度默认开启";
    },
  },
  {
    id: "safety",
    title: "安全与审批",
    description: "数据库访问边界与审批通知。",
    paths: [
      ["feature_switches", "database_access_guard_enabled"],
      ["approval_notifications", "zhaohu_tool_guard_enabled"],
    ],
    summary: () => "数据库防护已配置",
    highImpact: true,
  },
  {
    id: "model",
    title: "模型调用",
    description: "重试策略、并发与限流等待。",
    paths: [["query_retry"], ["llm_rate_limiter"]],
    summary: (config) => {
      const limiter = config.llm_rate_limiter as
        | { llm_max_qpm?: number; llm_max_concurrent?: number }
        | undefined;
      return limiter
        ? `QPM ${limiter.llm_max_qpm ?? "-"} · 并发 ${
            limiter.llm_max_concurrent ?? "-"
          }`
        : "采用运行配置";
    },
    inheritsAgent: true,
  },
  {
    id: "cron",
    title: "定时任务",
    description: "通知、暂停、清理与归档节奏。",
    paths: [
      ["cron_unread_auto_pause"],
      ["cron_notifications"],
      ["cron_task_session_cleanup"],
      ["archive_maintenance"],
    ],
    summary: () => "维护任务按计划运行",
  },
  {
    id: "output",
    title: "工具输出",
    description: "新产生、近期与历史工具输出边界。",
    paths: [["tool_result_compact"]],
    summary: () => "输出控制采用当前策略",
    inheritsAgent: true,
  },
];

function pickConfig(
  config: SourceSystemConfig,
  definition: CapabilityDefinition,
): SourceSystemConfig {
  return definition.paths.reduce<SourceSystemConfig>((result, path) => {
    let source: unknown = config;
    for (const key of path) {
      if (!source || typeof source !== "object" || !(key in source)) {
        return result;
      }
      source = (source as Record<string, unknown>)[key];
    }

    let target: Record<string, unknown> = result;
    path.forEach((key, index) => {
      if (index === path.length - 1) {
        target[key] = source;
        return;
      }
      const nextTarget = target[key];
      if (!nextTarget || typeof nextTarget !== "object") {
        target[key] = {};
      }
      target = target[key] as Record<string, unknown>;
    });
    return result;
  }, {});
}

export function buildCapabilitySummaries({
  savedConfig,
  draftConfig,
  effectiveConfig,
}: BuildCapabilitySummariesArgs): CapabilitySummary[] {
  return CAPABILITIES.map((definition) => {
    const saved = pickConfig(savedConfig, definition);
    const draft = pickConfig(draftConfig, definition);
    const effective = pickConfig(effectiveConfig, definition);
    const hasSavedOverride = Object.keys(saved).length > 0;
    const isDirty = !isEqual(saved, draft);

    return {
      id: definition.id,
      title: definition.title,
      description: definition.description,
      state: isDirty ? "unsaved" : hasSavedOverride ? "custom" : "default",
      sourceLabel:
        definition.inheritsAgent && !hasSavedOverride
          ? "继承 Agent 配置"
          : hasSavedOverride
          ? "已自定义"
          : "采用默认值",
      summary: definition.summary(
        Object.keys(effective).length ? effective : draft,
      ),
      highImpact: definition.highImpact,
    };
  });
}

export function filterCapabilitySummaries(
  summaries: readonly CapabilitySummary[],
  filter: CapabilityFilter,
): CapabilitySummary[] {
  return summaries.filter((summary) =>
    filter === "all" ? true : summary.state === filter,
  );
}

export function addPromptSegment(prompts: readonly string[]): string[] {
  return [...prompts, ""];
}

export function removePromptSegment(
  prompts: readonly string[],
  index: number,
): string[] {
  return prompts.filter((_, itemIndex) => itemIndex !== index);
}

export function movePromptSegment(
  prompts: readonly string[],
  index: number,
  direction: -1 | 1,
): string[] {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= prompts.length) {
    return [...prompts];
  }
  const next = [...prompts];
  [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
  return next;
}
