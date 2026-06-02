import type { SourceSystemConfig } from "@/api/types/sourceSystemConfig";
import { clonePlainConfig } from "@/utils/clonePlainConfig";

export interface CurrentSourceConfigSwitchDefinition {
  key: string;
  path: string[];
  defaultValue: boolean;
  title: string;
  description: string;
}

export interface ToolResultCompactConfig {
  enabled: boolean;
  recent_n: number;
  old_max_bytes: number;
  recent_max_bytes: number;
  retention_days: number;
}

export interface ImmediateTruncationConfig {
  enabled: boolean;
  max_bytes: number;
}

export type ImmediateTruncationConfigKey =
  | "file_read_truncation";

export interface ImmediateTruncationState {
  explicit: boolean;
  config: ImmediateTruncationConfig;
}

export interface CurrentSourceConfigNumberDefinition {
  key: keyof Omit<ToolResultCompactConfig, "enabled">;
  title: string;
  min: number;
  max?: number;
  step: number;
}

export const CURRENT_SOURCE_SYSTEM_CONFIG_SWITCHES: CurrentSourceConfigSwitchDefinition[] =
  [
    {
      key: "feature_switches.chat_task_progress_enabled",
      path: ["feature_switches", "chat_task_progress_enabled"],
      defaultValue: true,
      title: "任务进度步骤条",
      description:
        "关闭后不再注入 task progress 提示词，也不会写入或展示步骤进度。",
    },
  ];

export const TOOL_RESULT_COMPACT_DEFAULTS: ToolResultCompactConfig = {
  enabled: true,
  recent_n: 2,
  old_max_bytes: 3000,
  recent_max_bytes: 50000,
  retention_days: 5,
};

export const FILE_READ_TRUNCATION_DEFAULTS: ImmediateTruncationConfig = {
  enabled: true,
  max_bytes: 50000,
};

export const IMMEDIATE_TRUNCATION_MIN_BYTES = 1000;

export const TOOL_RESULT_COMPACT_NUMBER_FIELDS: CurrentSourceConfigNumberDefinition[] =
  [
    {
      key: "recent_n",
      title: "近期消息数量",
      min: 1,
      max: 10,
      step: 1,
    },
    {
      key: "old_max_bytes",
      title: "旧结果预览字节数",
      min: 100,
      step: 100,
    },
    {
      key: "recent_max_bytes",
      title: "近期结果预览字节数",
      min: 1000,
      step: 1000,
    },
    {
      key: "retention_days",
      title: "toolresult 保留天数",
      min: 1,
      max: 10,
      step: 1,
    },
  ];

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function readRegisteredSwitchValue(
  config: SourceSystemConfig,
  definition: CurrentSourceConfigSwitchDefinition,
): boolean {
  let current: unknown = config;
  for (const key of definition.path) {
    if (!current || typeof current !== "object" || !(key in current)) {
      return definition.defaultValue;
    }
    current = (current as Record<string, unknown>)[key];
  }
  return typeof current === "boolean" ? current : definition.defaultValue;
}

export function writeRegisteredSwitchValue(
  config: SourceSystemConfig,
  definition: CurrentSourceConfigSwitchDefinition,
  value: boolean,
): SourceSystemConfig {
  const nextConfig = clonePlainConfig(config);
  let current: Record<string, unknown> = nextConfig;
  definition.path.forEach((segment, index) => {
    const isLeaf = index === definition.path.length - 1;
    if (isLeaf) {
      current[segment] = value;
      return;
    }
    const nextValue = current[segment];
    if (
      !nextValue ||
      typeof nextValue !== "object" ||
      Array.isArray(nextValue)
    ) {
      current[segment] = {};
    }
    current = current[segment] as Record<string, unknown>;
  });
  return nextConfig;
}

export function readToolResultCompactConfig(
  config: SourceSystemConfig,
): ToolResultCompactConfig {
  const rawValue = config.tool_result_compact;
  if (!isPlainObject(rawValue)) {
    return { ...TOOL_RESULT_COMPACT_DEFAULTS };
  }
  const rawConfig = rawValue;
  return {
    enabled:
      typeof rawConfig.enabled === "boolean"
        ? rawConfig.enabled
        : TOOL_RESULT_COMPACT_DEFAULTS.enabled,
    recent_n:
      typeof rawConfig.recent_n === "number"
        ? rawConfig.recent_n
        : TOOL_RESULT_COMPACT_DEFAULTS.recent_n,
    old_max_bytes:
      typeof rawConfig.old_max_bytes === "number"
        ? rawConfig.old_max_bytes
        : TOOL_RESULT_COMPACT_DEFAULTS.old_max_bytes,
    recent_max_bytes:
      typeof rawConfig.recent_max_bytes === "number"
        ? rawConfig.recent_max_bytes
        : TOOL_RESULT_COMPACT_DEFAULTS.recent_max_bytes,
    retention_days:
      typeof rawConfig.retention_days === "number"
        ? rawConfig.retention_days
        : TOOL_RESULT_COMPACT_DEFAULTS.retention_days,
  };
}

