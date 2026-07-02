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

export interface CronUnreadAutoPauseConfig {
  enabled: boolean;
  threshold: number;
}

export interface CronTaskSessionCleanupConfig {
  enabled: boolean;
  retention_days: number;
  cron: string;
  run_time: string;
}

export interface QueryRetryConfig {
  enabled: boolean;
  max_retries: number;
  backoff_base: number;
  backoff_cap: number;
}

export interface LlmRateLimiterConfig {
  llm_max_concurrent: number;
  llm_chat_max_concurrent: number | null;
  llm_cron_max_concurrent: number | null;
  llm_max_qpm: number;
  llm_rate_limit_pause: number;
  llm_rate_limit_jitter: number;
  llm_acquire_timeout: number;
  llm_chat_acquire_timeout: number | null;
  llm_cron_acquire_timeout: number | null;
}

export type ImmediateTruncationConfigKey = "file_read_truncation";
export type ModelCallPolicyConfigKey = "query_retry" | "llm_rate_limiter";

export interface ImmediateTruncationState {
  explicit: boolean;
  config: ImmediateTruncationConfig;
}

export interface ModelCallPolicyState<T> {
  explicit: boolean;
  config: T;
}

export interface CurrentSourceConfigNumberDefinition {
  key: keyof Omit<ToolResultCompactConfig, "enabled">;
  title: string;
  min: number;
  max?: number;
  step: number;
}

export interface QueryRetryNumberDefinition {
  key: keyof Omit<QueryRetryConfig, "enabled">;
  title: string;
  min: number;
  step: number;
}

