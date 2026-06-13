import type { ReactNode } from "react";

export interface UserRow {
  userId: string;
  userName?: string;
  bbkId?: string;
  name: string;
  calls: number;
  tokens: number;
  lastActive: string;
  // 三种口径统计字段
  manualCalls: number;
  cronExecutions: number;
  cronReads: number;
}

// 活跃用户排行榜口径类型
export type UserMetricType = "manual" | "cron_exec" | "cron_read";

export interface UserDetailModalProps {
  open: boolean;
  userId: string | null;
  userName?: string;
  startDate?: string;
  endDate?: string;
  bbkIds?: string;
  onClose: () => void;
}

export interface BreakdownItem {
  name: string;
  value: number;
  valueText: string;
}

export interface OverviewMetricCard {
  key: string;
  title: string;
  valueText: ReactNode;
  changeText: string;
  changeDirection: "up" | "down" | "flat";
  accentColor: string;
  breakdown: BreakdownItem[] | null;
}

export interface DepthStatCard {
  key: string;
  title: string;
  valueText: string;
  changeText: string;
  changeDirection: "up" | "down" | "flat";
}

export interface SummaryLegendItem {
  key: string;
  label: string;
  value: number;
  color: string;
}

export interface TrendDatum {
  date: string;
  calls: number;
  users: number;
}

export type TimeRange = "day" | "week" | "month" | "custom";


export function formatNumber(
  value: number | string | undefined | null,
  decimals = 0,
): string {
  const numberValue = Number(value);
  if (Number.isNaN(numberValue)) {
    return "0";
  }
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  }).format(numberValue);
}

export function formatTokens(
  value: number | string | undefined | null,
): string {
  const numberValue = Number(value);
  if (Number.isNaN(numberValue)) {
    return "0";
  }
  // 使用英文单位：B、M、K
  if (numberValue >= 1000000000) {
    return `${(numberValue / 1000000000).toFixed(2)}B`;
  }
  if (numberValue >= 1000000) {
    return `${(numberValue / 1000000).toFixed(1)}M`;
  }
  if (numberValue >= 1000) {
    return `${(numberValue / 1000).toFixed(0)}K`;
  }
  return formatNumber(numberValue, 0);
}

export function formatPercent(value: number | undefined | null): string {
  const numberValue =
    typeof value === "number" && !Number.isNaN(value) ? value : 0;
  return `${numberValue.toFixed(1)}%`;
}

export function formatChange(value: number | undefined | null): string {
  if (value === null || value === undefined) {
    return "--";
  }
  const numberValue =
    typeof value === "number" && !Number.isNaN(value) ? value : 0;
  const sign = numberValue > 0 ? "+" : "";
  return `${sign}${numberValue.toFixed(1)}%`;
}

export function formatDuration(seconds: number | undefined | null): string {
  const numberValue =
    typeof seconds === "number" && !Number.isNaN(seconds) ? seconds : 0;

  if (numberValue < 1) {
    return `${Math.round(numberValue * 1000)}ms`;
  }
  if (numberValue < 60) {
    return `${numberValue.toFixed(2).replace(/\.00$/, "")}s`;
  }

  const minutes = Math.floor(numberValue / 60);
  const remainSeconds = Math.floor(numberValue % 60);
  return `${minutes}m ${remainSeconds}s`;
}

export function toChangeDirection(
  value: number | undefined | null,
): "up" | "down" | "flat" {
  if (value === null || value === undefined) {
    return "flat";
  }
  const numberValue =
    typeof value === "number" && !Number.isNaN(value) ? value : 0;
  if (numberValue > 0) {
    return "up";
  }
  if (numberValue < 0) {
    return "down";
  }
  return "flat";
}

export function truncateName(name: string, maxLength = 20): string {
  if (!name) {
    return "";
  }
  if (name.length <= maxLength) {
    return name;
  }
  return `${name.slice(0, maxLength)}...`;
}