export function writeToolResultCompactValue<
  K extends keyof ToolResultCompactConfig,
>(
  config: SourceSystemConfig,
  key: K,
  value: ToolResultCompactConfig[K],
): SourceSystemConfig {
  const nextConfig = clonePlainConfig(config);
  const rawValue = nextConfig.tool_result_compact;
  if (!isPlainObject(rawValue)) {
    nextConfig.tool_result_compact = {};
  }
  (nextConfig.tool_result_compact as Record<string, unknown>)[key] = value;
  return nextConfig;
}

export function readImmediateTruncationConfig(
  config: SourceSystemConfig,
  key: ImmediateTruncationConfigKey,
): ImmediateTruncationState {
  const defaults = FILE_READ_TRUNCATION_DEFAULTS;
  const rawValue = config[key];
  if (!isPlainObject(rawValue)) {
    return {
      explicit: false,
      config: { ...defaults },
    };
  }
  return {
    explicit: true,
    config: {
      enabled:
        typeof rawValue.enabled === "boolean"
          ? rawValue.enabled
          : defaults.enabled,
      max_bytes:
        typeof rawValue.max_bytes === "number"
          ? rawValue.max_bytes
          : defaults.max_bytes,
    },
  };
}

export function writeImmediateTruncationValue<
  K extends keyof ImmediateTruncationConfig,
>(
  config: SourceSystemConfig,
  configKey: ImmediateTruncationConfigKey,
  key: K,
  value: ImmediateTruncationConfig[K],
): SourceSystemConfig {
  const defaults = FILE_READ_TRUNCATION_DEFAULTS;
  const nextConfig = structuredClone(config);
  const rawValue = nextConfig[configKey];
  if (!isPlainObject(rawValue)) {
    nextConfig[configKey] = {};
  }
  const section = nextConfig[configKey] as Record<string, unknown>;
  section[key] = value;
  if (
    key === "enabled" &&
    value === true &&
    typeof section.max_bytes !== "number"
  ) {
    section.max_bytes = defaults.max_bytes;
  }
  return nextConfig;
}

export function enableImmediateTruncationConfig(
  config: SourceSystemConfig,
  configKey: ImmediateTruncationConfigKey,
): SourceSystemConfig {
  const defaults = FILE_READ_TRUNCATION_DEFAULTS;
  const nextConfig = writeImmediateTruncationValue(
    config,
    configKey,
    "enabled",
    true,
  );
  const rawValue = nextConfig[configKey];
  if (isPlainObject(rawValue) && typeof rawValue.max_bytes !== "number") {
    rawValue.max_bytes = defaults.max_bytes;
  }
  return nextConfig;
}

export function clearImmediateTruncationConfig(
  config: SourceSystemConfig,
  configKey: ImmediateTruncationConfigKey,
): SourceSystemConfig {
  const nextConfig = structuredClone(config);
  delete nextConfig[configKey];
  return nextConfig;
}

export function validateToolResultCompactConfig(
  config: ToolResultCompactConfig,
): string | null {
  for (const definition of TOOL_RESULT_COMPACT_NUMBER_FIELDS) {
    const value = config[definition.key];
    if (!Number.isInteger(value) || value < definition.min) {
      return `${definition.title}不能小于 ${definition.min}`;
    }
    if (definition.max !== undefined && value > definition.max) {
      return `${definition.title}不能大于 ${definition.max}`;
    }
  }
  if (config.recent_max_bytes < config.old_max_bytes) {
    return "近期结果预览字节数不能小于旧结果预览字节数";
  }
  return null;
}

export function validateImmediateTruncationConfig(
  state: ImmediateTruncationState,
  title: string,
): string | null {
  if (!state.explicit) {
    return null;
  }
  const value = state.config.max_bytes;
  if (!Number.isInteger(value) || value < IMMEDIATE_TRUNCATION_MIN_BYTES) {
    return `${title}不能小于 ${IMMEDIATE_TRUNCATION_MIN_BYTES}`;
  }
  return null;
}

export function validateToolOutputConfigs(
  config: SourceSystemConfig,
): string | null {
  return (
    validateToolResultCompactConfig(readToolResultCompactConfig(config)) ||
    validateImmediateTruncationConfig(
      readImmediateTruncationConfig(config, "file_read_truncation"),
      "文件读取输出片段字节数",
    )
  );
}
