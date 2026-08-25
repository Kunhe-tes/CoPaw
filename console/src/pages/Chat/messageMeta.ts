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
  planReviewCard?: ChatPlanReviewCardData;
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
  | "text"
  | "form";

export interface PlanClarificationOption {
  id: string;
  label: string;
}

export type PlanClarificationFieldType =
  | "text"
  | "single_choice"
  | "multi_choice";

export interface PlanClarificationField {
  id: string;
  label: string;
  type: PlanClarificationFieldType;
  options?: PlanClarificationOption[];
  placeholder?: string;
  required?: boolean;
  description?: string;
}

export interface ChatPlanClarificationCardData {
  card_type: "plan_clarification";
  kind: PlanClarificationKind;
  prompt: string;
  options?: PlanClarificationOption[];
  form_id?: string;
  fields?: PlanClarificationField[];
  allow_custom_response?: boolean;
}

export type PlanReviewDecision = "revise" | "execute" | "exit_plan";

export interface ChatPlanReviewCardData {
  card_type: "plan_review";
  plan_id: string;
  title: string;
  summary: string;
  steps: string[];
  risks: string[];
  verification: string[];
  status?: "pending" | "submitted";
  submitted_decision?: PlanReviewDecision;
  feedback?: string;
}

export interface ChatGoalCompletionCriterion {
  requirement: string;
  observable_assertion: string;
  verification_method: string;
  expected_outcome: string;
}

export interface ChatGoalProposalCardData {
  card_type: "goal_proposal";
  objective: string;
  completion_criteria: ChatGoalCompletionCriterion[];
  constraints: { must_preserve: string[]; must_not_do: string[] };
  autonomy_boundary: string;
}

export type ChatPlanInteractionCardData =
  | ChatPlanClarificationCardData
  | ChatPlanReviewCardData
  | ChatGoalProposalCardData;

function isStringArray(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((item) => typeof item === "string")
  );
}

function isPlanClarificationOption(
  value: unknown,
): value is PlanClarificationOption {
  return (
    Boolean(value) &&
    typeof value === "object" &&
    typeof (value as PlanClarificationOption).id === "string" &&
    typeof (value as PlanClarificationOption).label === "string"
  );
}

function isPlanReviewDecision(value: unknown): value is PlanReviewDecision {
  return value === "revise" || value === "execute" || value === "exit_plan";
}

function normalizeGoalCompletionCriteria(
  value: unknown,
): ChatGoalCompletionCriterion[] | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  const required = [
    "requirement",
    "observable_assertion",
    "verification_method",
    "expected_outcome",
  ] as const;
  const normalized = value.map((item) => {
    if (!item || typeof item !== "object") return null;
    const record = item as Record<string, unknown>;
    if (
      required.some(
        (key) => typeof record[key] !== "string" || !record[key].trim(),
      )
    ) {
      return null;
    }
    return Object.fromEntries(
      required.map((key) => [key, record[key] as string]),
    ) as ChatGoalCompletionCriterion;
  });
  return normalized.every(Boolean)
    ? (normalized as ChatGoalCompletionCriterion[])
    : null;
}

function normalizeGoalStringList(value: unknown): string[] | null {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    return null;
  }
  return value.map((item) => item.trim()).filter(Boolean);
}

function normalizePlanClarificationFields(
  value: unknown,
): PlanClarificationField[] | null {
  if (!Array.isArray(value) || value.length === 0) return null;

  const normalized = value
    .map((field): PlanClarificationField | null => {
      if (!field || typeof field !== "object") return null;
      const record = field as Record<string, unknown>;
      const type = record.type;
      if (
        typeof record.id !== "string" ||
        typeof record.label !== "string" ||
        (type !== "single_choice" && type !== "multi_choice" && type !== "text")
      ) {
        return null;
      }

      const options = Array.isArray(record.options)
        ? record.options.filter(isPlanClarificationOption)
        : undefined;
      if (
        (type === "single_choice" || type === "multi_choice") &&
        (!options || options.length === 0)
      ) {
        return null;
      }

      return {
        id: record.id,
        label: record.label,
        type,
        options,
        placeholder:
          typeof record.placeholder === "string"
            ? record.placeholder
            : undefined,
        required: record.required === true,
        description:
          typeof record.description === "string"
            ? record.description
            : undefined,
      };
    })
    .filter((field): field is PlanClarificationField => Boolean(field));

  return normalized.length === value.length ? normalized : null;
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
      kind !== "text" &&
      kind !== "form"
    ) {
      return null;
    }
    if (typeof card.prompt !== "string" || !card.prompt.trim()) return null;
    const options = Array.isArray(card.options)
      ? card.options.filter(isPlanClarificationOption)
      : undefined;
    const fields = normalizePlanClarificationFields(card.fields);
    if (kind === "form" && !fields) return null;
    return {
      card_type: "plan_clarification",
      kind,
      prompt: card.prompt,
      options,
      form_id: typeof card.form_id === "string" ? card.form_id : undefined,
      fields: kind === "form" ? fields || undefined : undefined,
      allow_custom_response: card.allow_custom_response !== false,
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
      "open_questions" in card ||
      "confidence" in card
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
      status: card.status === "submitted" ? "submitted" : undefined,
      submitted_decision: isPlanReviewDecision(card.submitted_decision)
        ? card.submitted_decision
        : undefined,
      feedback: typeof card.feedback === "string" ? card.feedback : undefined,
    };
  }

  if (card.card_type === "goal_proposal") {
    const criteria = normalizeGoalCompletionCriteria(card.completion_criteria);
    const constraints = card.constraints;
    if (
      typeof card.objective !== "string" ||
      !card.objective.trim() ||
      !criteria ||
      !constraints ||
      typeof constraints !== "object" ||
      !normalizeGoalStringList((constraints as Record<string, unknown>).must_preserve) ||
      !normalizeGoalStringList((constraints as Record<string, unknown>).must_not_do) ||
      typeof card.autonomy_boundary !== "string" ||
      !card.autonomy_boundary.trim()
    ) {
      return null;
    }
    return {
      card_type: "goal_proposal",
      objective: card.objective.trim(),
      completion_criteria: criteria,
      constraints: {
        must_preserve: normalizeGoalStringList(
          (constraints as Record<string, unknown>).must_preserve,
        )!,
        must_not_do: normalizeGoalStringList(
          (constraints as Record<string, unknown>).must_not_do,
        )!,
      },
      autonomy_boundary: card.autonomy_boundary.trim(),
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
