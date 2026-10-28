import type { IAgentScopeRuntimeWebUIMessage } from "@/components/agentscope-chat";
import type { Message } from "@/api/types/chat";
import { readStopAppendMetadata } from "../stopAppend";

const RESPONSE_CARD = "AgentScopeRuntimeResponseCard";
const BOUNDARY_CARD = "ConversationCompactionBoundary";
const FEEDBACK_CARD = "ResponseFeedback";
export const INLINE_COMPACTION_TYPE = "conversation_compaction_boundary";

type HistoryMessage = IAgentScopeRuntimeWebUIMessage & {
  history?: boolean;
  historyAnchorIds?: string[];
};

function fragmentIdentity(message: Message): string | null {
  if (message.role === "user" || typeof message.id !== "string") return null;
  const metadata = message.metadata as Record<string, unknown> | undefined;
  if (!metadata || metadata.original_id !== message.id) return null;

  const serialized = JSON.stringify([
    message.role,
    message.type,
    message.content,
    metadata.metadata,
  ]);
  let hash = 2166136261;
  for (let index = 0; index < serialized.length; index += 1) {
    hash = Math.imul(hash ^ serialized.charCodeAt(index), 16777619);
  }
  return `${message.id}:fragment:${(hash >>> 0).toString(16)}`;
}

/** Old servers assign every runtime fragment its source Msg ID. */
export function normalizeHistoryMessages(messages: Message[]): Message[] {
  return messages.map((message) => {
    const id = fragmentIdentity(message);
    if (!id) return message;
    return { ...message, id };
  });
}

export function historyMessageMetadata(
  message: Message,
): Record<string, unknown> {
  const metadata =
    message.metadata && typeof message.metadata === "object"
      ? (message.metadata as Record<string, unknown>)
      : {};
  const nested = metadata.metadata;
  return nested && typeof nested === "object"
    ? { ...metadata, ...(nested as Record<string, unknown>) }
    : metadata;
}

function isIndependentOutput(message: Message): boolean {
  if (readStopAppendMetadata(message)) return true;
  return Boolean(historyMessageMetadata(message).cron_task);
}

function responseTaskRunId(messages: Message[]): string | null | undefined {
  const runIds = new Set(
    messages
      .map((message) => historyMessageMetadata(message).task_run_id)
      .filter((runId): runId is string => typeof runId === "string" && !!runId),
  );
  if (runIds.size > 1) return undefined;
  return runIds.values().next().value ?? null;
}

function canMergeResponses(older: Message[], newer: Message[]): boolean {
  const olderRunId = responseTaskRunId(older);
  const newerRunId = responseTaskRunId(newer);
  if (olderRunId === null && newerRunId === null) return true;
  return typeof olderRunId === "string" && olderRunId === newerRunId;
}

function responseOutput(message: HistoryMessage): Message[] | null {
  if (
    !message.history ||
    message.role !== "assistant" ||
    message.msgStatus === "generating"
  )
    return null;
  const card = message.cards?.[0];
  if (card?.code !== RESPONSE_CARD || !Array.isArray(card.data?.output))
    return null;
  const output = card.data.output as Message[];
  return output.length && !output.some(isIndependentOutput) ? output : null;
}

function inlineBoundary(message: HistoryMessage): Message {
  return {
    id: message.id,
    role: "system",
    type: INLINE_COMPACTION_TYPE,
    status: "completed",
    content: [
      { type: "data", status: "completed", data: message.cards?.[0].data },
    ],
  };
}

function uniqueOutput(messages: Message[]): Message[] {
  const seen = new Set<string>();
  return messages.filter((message) => {
    if (typeof message.id !== "string") return true;
    if (seen.has(message.id)) return false;
    seen.add(message.id);
    return true;
  });
}

function mergeResponsePair(
  older: HistoryMessage,
  separators: HistoryMessage[],
  newer: HistoryMessage,
): HistoryMessage {
  const olderCard = older.cards![0];
  const newerCard = newer.cards![0];
  const data = {
    ...newerCard.data,
    output: uniqueOutput([
      ...olderCard.data.output,
      ...separators.map(inlineBoundary),
      ...newerCard.data.output,
    ]),
    headerMeta: olderCard.data.headerMeta || newerCard.data.headerMeta,
    planReviewCard:
      newerCard.data.planReviewCard || olderCard.data.planReviewCard,
  };
  const extraCards = new Map<
    string,
    NonNullable<HistoryMessage["cards"]>[number]
  >();
  for (const card of [...(older.cards || []), ...(newer.cards || [])]) {
    if (card.code !== RESPONSE_CARD && card.code !== FEEDBACK_CARD) {
      extraCards.set(`${card.code}:${JSON.stringify(card.data)}`, card);
    }
  }
  const feedback = [...(newer.cards || []), ...(older.cards || [])].find(
    (card) => card.code === FEEDBACK_CARD,
  );
  return {
    ...newer,
    historyAnchorIds: Array.from(
      new Set([
        older.id,
        ...(older.historyAnchorIds || []),
        ...(newer.historyAnchorIds || []),
      ]),
    ).filter((id) => id !== newer.id),
    cards: [
      { ...newerCard, data },
      ...extraCards.values(),
      ...(feedback ? [{ ...feedback, data }] : []),
    ],
  };
}

/** HTTP pages and compaction dividers are not user-turn boundaries. */
export function mergeHistoryResponses(
  messages: IAgentScopeRuntimeWebUIMessage[],
): IAgentScopeRuntimeWebUIMessage[] {
  const result: HistoryMessage[] = [];
  for (const message of messages as HistoryMessage[]) {
    if (responseOutput(message)) {
      let previousIndex = result.length - 1;
      while (
        previousIndex >= 0 &&
        result[previousIndex].cards?.[0]?.code === BOUNDARY_CARD
      ) {
        previousIndex -= 1;
      }
      const previous = result[previousIndex];
      const previousOutput = previous && responseOutput(previous);
      const currentOutput = responseOutput(message);
      if (
        previousOutput &&
        currentOutput &&
        canMergeResponses(previousOutput, currentOutput)
      ) {
        result.splice(
          previousIndex,
          result.length - previousIndex,
          mergeResponsePair(previous, result.slice(previousIndex + 1), message),
        );
        continue;
      }
    }
    result.push(message);
  }
  return result;
}

export function resolveHistoryAnchorId(
  messages: IAgentScopeRuntimeWebUIMessage[],
  anchorId: string,
): string {
  return (
    (messages as HistoryMessage[]).find(
      (message) =>
        message.id === anchorId || message.historyAnchorIds?.includes(anchorId),
    )?.id || anchorId
  );
}
