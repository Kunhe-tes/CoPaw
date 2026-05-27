import dayjs from "dayjs";
import type {
  IAgentScopeRuntimeRequest,
  IAgentScopeRuntimeResponse,
} from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/AgentScopeRuntime/types";
import type { IAgentScopeRuntimeWebUIMessage } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/types/IMessages";

export interface ChatMessageHeaderMeta {
  timestamp?: number;
}

export interface ChatRuntimeRequestCardData extends IAgentScopeRuntimeRequest {
  headerMeta?: ChatMessageHeaderMeta;
}

export interface ChatRuntimeResponseCardData
  extends IAgentScopeRuntimeResponse {
  headerMeta?: ChatMessageHeaderMeta;
}

function readMetadataOriginalId(metadata: unknown): string | null {
  if (!metadata || typeof metadata !== "object") return null;
  const record = metadata as Record<string, unknown>;
  const direct = record.original_id || record.originalId;
  if (typeof direct === "string" && direct.trim()) {
    return direct;
  }
  return readMetadataOriginalId(record.metadata);
}

function readObjectOriginalId(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const direct = record.original_id || record.originalId;
  if (typeof direct === "string" && direct.trim()) {
    return direct;
  }
  return readMetadataOriginalId(record.metadata);
}

function isRuntimeGeneratedId(value: string): boolean {
  return value.startsWith("msg_") || value.startsWith("response_");
}

export function resolveFeedbackResponseId(
  response: ChatRuntimeResponseCardData,
): string | null {
  const output = Array.isArray(response.output) ? response.output : [];

  for (let index = output.length - 1; index >= 0; index -= 1) {
    const message = output[index];
    if (message?.role === "assistant") {
      const originalId = readObjectOriginalId(message);
      if (originalId) return originalId;
    }
  }

  const responseOriginalId = readObjectOriginalId(response);
  if (responseOriginalId) return responseOriginalId;

  for (let index = output.length - 1; index >= 0; index -= 1) {
    const message = output[index];
    if (
      message?.role === "assistant" &&
      message.id &&
      !isRuntimeGeneratedId(message.id)
    ) {
      return message.id;
    }
  }

  if (response.id && !isRuntimeGeneratedId(response.id)) {
    return response.id;
  }

  return resolveFeedbackTraceId(response);
}

function readMetadataTraceId(metadata: unknown): string | null {
  if (!metadata || typeof metadata !== "object") return null;
  const record = metadata as Record<string, unknown>;
  const direct = record.trace_id || record.traceId;
  if (typeof direct === "string" && direct.trim()) {
    return direct;
  }
  return readMetadataTraceId(record.metadata);
}

function readObjectTraceId(value: unknown): string | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const direct = record.trace_id || record.traceId;
  if (typeof direct === "string" && direct.trim()) {
    return direct;
  }
  return readMetadataTraceId(record.metadata);
}

export function resolveFeedbackTraceId(
  response: ChatRuntimeResponseCardData,
): string | null {
  const direct = readObjectTraceId(response);
  if (direct) return direct;

  const output = Array.isArray(response.output) ? response.output : [];
  for (let index = output.length - 1; index >= 0; index -= 1) {
    const traceId = readObjectTraceId(output[index]);
    if (traceId) return traceId;
  }

  return null;
}

export interface ChatApprovalActionCardData {
  requestId: string;
  toolName: string;
  toolInput: Record<string, unknown>;
  triggerLabel: string;
  approveCommand: string;
  denyCommand: string;
  status?: "pending" | "approved" | "denied" | "timeout" | "superseded";
}

export type PlanClarificationKind =
  | "single_choice"
  | "multi_choice"
  | "text_input";

export interface PlanClarificationOption {
  id: string;
  label: string;
}

export interface ChatPlanClarificationCardData {
  card_type: "plan_clarification";
  kind: PlanClarificationKind;
  prompt: string;
  options?: PlanClarificationOption[];
}

