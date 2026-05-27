import React from "react";
import { Switch, Tooltip } from "antd";
import type { IAgentScopeRuntimeWebUIInputData } from "@/components/agentscope-chat";
import styles from "./index.module.less";

export type ChatPlanMode = "plan" | "normal";

export type PlanModeSubmitCancelled = {
  shouldSubmit: false;
  clearInput?: boolean;
};

export type PlanModeSubmitResult =
  | IAgentScopeRuntimeWebUIInputData
  | PlanModeSubmitCancelled;

export type PlanModeSessionLike = {
  meta?: Record<string, unknown> | null;
};

export function getPlanModeEnabled(
  session?: PlanModeSessionLike | null,
): boolean {
  return session?.meta?.plan_mode_enabled === true;
}

export function buildPlanModeMeta(
  meta: Record<string, unknown> | null | undefined,
  enabled: boolean,
): Record<string, unknown> {
  return {
    ...(meta || {}),
    plan_mode_enabled: enabled,
  };
}

export function getPlanModeForRequest(enabled: boolean): ChatPlanMode {
  return enabled ? "plan" : "normal";
}

function withPlanMode(
  data: IAgentScopeRuntimeWebUIInputData,
  mode: ChatPlanMode,
): IAgentScopeRuntimeWebUIInputData {
  const explicitMode =
    data.biz_params?.mode === "plan" || data.biz_params?.mode === "normal"
      ? data.biz_params.mode
      : mode;
  return {
    ...data,
    biz_params: {
      ...(data.biz_params || {}),
      mode: explicitMode,
    },
  };
}

function parsePlanCommand(query: string): string | null {
  const match = query.match(/^\/plan(?:\s+([\s\S]*))?$/i);
  if (!match) {
    return null;
  }
  return (match[1] || "").trim();
}

export async function preparePlanModeSubmit(
  data: IAgentScopeRuntimeWebUIInputData,
  options: {
    planModeEnabled: boolean;
    persistPlanMode: (enabled: boolean) => Promise<void>;
  },
): Promise<PlanModeSubmitResult> {
  const planCommandText = parsePlanCommand(data.query.trim());
  if (planCommandText === null) {
    return withPlanMode(data, getPlanModeForRequest(options.planModeEnabled));
  }

  await options.persistPlanMode(true);

  if (!planCommandText) {
    return {
      shouldSubmit: false,
      clearInput: true,
    };
  }

  return withPlanMode(
    {
      ...data,
      query: planCommandText,
    },
    "plan",
  );
}

export function isPlanModeSubmitCancelled(
  result: unknown,
): result is PlanModeSubmitCancelled {
  return (
    Boolean(result) &&
    typeof result === "object" &&
    (result as PlanModeSubmitCancelled).shouldSubmit === false
  );
}

export function PlanModeToggle({
  enabled,
  disabled = false,
  label,
  tooltip,
  onChange,
}: {
  enabled: boolean;
  disabled?: boolean;
  label: string;
  tooltip?: string;
  onChange: (enabled: boolean) => void;
}) {
  const control = (
    <label className={styles.planModeToggle}>
      <span className={styles.planModeToggleLabel}>{label}</span>
      <Switch
        size="small"
        checked={enabled}
        disabled={disabled}
        aria-label={label}
        onChange={(checked) => onChange(checked)}
      />
    </label>
  );

  return tooltip ? <Tooltip title={tooltip}>{control}</Tooltip> : control;
}
