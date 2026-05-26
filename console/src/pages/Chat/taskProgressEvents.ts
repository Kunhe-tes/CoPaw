import { emit } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/useChatAnywhereEventEmitter";

export type ChatTaskProgressItem = {
  id: string;
  label: string;
  status: "todo" | "running" | "done";
};

export type ChatTaskProgressData = {
  turn_id: string;
  phase_status: "active" | "completed" | "cancelled";
  version: number;
  current_step_index: number | null;
  total_steps: number;
  title?: string;
  items: ChatTaskProgressItem[];
};

export type ChatTaskProgressOwner = {
  session_id?: string;
  logical_session_id?: string;
  chat_id?: string | null;
};

export type ChatTaskProgressUpdateDetail =
  | ChatTaskProgressData
  | null
  | (ChatTaskProgressOwner & {
      task_progress: ChatTaskProgressData | null;
    });

export type NormalizedChatTaskProgressUpdate = ChatTaskProgressOwner & {
  task_progress: ChatTaskProgressData | null;
};

export const CHAT_TASK_PROGRESS_UPDATE_EVENT = "chat-task-progress-update";

function isTaskProgressItem(value: unknown): value is ChatTaskProgressItem {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return (
    typeof item.id === "string"
    && typeof item.label === "string"
    && (item.status === "todo"
      || item.status === "running"
      || item.status === "done")
  );
}

export function extractTaskProgress(
  value: unknown,
): ChatTaskProgressData | null | undefined {
  if (!value || typeof value !== "object") return undefined;
  const raw = value as Record<string, unknown>;
  if (!Object.prototype.hasOwnProperty.call(raw, "task_progress")) {
    return undefined;
  }

  const progress = raw.task_progress;
  if (!progress || typeof progress !== "object") {
    return null;
  }

  const payload = progress as Record<string, unknown>;
  if (
    typeof payload.turn_id !== "string"
    || (payload.phase_status !== "active"
      && payload.phase_status !== "completed"
      && payload.phase_status !== "cancelled")
    || typeof payload.version !== "number"
    || typeof payload.total_steps !== "number"
    || !Array.isArray(payload.items)
    || !payload.items.every(isTaskProgressItem)
  ) {
    return null;
  }

  const currentStepIndex =
    typeof payload.current_step_index === "number"
      ? payload.current_step_index
      : null;

  return {
    turn_id: payload.turn_id,
    phase_status: payload.phase_status,
    version: payload.version,
    current_step_index: currentStepIndex,
    total_steps: payload.total_steps,
    title: typeof payload.title === "string" ? payload.title : undefined,
    items: payload.items,
  };
}

export function emitTaskProgressUpdate(
  payload: ChatTaskProgressData | null,
  owner?: {
    sessionId?: string;
    logicalSessionId?: string;
    chatId?: string | null;
  },
): void {
  const data: ChatTaskProgressUpdateDetail = owner
    ? {
        task_progress: payload,
        session_id: owner.sessionId,
        logical_session_id: owner.logicalSessionId,
        chat_id: owner.chatId,
      }
    : payload;

  emit({
    type: CHAT_TASK_PROGRESS_UPDATE_EVENT,
    data,
  });
}

export function normalizeTaskProgressUpdateEventDetail(
  detail: ChatTaskProgressUpdateDetail,
): NormalizedChatTaskProgressUpdate {
  if (
    detail &&
    typeof detail === "object" &&
    Object.prototype.hasOwnProperty.call(detail, "task_progress")
  ) {
    const wrapped = detail as ChatTaskProgressOwner & {
      task_progress: ChatTaskProgressData | null;
    };
    return {
      task_progress: wrapped.task_progress,
      session_id: wrapped.session_id,
      logical_session_id: wrapped.logical_session_id,
      chat_id: wrapped.chat_id,
    };
  }

  return {
    task_progress: detail as ChatTaskProgressData | null,
  };
}

export function isTaskProgressUpdateForActiveSession(
  update: NormalizedChatTaskProgressUpdate,
  activeSessionIdentities: Array<string | null | undefined>,
): boolean {
  const ownerIdentities = [
    update.session_id,
    update.logical_session_id,
    update.chat_id,
  ].filter((value): value is string => Boolean(value));

  if (ownerIdentities.length === 0) {
    return true;
  }

  const activeIdentities = new Set(
    activeSessionIdentities.filter((value): value is string => Boolean(value)),
  );
  return ownerIdentities.some((identity) => activeIdentities.has(identity));
}