export interface ChatPlanReviewCardData {
  card_type: "plan_review";
  plan_id: string;
  title: string;
  summary: string;
  steps: string[];
  risks: string[];
  verification: string[];
  open_questions: string[];
  confidence: number;
  status?: "pending" | "submitted";
}

export type ChatPlanInteractionCardData =
  | ChatPlanClarificationCardData
  | ChatPlanReviewCardData;

function isStringArray(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((item) => typeof item === "string")
  );
}

function normalizePlanInteractionCard(
  value: unknown,
): ChatPlanInteractionCardData | null {
  if (!value || typeof value !== "object") return null;
  const card = value as Record<string, unknown>;

  if (card.card_type === "plan_clarification") {
    const kind = card.kind;
    if (
      kind !== "single_choice" &&
      kind !== "multi_choice" &&
      kind !== "text_input"
    ) {
      return null;
    }
    if (typeof card.prompt !== "string" || !card.prompt.trim()) return null;
    const options = Array.isArray(card.options)
      ? card.options.filter(
          (option): option is PlanClarificationOption =>
            Boolean(option) &&
            typeof option === "object" &&
            typeof (option as PlanClarificationOption).id === "string" &&
            typeof (option as PlanClarificationOption).label === "string",
        )
      : undefined;
    return {
      card_type: "plan_clarification",
      kind,
      prompt: card.prompt,
      options,
    };
  }

  if (card.card_type === "plan_review") {
    if (
      typeof card.plan_id !== "string" ||
      typeof card.title !== "string" ||
      typeof card.summary !== "string" ||
      !isStringArray(card.steps) ||
      !isStringArray(card.risks) ||
      !isStringArray(card.verification) ||
      !isStringArray(card.open_questions) ||
      typeof card.confidence !== "number"
    ) {
      return null;
    }

    return {
      card_type: "plan_review",
      plan_id: card.plan_id,
      title: card.title,
      summary: card.summary,
      steps: card.steps,
      risks: card.risks,
      verification: card.verification,
      open_questions: card.open_questions,
      confidence: card.confidence,
      status: card.status === "submitted" ? "submitted" : undefined,
    };
  }

  return null;
}

export function extractPlanInteractionCard(
  value: unknown,
): ChatPlanInteractionCardData | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const direct = normalizePlanInteractionCard(record.plan_interaction_card);
  if (direct) return direct;

  const nested = extractPlanInteractionCard(record.metadata);
  if (nested) return nested;

  if (Array.isArray(record.output)) {
    for (const item of record.output) {
      const found = extractPlanInteractionCard(item);
      if (found) return found;
    }
  }

  return null;
}

export interface ChatTaskRunGroupCardData {
  runId: string;
  runIndex: number;
  taskName?: string;
  collapsedByDefault?: boolean;
  finalMessages: IAgentScopeRuntimeWebUIMessage[];
  stepMessages: IAgentScopeRuntimeWebUIMessage[];
  headerMeta?: ChatMessageHeaderMeta;
}

type TimestampSource = {
  timestamp?: unknown;
};

function normalizeEpochMs(value: number): number {
  return value < 1_000_000_000_000 ? value * 1000 : value;
}

function toTimestamp(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return normalizeEpochMs(value);
  }

  if (typeof value !== "string") return null;

  const trimmed = value.trim();
  if (!trimmed) return null;

  const numeric = Number(trimmed);
  if (Number.isFinite(numeric)) {
    return normalizeEpochMs(numeric);
  }

  const parsed = Date.parse(trimmed);
  return Number.isNaN(parsed) ? null : parsed;
}

export function resolveMessageTimestamp(
  message: TimestampSource,
): number | undefined {
  return toTimestamp(message.timestamp) ?? undefined;
}

export function resolveGroupTimestamp(
  messages: TimestampSource[],
): number | undefined {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const resolved = resolveMessageTimestamp(messages[index]);
    if (resolved) return resolved;
  }

  return undefined;
}

export function formatMessageTime(timestamp?: number): string {
  if (timestamp === undefined) return "";
  return dayjs(timestamp).format("MM-DD HH:mm");
}
