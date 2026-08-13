import AgentScopeRuntimeResponseCard from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/AgentScopeRuntime/Response/Card";
import type { FeedbackRecord } from "@/api/types/feedback";
import { useIframeStore } from "@/stores/iframeStore";
import ChatMessageMeta from "../ChatMessageMeta";
import {
  resolveFeedbackResponseId,
  resolveFeedbackTraceId,
  type ChatRuntimeResponseCardData,
} from "../../messageMeta";
import styles from "../ChatMessageMeta/index.module.less";
import ResponseFeedbackCard, {
  type ResponseFeedbackTaskMeta,
} from "../ResponseFeedbackCard";
import { PlanReviewMessageCard } from "../PlanInteractionCards";

const ASSISTANT_MESSAGE_NAME = "小助 Claw";
const ORIGIN_Y_ASSISTANT_MESSAGE_NAME = "AI伙伴";
const ORIGIN_Y_SOURCE = "RMASSIST";

type AssistantMessageContext = {
  hideMenu?: boolean;
  source?: string | null;
};

export function getAssistantMessageName(
  search: string = window.location.search,
  context?: AssistantMessageContext,
): string {
  const urlParams = new URLSearchParams(search);
  const isOriginYContext =
    context?.hideMenu === true && context?.source === ORIGIN_Y_SOURCE;
  return urlParams.get("origin") === "Y" || isOriginYContext
    ? ORIGIN_Y_ASSISTANT_MESSAGE_NAME
    : ASSISTANT_MESSAGE_NAME;
}

export default function RuntimeResponseCard(props: {
  data: ChatRuntimeResponseCardData;
  isLast?: boolean;
}) {
  const hideMenu = useIframeStore((state) => state.hideMenu);
  const source = useIframeStore((state) => state.source);

  return (
    <div className={styles.messageBlockStart}>
      <ChatMessageMeta
        align="start"
        name={getAssistantMessageName(window.location.search, {
          hideMenu,
          source,
        })}
        timestamp={props.data.headerMeta?.timestamp}
      />
      <AgentScopeRuntimeResponseCard
        beforeActions={
          props.data.planReviewCard && (
            <PlanReviewMessageCard data={props.data.planReviewCard} />
          )
        }
        data={props.data}
        isLast={props.isLast}
      />
    </div>
  );
}

export function RuntimeResponseFeedbackCard(props: {
  data: ChatRuntimeResponseCardData;
  showFeedback?: boolean;
  chatId?: string | null;
  sessionId?: string | null;
  task?: ResponseFeedbackTaskMeta | null;
  existingFeedback?: FeedbackRecord | null;
  loadingFeedback?: boolean;
  onFeedbackSaved?: (
    feedback: FeedbackRecord,
    response: ChatRuntimeResponseCardData,
  ) => void;
}) {
  const shouldShowFeedback =
    props.showFeedback !== false &&
    props.data.status === "completed" &&
    !props.data.error &&
    Boolean(props.chatId || props.sessionId);
  const feedbackResponseId = resolveFeedbackResponseId(props.data);
  const feedbackTraceId = resolveFeedbackTraceId(props.data);

  if (!shouldShowFeedback) return null;

  return (
    <ResponseFeedbackCard
      chatId={props.chatId}
      existingFeedback={props.existingFeedback}
      loadingExisting={props.loadingFeedback}
      onFeedbackSaved={(feedback) =>
        props.onFeedbackSaved?.(feedback, props.data)
      }
      responseId={feedbackResponseId}
      sessionId={props.sessionId}
      task={props.task}
      traceId={feedbackTraceId}
    />
  );
}
