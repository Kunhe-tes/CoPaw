import classNames from "classnames";
import { MessageCircle, Send } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { message } from "antd";
import { feedbackApi } from "@/api/modules/feedback";
import type {
  FeedbackRecord,
  FeedbackSubmitPayload,
} from "@/api/types/feedback";
import { useIframeStore } from "@/stores/iframeStore";
import styles from "./index.module.less";
import { isResponseFeedbackUserAllowed } from "./whitelist";

const QUICK_OPTIONS = [
  "输出格式需调整",
  "分析维度需增删",
  "筛选逻辑不对",
  "其他想法",
];

export interface ResponseFeedbackTaskMeta {
  cronTaskName?: string | null;
  cronTaskId?: string | null;
}

export default function ResponseFeedbackCard(props: {
  responseId?: string | null;
  traceId?: string | null;
  chatId?: string | null;
  sessionId?: string | null;
  task?: ResponseFeedbackTaskMeta | null;
  existingFeedback?: FeedbackRecord | null;
  loadingExisting?: boolean;
  onFeedbackSaved?: (feedback: FeedbackRecord) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [feedbackId, setFeedbackId] = useState<number | null>(null);
  const [savedTraceId, setSavedTraceId] = useState<string | null>(null);
  const [selectedOptions, setSelectedOptions] = useState<string[]>([]);
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const userId = useIframeStore((state) => state.userId);
  const userName = useIframeStore((state) => state.userName);
  const bbk = useIframeStore((state) => state.bbk);
  const subBranchId = useIframeStore((state) => state.subBranchId);
  const positionId = useIframeStore((state) => state.positionId);
  const eligible = isResponseFeedbackUserAllowed(userId);
  const feedbackTargetKey = useMemo(
    () =>
      [
        props.responseId || "",
        props.traceId || "",
        props.chatId || "",
        props.sessionId || "",
      ].join("|"),
    [props.chatId, props.responseId, props.sessionId, props.traceId],
  );
  const lastFeedbackTargetKeyRef = useRef(feedbackTargetKey);

  useEffect(() => {
    if (selectedOptions.length === 0 && !submitted) {
      setExpanded(false);
    }
  }, [selectedOptions, submitted]);

  useEffect(() => {
    if (!eligible) {
      return;
    }

    const targetChanged =
      lastFeedbackTargetKeyRef.current !== feedbackTargetKey;
    if (targetChanged) {
      lastFeedbackTargetKeyRef.current = feedbackTargetKey;
    }

    if (props.loadingExisting) {
      return;
    }

    if (props.existingFeedback) {
      applyExistingFeedback(props.existingFeedback, props.traceId || null);
      return;
    }

    if (!targetChanged && submitted) {
      return;
    }

    setFeedbackId(null);
    setSavedTraceId(props.traceId || null);
    setSelectedOptions([]);
    setContent("");
    setSubmitted(false);
    setExpanded(false);
  }, [
    eligible,
    feedbackTargetKey,
    props.existingFeedback,
    props.loadingExisting,
    props.traceId,
    submitted,
  ]);

  const payload = useMemo<FeedbackSubmitPayload>(
    () => ({
      id: feedbackId,
      feedback_content: content.trim() || selectedOptions.join("；"),
      feedback_options: selectedOptions,
      response_id: props.responseId || null,
      trace_id: savedTraceId || props.traceId || null,
      chat_id: props.chatId || null,
      session_id: props.sessionId || null,
      cron_task_name: props.task?.cronTaskName || null,
      cron_task_id: props.task?.cronTaskId || null,
      feedback_user_name: userName || null,
      feedback_user_sap: userId || null,
      feedback_branch: bbk || null,
      feedback_sub_branch: subBranchId || null,
      feedback_position: positionId || null,
    }),
    [
      bbk,
      content,
      feedbackId,
      positionId,
      props.chatId,
      props.responseId,
      props.sessionId,
      props.task?.cronTaskId,
      props.task?.cronTaskName,
      props.traceId,
      savedTraceId,
      selectedOptions,
      subBranchId,
      userId,
      userName,
    ],
  );

  if (!eligible) return null;

  function applyExistingFeedback(
    existing: FeedbackRecord,
    fallbackTraceId: string | null,
  ) {
    setFeedbackId(existing.id);
    setSavedTraceId(existing.trace_id || fallbackTraceId);
    setSelectedOptions(existing.feedback_options || []);
    setContent(existing.feedback_content || "");
    setSubmitted(true);
    setExpanded(false);
  }

  const toggleOption = (option: string) => {
    if (submitted) return;
    setExpanded(true);
    setSelectedOptions((prev) =>
      prev.includes(option)
        ? prev.filter((item) => item !== option)
        : [...prev, option],
    );
  };

  const handleSubmit = async () => {
    if (!payload.feedback_content) {
      message.warning("请先选择或填写反馈内容");
      return;
    }
    setSubmitting(true);
    try {
      const result = await feedbackApi.submitFeedback(payload);
      const nextFeedback: FeedbackRecord = {
        id: result.feedback_id || feedbackId || 0,
        feedback_content: payload.feedback_content,
        feedback_options: payload.feedback_options || [],
        response_id: payload.response_id,
        trace_id: result.trace_id || savedTraceId || props.traceId || null,
        chat_id: payload.chat_id,
        session_id: payload.session_id,
        cron_task_name: payload.cron_task_name,
        cron_task_id: payload.cron_task_id,
        feedback_user_name: payload.feedback_user_name,
        feedback_user_sap: payload.feedback_user_sap,
        feedback_branch: payload.feedback_branch,
        feedback_sub_branch: payload.feedback_sub_branch,
        feedback_position: payload.feedback_position,
      };
      setFeedbackId(nextFeedback.id);
      setSavedTraceId(nextFeedback.trace_id || null);
      setSubmitted(true);
      setExpanded(false);
      props.onFeedbackSaved?.(nextFeedback);
      message.success("反馈已提交");
    } catch {
      message.error("反馈提交失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.feedbackCard}>
      <div className={styles.header}>
        <div className={styles.title}>
          <MessageCircle size={14} />
          <span>对任务结果还满意吗？请告诉我你的修改意见，我将持续优化。</span>
        </div>
      </div>
      {props.loadingExisting && !submitted ? (
        <div className={styles.loadingState}>正在加载历史反馈...</div>
      ) : submitted ? (
        <div className={styles.successState}>
          <span>反馈已收到，我们会尽快评估你的建议，感谢支持！</span>
        </div>
      ) : props.loadingExisting ? null : (
        <>
          <div className={styles.options}>
            {QUICK_OPTIONS.map((option) => (
              <button
                className={classNames(styles.optionButton, {
                  [styles.optionButtonSelected]:
                    selectedOptions.includes(option),
                })}
                key={option}
                onClick={() => toggleOption(option)}
                type="button"
              >
                {option}
              </button>
            ))}
          </div>
          <div
            className={classNames(styles.inputArea, {
              [styles.inputAreaCollapsed]: !expanded,
            })}
          >
            <textarea
              className={styles.textarea}
              maxLength={5000}
              onChange={(event) => setContent(event.target.value)}
              placeholder="具体说说你希望怎么调整？比如：&#10;- 希望增加客户年龄分层的维度&#10;- 出金阈值建议改成近15日而不是7日&#10;- 结论部分希望更简短，直接给行动建议"
              value={content}
            />

            <div className={styles.actions}>
              <span className={styles.hint}>
                详细描述有助于我们更精准地优化，最多5000字。
              </span>
              <button
                className={styles.submitButton}
                disabled={submitting}
                onClick={handleSubmit}
                type="button"
              >
                <Send size={12} />
                {submitting ? "提交中..." : "提交反馈"}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
