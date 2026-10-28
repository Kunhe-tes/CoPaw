import type { IframeContext } from "../../types/iframe";

export interface SceneMonitoring {
  schedule: {
    type: "daily" | "weekly";
    hour: number;
    minute: number;
    daysOfWeek: string[];
  };
  cycle: "today" | "within7days" | "validity";
  expectedCompletionRate: number;
}

export type MonitoringConfigurations = Record<string, SceneMonitoring>;

export const MONITORING_SAVE_ERROR = "监控配置保存失败，请重新设置";

const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const CYCLES = ["today", "within7days", "validity"];

export function defaultMonitoring(): SceneMonitoring {
  return {
    schedule: { type: "daily", hour: 9, minute: 0, daysOfWeek: ["mon"] },
    cycle: "today",
    expectedCompletionRate: 60,
  };
}

export function monitoringScope(context: IframeContext): string {
  return JSON.stringify([
    context.source ?? "",
    context.space ?? "",
    context.bbk ?? "",
    context.orgCode ?? "",
    context.userId ?? "",
    context.positionId ?? "",
  ]);
}

export function monitoringStorageKey(
  scope: string,
  planId: string | null,
): string {
  const owner =
    planId === null ? "draft" : `plan:${encodeURIComponent(planId)}`;
  return `wealth:scene-monitoring:v1:${encodeURIComponent(scope)}:${owner}`;
}

function integerInRange(
  value: unknown,
  min: number,
  max: number,
): value is number {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= min &&
    value <= max
  );
}

function validMonitoring(value: unknown): value is SceneMonitoring {
  if (!value || typeof value !== "object") return false;
  const config = value as SceneMonitoring;
  const schedule = config.schedule;
  return Boolean(
    schedule &&
      (schedule.type === "daily" || schedule.type === "weekly") &&
      integerInRange(schedule.hour, 0, 23) &&
      integerInRange(schedule.minute, 0, 59) &&
      Array.isArray(schedule.daysOfWeek) &&
      schedule.daysOfWeek.length > 0 &&
      schedule.daysOfWeek.every((day) => WEEKDAYS.includes(day)) &&
      CYCLES.includes(config.cycle) &&
      integerInRange(config.expectedCompletionRate, 0, 100),
  );
}

export function readMonitoring(key: string): MonitoringConfigurations {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? "{}");
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    return Object.fromEntries(
      Object.entries(value).filter(([, config]) => validMonitoring(config)),
    );
  } catch {
    return {};
  }
}

export function writeMonitoring(
  key: string,
  configs: MonitoringConfigurations,
): boolean {
  try {
    localStorage.setItem(key, JSON.stringify(configs));
    return true;
  } catch {
    return false;
  }
}

export function saveSceneMonitoring(
  key: string,
  sceneId: string,
  config: SceneMonitoring,
): boolean {
  return writeMonitoring(key, { ...readMonitoring(key), [sceneId]: config });
}