export interface LlmRateLimiterNumberDefinition {
  key: keyof LlmRateLimiterConfig;
  title: string;
  min: number;
  step: number;
  nullable?: boolean;
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
    {
      key: "feature_switches.database_access_guard_enabled",
      path: ["feature_switches", "database_access_guard_enabled"],
      defaultValue: true,
      title: "数据库访问拦截",
      description: "关闭后模型可通过 Python/命令行直连数据库，不再拦截。",
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

export const CRON_UNREAD_AUTO_PAUSE_DEFAULTS: CronUnreadAutoPauseConfig = {
  enabled: true,
  threshold: 10,
};

export const CRON_TASK_SESSION_CLEANUP_DEFAULTS: CronTaskSessionCleanupConfig =
  {
    enabled: false,
    retention_days: 30,
    cron: "0 1 * * *",
    run_time: "01:00",
  };

export const QUERY_RETRY_DEFAULTS: QueryRetryConfig = {
  enabled: false,
  max_retries: 3,
  backoff_base: 2,
  backoff_cap: 30,
};

export const LLM_RATE_LIMITER_DEFAULTS: LlmRateLimiterConfig = {
  llm_max_concurrent: 5,
  llm_chat_max_concurrent: 2,
  llm_cron_max_concurrent: 3,
  llm_max_qpm: 100,
  llm_rate_limit_pause: 5,
  llm_rate_limit_jitter: 1,
  llm_acquire_timeout: 300,
  llm_chat_acquire_timeout: null,
  llm_cron_acquire_timeout: null,
};

export const CRON_TASK_SESSION_CLEANUP_RUN_TIME_OPTIONS = Array.from(
  { length: 48 },
  (_, index) => {
    const totalMinutes = index * 30;
    const hour = Math.floor(totalMinutes / 60);
    const minute = totalMinutes % 60;
    return `${String(hour).padStart(2, "0")}:${String(minute).padStart(
      2,
      "0",
    )}`;
  },
);

export const CRON_UNREAD_AUTO_PAUSE_MIN_THRESHOLD = 1;

export const CRON_TASK_SESSION_CLEANUP_MIN_RETENTION_DAYS = 1;

export const IMMEDIATE_TRUNCATION_MIN_BYTES = 1000;

export const QUERY_RETRY_BACKOFF_BASE_MIN = 0.5;
export const QUERY_RETRY_BACKOFF_CAP_MIN = 1;

export const SYSTEM_PROMPT_INJECTION_SEPARATOR = /\n\s*\n/g;

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

export const QUERY_RETRY_NUMBER_FIELDS: QueryRetryNumberDefinition[] = [
  {
    key: "max_retries",
    title: "最大重试次数",
    min: 1,
    step: 1,
  },
  {
    key: "backoff_base",
    title: "基础退避秒数",
    min: QUERY_RETRY_BACKOFF_BASE_MIN,
    step: 0.1,
  },
  {
    key: "backoff_cap",
    title: "最大退避秒数",
    min: QUERY_RETRY_BACKOFF_CAP_MIN,
    step: 0.5,
  },
];

export const LLM_RATE_LIMITER_NUMBER_FIELDS: LlmRateLimiterNumberDefinition[] =
  [
    {
      key: "llm_max_concurrent",
      title: "兜底并发数",
      min: 1,
      step: 1,
    },
    {
      key: "llm_chat_max_concurrent",
      title: "对话并发数",
      min: 1,
      step: 1,
      nullable: true,
    },
    {
      key: "llm_cron_max_concurrent",
      title: "定时任务并发数",
      min: 1,
      step: 1,
      nullable: true,
    },
    {
      key: "llm_max_qpm",
      title: "每分钟请求数",
      min: 0,
      step: 10,
    },
    {
      key: "llm_rate_limit_pause",
      title: "限流暂停秒数",
      min: 1,
      step: 0.5,
    },
    {
      key: "llm_rate_limit_jitter",
      title: "随机抖动秒数",
      min: 0,
      step: 0.5,
    },
    {
      key: "llm_acquire_timeout",
      title: "兜底等待秒数",
      min: 10,
      step: 10,
    },
    {
      key: "llm_chat_acquire_timeout",
      title: "对话等待秒数",
      min: 10,
      step: 10,
      nullable: true,
    },
    {
      key: "llm_cron_acquire_timeout",
      title: "定时任务等待秒数",
      min: 10,
      step: 10,
      nullable: true,
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

export function readCronUnreadAutoPauseConfig(
  config: SourceSystemConfig,
): CronUnreadAutoPauseConfig {
  const rawValue = config.cron_unread_auto_pause;
  if (!isPlainObject(rawValue)) {
    return { ...CRON_UNREAD_AUTO_PAUSE_DEFAULTS };
  }
  return {
    enabled:
      typeof rawValue.enabled === "boolean"
        ? rawValue.enabled
        : CRON_UNREAD_AUTO_PAUSE_DEFAULTS.enabled,
    threshold:
      typeof rawValue.threshold === "number"
        ? rawValue.threshold
        : CRON_UNREAD_AUTO_PAUSE_DEFAULTS.threshold,
  };
}

export function writeCronUnreadAutoPauseValue<
  K extends keyof CronUnreadAutoPauseConfig,
>(
  config: SourceSystemConfig,
  key: K,
  value: CronUnreadAutoPauseConfig[K],
): SourceSystemConfig {
  const nextConfig = clonePlainConfig(config);
  const rawValue = nextConfig.cron_unread_auto_pause;
  if (!isPlainObject(rawValue)) {
    nextConfig.cron_unread_auto_pause = {};
  }
  (nextConfig.cron_unread_auto_pause as Record<string, unknown>)[key] = value;
  return nextConfig;
}

export function dailyRunTimeToCron(value: string): string | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  if (!match) {
    return null;
  }
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (
    !Number.isInteger(hour) ||
    !Number.isInteger(minute) ||
    hour < 0 ||
    hour > 23 ||
    minute < 0 ||
    minute > 59
  ) {
    return null;
  }
  return `${minute} ${hour} * * *`;
}

export function cronToDailyRunTime(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const parts = value.trim().split(/\s+/);
  if (parts.length !== 5) {
    return null;
  }
  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;
  if (dayOfMonth !== "*" || month !== "*" || dayOfWeek !== "*") {
    return null;
  }
  if (!/^\d+$/.test(minute) || !/^\d+$/.test(hour)) {
    return null;
  }
  const minuteValue = Number(minute);
  const hourValue = Number(hour);
  if (minuteValue < 0 || minuteValue > 59 || hourValue < 0 || hourValue > 23) {
    return null;
  }
  return `${String(hourValue).padStart(2, "0")}:${String(minuteValue).padStart(
    2,
    "0",
  )}`;
}

export function readCronTaskSessionCleanupConfig(
  config: SourceSystemConfig,
): CronTaskSessionCleanupConfig {
  const rawValue = config.cron_task_session_cleanup;
  if (!isPlainObject(rawValue)) {
    return { ...CRON_TASK_SESSION_CLEANUP_DEFAULTS };
  }
  const cron =
    typeof rawValue.cron === "string"
      ? rawValue.cron
      : CRON_TASK_SESSION_CLEANUP_DEFAULTS.cron;
  return {
    enabled:
      typeof rawValue.enabled === "boolean"
        ? rawValue.enabled
        : CRON_TASK_SESSION_CLEANUP_DEFAULTS.enabled,
    retention_days:
      typeof rawValue.retention_days === "number"
        ? rawValue.retention_days
        : CRON_TASK_SESSION_CLEANUP_DEFAULTS.retention_days,
    cron,
    run_time:
      cronToDailyRunTime(cron) ?? CRON_TASK_SESSION_CLEANUP_DEFAULTS.run_time,
  };
}

export function writeCronTaskSessionCleanupValue(
  config: SourceSystemConfig,
  key: "enabled" | "retention_days" | "cron" | "run_time",
  value: boolean | number | string,
): SourceSystemConfig {
  const nextConfig = clonePlainConfig(config);
  const rawValue = nextConfig.cron_task_session_cleanup;
  if (!isPlainObject(rawValue)) {
    nextConfig.cron_task_session_cleanup = {};
  }
  const section = nextConfig.cron_task_session_cleanup as Record<
    string,
    unknown
  >;
  if (key === "run_time") {
    const cron = dailyRunTimeToCron(String(value));
    if (cron !== null) {
      section.cron = cron;
    }
    return nextConfig;
  }
  section[key] = value;
  return nextConfig;
}

export function readQueryRetryConfigState(
  config: SourceSystemConfig,
  effectiveConfig?: SourceSystemConfig | null,
): ModelCallPolicyState<QueryRetryConfig> {
  const defaults = readQueryRetryDefaults(effectiveConfig);
  const rawValue = config.query_retry;
  if (!isPlainObject(rawValue)) {
    return {
      explicit: false,
      config: defaults,
    };
  }
  return {
    explicit: true,
    config: {
      enabled:
        typeof rawValue.enabled === "boolean"
          ? rawValue.enabled
          : defaults.enabled,
      max_retries:
        typeof rawValue.max_retries === "number"
          ? rawValue.max_retries
          : defaults.max_retries,
      backoff_base:
        typeof rawValue.backoff_base === "number"
          ? rawValue.backoff_base
          : defaults.backoff_base,
      backoff_cap:
        typeof rawValue.backoff_cap === "number"
          ? rawValue.backoff_cap
          : defaults.backoff_cap,
    },
  };
}

export function readLlmRateLimiterConfigState(
  config: SourceSystemConfig,
  effectiveConfig?: SourceSystemConfig | null,
): ModelCallPolicyState<LlmRateLimiterConfig> {
  const defaults = readLlmRateLimiterDefaults(effectiveConfig);
  const rawValue = config.llm_rate_limiter;
  if (!isPlainObject(rawValue)) {
    return {
      explicit: false,
      config: defaults,
    };
  }
  const readNumber = <K extends keyof LlmRateLimiterConfig>(
    key: K,
  ): LlmRateLimiterConfig[K] => {
    const value = rawValue[key];
    if (typeof value === "number" || value === null) {
      return value as LlmRateLimiterConfig[K];
    }
    return defaults[key];
  };
  return {
    explicit: true,
    config: {
      llm_max_concurrent: readNumber("llm_max_concurrent"),
      llm_chat_max_concurrent: readNumber("llm_chat_max_concurrent"),
      llm_cron_max_concurrent: readNumber("llm_cron_max_concurrent"),
      llm_max_qpm: readNumber("llm_max_qpm"),
      llm_rate_limit_pause: readNumber("llm_rate_limit_pause"),
      llm_rate_limit_jitter: readNumber("llm_rate_limit_jitter"),
      llm_acquire_timeout: readNumber("llm_acquire_timeout"),
      llm_chat_acquire_timeout: readNumber("llm_chat_acquire_timeout"),
      llm_cron_acquire_timeout: readNumber("llm_cron_acquire_timeout"),
    },
  };
}

export function enableModelCallPolicyConfig(
  config: SourceSystemConfig,
  configKey: ModelCallPolicyConfigKey,
  effectiveConfig?: SourceSystemConfig | null,
): SourceSystemConfig {
  const nextConfig = clonePlainConfig(config);
  nextConfig[configKey] =
    configKey === "query_retry"
      ? readQueryRetryDefaults(effectiveConfig)
      : readLlmRateLimiterDefaults(effectiveConfig);
  return nextConfig;
}

function readQueryRetryDefaults(
  effectiveConfig?: SourceSystemConfig | null,
): QueryRetryConfig {
  const rawValue = effectiveConfig?.query_retry;
  if (!isPlainObject(rawValue)) {
    return { ...QUERY_RETRY_DEFAULTS };
  }
  return {
    enabled:
      typeof rawValue.enabled === "boolean"
        ? rawValue.enabled
        : QUERY_RETRY_DEFAULTS.enabled,
    max_retries:
      typeof rawValue.max_retries === "number"
        ? rawValue.max_retries
        : QUERY_RETRY_DEFAULTS.max_retries,
    backoff_base:
      typeof rawValue.backoff_base === "number"
        ? rawValue.backoff_base
        : QUERY_RETRY_DEFAULTS.backoff_base,
    backoff_cap:
      typeof rawValue.backoff_cap === "number"
        ? rawValue.backoff_cap
        : QUERY_RETRY_DEFAULTS.backoff_cap,
  };
}

function readLlmRateLimiterDefaults(
  effectiveConfig?: SourceSystemConfig | null,
): LlmRateLimiterConfig {
  const rawValue = effectiveConfig?.llm_rate_limiter;
  if (!isPlainObject(rawValue)) {
    return { ...LLM_RATE_LIMITER_DEFAULTS };
  }
  const readNumber = <K extends keyof LlmRateLimiterConfig>(
    key: K,
  ): LlmRateLimiterConfig[K] => {
    const value = rawValue[key];
    if (typeof value === "number" || value === null) {
      return value as LlmRateLimiterConfig[K];
    }
    return LLM_RATE_LIMITER_DEFAULTS[key];
  };
  return {
    llm_max_concurrent: readNumber("llm_max_concurrent"),
    llm_chat_max_concurrent: readNumber("llm_chat_max_concurrent"),
    llm_cron_max_concurrent: readNumber("llm_cron_max_concurrent"),
    llm_max_qpm: readNumber("llm_max_qpm"),
    llm_rate_limit_pause: readNumber("llm_rate_limit_pause"),
    llm_rate_limit_jitter: readNumber("llm_rate_limit_jitter"),
    llm_acquire_timeout: readNumber("llm_acquire_timeout"),
    llm_chat_acquire_timeout: readNumber("llm_chat_acquire_timeout"),
    llm_cron_acquire_timeout: readNumber("llm_cron_acquire_timeout"),
  };
}

export function clearModelCallPolicyConfig(
  config: SourceSystemConfig,
  configKey: ModelCallPolicyConfigKey,
): SourceSystemConfig {
  const nextConfig = clonePlainConfig(config);
  delete nextConfig[configKey];
  return nextConfig;
}

export function writeQueryRetryValue<K extends keyof QueryRetryConfig>(
  config: SourceSystemConfig,
  key: K,
  value: QueryRetryConfig[K],
): SourceSystemConfig {
  const nextConfig = clonePlainConfig(config);
  const rawValue = nextConfig.query_retry;
  if (!isPlainObject(rawValue)) {
    nextConfig.query_retry = {};
  }
  (nextConfig.query_retry as Record<string, unknown>)[key] = value;
  return nextConfig;
}

export function writeLlmRateLimiterValue<K extends keyof LlmRateLimiterConfig>(
  config: SourceSystemConfig,
  key: K,
  value: LlmRateLimiterConfig[K],
): SourceSystemConfig {
  const nextConfig = clonePlainConfig(config);
  const rawValue = nextConfig.llm_rate_limiter;
  if (!isPlainObject(rawValue)) {
    nextConfig.llm_rate_limiter = {};
  }
  (nextConfig.llm_rate_limiter as Record<string, unknown>)[key] = value;
  return nextConfig;
}

export function normalizeSystemPromptInjections(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const seen = new Set<string>();
  const prompts: string[] = [];
  for (const item of value) {
    const prompt = String(item).trim();
    if (!prompt || seen.has(prompt)) {
      continue;
    }
    seen.add(prompt);
    prompts.push(prompt);
  }
  return prompts;
}

export function readSystemPromptInjections(
  config: SourceSystemConfig,
): string[] {
  return normalizeSystemPromptInjections(config.system_prompt_injections);
}

export function parseSystemPromptInjectionText(value: string): string[] {
  return normalizeSystemPromptInjections(
    value.split(SYSTEM_PROMPT_INJECTION_SEPARATOR),
  );
}

export function formatSystemPromptInjectionText(
  prompts: readonly string[],
): string {
  return normalizeSystemPromptInjections([...prompts]).join("\n\n");
}

export function writeSystemPromptInjections(
  config: SourceSystemConfig,
  value: unknown,
): SourceSystemConfig {
  const nextConfig = clonePlainConfig(config);
  const prompts = normalizeSystemPromptInjections(value);
  if (prompts.length === 0) {
    delete nextConfig.system_prompt_injections;
    return nextConfig;
  }
  nextConfig.system_prompt_injections = prompts;
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
  const nextConfig = clonePlainConfig(config);
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
  const nextConfig = clonePlainConfig(config);
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

export function validateQueryRetryConfig(
  state: ModelCallPolicyState<QueryRetryConfig>,
): string | null {
  if (!state.explicit) {
    return null;
  }
  const config = state.config;
  if (!Number.isInteger(config.max_retries) || config.max_retries < 1) {
    return "最大重试次数不能小于 1";
  }
  if (config.backoff_base < QUERY_RETRY_BACKOFF_BASE_MIN) {
    return `基础退避秒数不能小于 ${QUERY_RETRY_BACKOFF_BASE_MIN}`;
  }
  if (config.backoff_cap < QUERY_RETRY_BACKOFF_CAP_MIN) {
    return `最大退避秒数不能小于 ${QUERY_RETRY_BACKOFF_CAP_MIN}`;
  }
  if (config.backoff_cap < config.backoff_base) {
    return "最大退避秒数不能小于基础退避秒数";
  }
  return null;
}

export function validateLlmRateLimiterConfig(
  state: ModelCallPolicyState<LlmRateLimiterConfig>,
): string | null {
  if (!state.explicit) {
    return null;
  }
  const config = state.config;
  for (const definition of LLM_RATE_LIMITER_NUMBER_FIELDS) {
    const value = config[definition.key];
    if (value == null && definition.nullable) {
      continue;
    }
    if (typeof value !== "number" || value < definition.min) {
      return `${definition.title}不能小于 ${definition.min}`;
    }
    if (
      definition.step === 1 &&
      !definition.nullable &&
      !Number.isInteger(value)
    ) {
      return `${definition.title}必须是整数`;
    }
  }
  const cooldown = config.llm_rate_limit_pause + config.llm_rate_limit_jitter;
  const timeoutChecks: Array<[number | null, string]> = [
    [config.llm_acquire_timeout, "兜底等待秒数"],
    [config.llm_chat_acquire_timeout, "对话等待秒数"],
    [config.llm_cron_acquire_timeout, "定时任务等待秒数"],
  ];
  for (const [value, label] of timeoutChecks) {
    if (value != null && value <= cooldown) {
      return `${label}必须大于限流暂停秒数与随机抖动秒数之和`;
    }
  }
  return null;
}

export function validateCronUnreadAutoPauseConfig(
  config: CronUnreadAutoPauseConfig,
): string | null {
  if (
    !Number.isInteger(config.threshold) ||
    config.threshold < CRON_UNREAD_AUTO_PAUSE_MIN_THRESHOLD
  ) {
    return `未读暂停条数不能小于 ${CRON_UNREAD_AUTO_PAUSE_MIN_THRESHOLD}`;
  }
  return null;
}

export function validateCronTaskSessionCleanupConfig(
  config: CronTaskSessionCleanupConfig,
): string | null {
  if (
    !Number.isInteger(config.retention_days) ||
    config.retention_days < CRON_TASK_SESSION_CLEANUP_MIN_RETENTION_DAYS
  ) {
    return `浠诲姟浼氳瘽鍘嗗彶淇濈暀澶╂暟涓嶈兘灏忎簬 ${CRON_TASK_SESSION_CLEANUP_MIN_RETENTION_DAYS}`;
  }
  if (cronToDailyRunTime(config.cron) === null) {
    return "cron_task_session_cleanup.cron must be daily cron";
  }
  return null;
}

export function validateSourceSystemConfig(
  config: SourceSystemConfig,
  effectiveConfig?: SourceSystemConfig | null,
): string | null {
  return (
    validateCronTaskSessionCleanupConfig(
      readCronTaskSessionCleanupConfig(config),
    ) ||
    validateCronUnreadAutoPauseConfig(readCronUnreadAutoPauseConfig(config)) ||
    validateQueryRetryConfig(
      readQueryRetryConfigState(config, effectiveConfig),
    ) ||
    validateLlmRateLimiterConfig(
      readLlmRateLimiterConfigState(config, effectiveConfig),
    ) ||
    validateToolOutputConfigs(config)
  );
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
