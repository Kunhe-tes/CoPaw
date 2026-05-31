import React from "react";
import { Switch, Tooltip } from "antd";
import type { IAgentScopeRuntimeWebUIInputData } from "@/components/agentscope-chat";
import { ApartmentOutlined } from "@ant-design/icons";
import { ComposerQuickMenuItem } from "@/components/agentscope-chat/ComposerQuickMenu";
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
  id?: string;
  realId?: string;
  sessionId?: string;
  session_id?: string;
  meta?: Record<string, unknown> | null;
};

type PersistPlanModeStateOptions<TSession extends PlanModeSessionLike> = {
  enabled: boolean;
  session: TSession | null;
  ensureChatId: (
    session: TSession | null,
    meta: Record<string, unknown>,
  ) => Promise<string | null>;
  updateChat: (
    chatId: string,
    payload: { meta: Record<string, unknown> },
  ) => Promise<{ meta?: Record<string, unknown> | null }>;
  updateSession: (session: {
    id: string;
    meta: Record<string, unknown>;
  }) => Promise<unknown>;
  setPlanModeEnabled: (enabled: boolean) => void;
  onPersistError?: (error: unknown) => void;
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

export function resolveActivePlanModeSession<
  TSession extends PlanModeSessionLike,
>(sessions: TSession[], ids: Array<string | null | undefined>): TSession | null {
  const idSet = new Set(
    ids.filter((value): value is string => Boolean(value)),
  );

  if (idSet.size === 0) {
    return null;
  }

  return (
    sessions.find((session) =>
      [session.id, session.realId, session.sessionId, session.session_id].some(
        (value) => Boolean(value && idSet.has(value)),
      ),
    ) || null
  );
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
    setPlanModeEnabled?: (enabled: boolean) => void;
  },
): Promise<PlanModeSubmitResult> {
  const planCommandText = parsePlanCommand(data.query.trim());
  if (planCommandText === null) {
    return withPlanMode(data, getPlanModeForRequest(options.planModeEnabled));
  }

  if (!planCommandText) {
    options.setPlanModeEnabled?.(true);
    return {
      shouldSubmit: false,
      clearInput: true,
    };
  }

  await options.persistPlanMode(true);

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

export async function persistPlanModeState<
  TSession extends PlanModeSessionLike,
>({
  enabled,
  session,
  ensureChatId,
  updateChat,
  updateSession,
  setPlanModeEnabled,
  onPersistError,
}: PersistPlanModeStateOptions<TSession>): Promise<void> {
  const nextMeta = buildPlanModeMeta(session?.meta, enabled);

  setPlanModeEnabled(enabled);

  try {
    const targetChatId = await ensureChatId(session, nextMeta);
    if (!targetChatId) {
      throw new Error("Missing chat id for Plan Mode state");
    }

    const updated = await updateChat(targetChatId, {
      meta: nextMeta,
    });

    await updateSession({
      id: session?.id || targetChatId,
      meta: updated.meta || nextMeta,
    });
  } catch (error) {
    setPlanModeEnabled(getPlanModeEnabled(session));
    onPersistError?.(error);
    throw error;
  }
}

export function PlanModeMenuItem({
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
    <ComposerQuickMenuItem
      icon={<ApartmentOutlined />}
      label={<span className={styles.planModeToggleLabel}>{label}</span>}
      extra={
        <Switch
          size="small"
          checked={enabled}
          disabled={disabled}
          aria-label={label}
          onChange={(checked) => onChange(checked)}
        />
      }
    />
  );

  return tooltip ? <Tooltip title={tooltip}>{control}</Tooltip> : control;
}

export function ActivePlanModeButton({
  enabled,
  disabled = false,
  label,
  onDisable,
}: {
  enabled: boolean;
  disabled?: boolean;
  label: string;
  onDisable: () => void;
}) {
  if (!enabled) {
    return null;
  }

  return (
    <button
      type="button"
      className={styles.planModeActiveButton}
      aria-label={label}
      disabled={disabled}
      onClick={onDisable}
    >
      <ApartmentOutlined />
      <span>{label}</span>
    </button>
  );
}
