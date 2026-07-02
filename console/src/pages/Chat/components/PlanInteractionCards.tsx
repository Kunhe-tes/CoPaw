import { useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  ClipboardCheck,
  CornerDownLeft,
} from "lucide-react";
import {
  ChatAnywhereSessionsContext,
  type IAgentScopeRuntimeWebUIMessage,
} from "@/components/agentscope-chat";
import { ChatAnywhereMessagesContext } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/ChatAnywhereMessagesContext";
import { emit } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/useChatAnywhereEventEmitter";
import type {
  ChatRuntimeResponseCardData,
  ChatPlanClarificationCardData,
  PlanClarificationField,
  ChatPlanReviewCardData,
  PlanClarificationOption,
} from "../messageMeta";
import {
  resolveFeedbackResponseId,
  resolveFeedbackTraceId,
} from "../messageMeta";
import styles from "./PlanInteractionCards.module.less";
import { useContextSelector } from "use-context-selector";

const PLAN_CLARIFICATION_STORAGE_KEY = "copaw_submitted_plan_clarifications";
const PLAN_CLARIFICATION_DISMISSAL_STORAGE_KEY =
  "copaw_dismissed_plan_clarifications";
const PLAN_CLARIFICATION_SEEN_STORAGE_KEY =
  "swe_seen_plan_clarification_instances";
const PLAN_REVIEW_STORAGE_KEY = "copaw_submitted_plan_reviews";
const PLAN_INTERACTION_CARD_CODE = "PlanInteraction";
const RUNTIME_RESPONSE_CARD_CODE = "AgentScopeRuntimeResponseCard";

function loadSubmittedInteractionKeys(storageKey: string): Set<string> {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(
      parsed.filter((item): item is string => typeof item === "string"),
    );
  } catch {
    return new Set();
  }
}

function storeSubmittedInteractionKey(storageKey: string, key: string): void {
  if (!key) return;
  const submittedIds = loadSubmittedInteractionKeys(storageKey);
  submittedIds.add(key);
  try {
    sessionStorage.setItem(
      storageKey,
      JSON.stringify(Array.from(submittedIds)),
    );
  } catch {
    return;
  }
}

function loadSubmittedPlanIds(): Set<string> {
  return loadSubmittedInteractionKeys(PLAN_REVIEW_STORAGE_KEY);
}

function storeSubmittedPlanId(planId: string): void {
  storeSubmittedInteractionKey(PLAN_REVIEW_STORAGE_KEY, planId);
}

function optionLabels(
  options: PlanClarificationOption[] | undefined,
  selectedIds: string[],
): string {
  const labelById = new Map(
    (options || []).map((item) => [item.id, item.label]),
  );
  return selectedIds
    .map((id) => labelById.get(id) || id)
    .filter(Boolean)
    .join(", ");
}

function hasFormValue(value: string | string[] | undefined): boolean {
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  return Boolean(value && value.trim());
}

function formatFormFieldValue(
  field: PlanClarificationField,
  value: string | string[] | undefined,
): string {
  if (!hasFormValue(value)) return "";
  const optionLabelById = new Map(
    (field.options || []).map((item) => [item.id, item.label]),
  );
  if (Array.isArray(value)) {
    return value
      .map((item) => optionLabelById.get(item) || item)
      .filter(Boolean)
      .join(", ");
  }
  return optionLabelById.get(value) || value;
}

function collectFormValues(
  fields: PlanClarificationField[],
  values: Record<string, string | string[]>,
): Record<string, string | string[]> {
  return Object.fromEntries(
    fields
      .map((field) => [field.id, values[field.id]] as const)
      .filter(([, value]) => hasFormValue(value)),
  );
}

function isPlanClarificationCardData(
  data: unknown,
): data is ChatPlanClarificationCardData {
  return (
    Boolean(data) &&
    typeof data === "object" &&
    (data as { card_type?: unknown }).card_type === "plan_clarification"
  );
}

function isRuntimeResponseCardData(
  data: unknown,
): data is ChatRuntimeResponseCardData {
  return (
    Boolean(data) &&
    typeof data === "object" &&
    Array.isArray((data as { output?: unknown }).output)
  );
}

function createPlanClarificationFingerprint(
  data: ChatPlanClarificationCardData,
): string {
  return JSON.stringify({
    kind: data.kind,
    prompt: data.prompt,
    form_id: data.form_id,
    options: data.options || [],
    fields: data.fields || [],
    allow_custom_response: data.allow_custom_response === true,
  });
}

function resolveClarificationSourceKey(
  cards: IAgentScopeRuntimeWebUIMessage["cards"],
  data: ChatPlanClarificationCardData,
): string | null {
  const responseCard = (cards || []).find(
    (card) =>
      card.code === RUNTIME_RESPONSE_CARD_CODE &&
      isRuntimeResponseCardData(card.data),
  );
  if (!responseCard || !isRuntimeResponseCardData(responseCard.data)) {
    return null;
  }

  const responseId = resolveFeedbackResponseId(responseCard.data);
  if (responseId) {
    return JSON.stringify({
      source: "response",
      response_id: responseId,
      clarification: createPlanClarificationFingerprint(data),
    });
  }

  const traceId = resolveFeedbackTraceId(responseCard.data);
  if (traceId) {
    return JSON.stringify({
      source: "trace",
      trace_id: traceId,
      clarification: createPlanClarificationFingerprint(data),
    });
  }

  return null;
}

function findLatestPlanClarificationCard(
  messages: IAgentScopeRuntimeWebUIMessage[],
): {
  data: ChatPlanClarificationCardData;
  instanceKey: string;
  sourceKey: string | null;
} | null {
  for (
    let messageIndex = messages.length - 1;
    messageIndex >= 0;
    messageIndex -= 1
  ) {
    const message = messages[messageIndex];
    const cards = message?.cards || [];
    for (let cardIndex = cards.length - 1; cardIndex >= 0; cardIndex -= 1) {
      const card = cards[cardIndex];
      if (
        card.code === PLAN_INTERACTION_CARD_CODE &&
        isPlanClarificationCardData(card.data)
      ) {
        return {
          data: card.data,
          instanceKey: `${message.id}:${card.id || card.code}:${cardIndex}`,
          sourceKey: resolveClarificationSourceKey(cards, card.data),
        };
      }
    }
  }
  return null;
}

function createPlanClarificationSubmissionKey(
  data: ChatPlanClarificationCardData,
  sessionId: string | undefined,
  stableSourceKey: string | null = null,
  fallbackKey: string | null = null,
): string {
  return JSON.stringify({
    session_id: sessionId || "unknown",
    clarification:
      stableSourceKey ||
      (fallbackKey
        ? JSON.stringify({
            source: "instance",
            instance_key: fallbackKey,
          })
        : createPlanClarificationFingerprint(data)),
  });
}

function createPlanClarificationDismissalKey(
  sessionId: string | undefined,
  stableSourceKey: string | null,
  fallbackKey: string,
): string {
  return JSON.stringify({
    session_id: sessionId || "unknown",
    clarification:
      stableSourceKey ||
      JSON.stringify({
        source: "content",
        fingerprint: fallbackKey,
      }),
  });
}

function createPlanClarificationSeenKey(
  data: ChatPlanClarificationCardData,
  sessionId: string | undefined,
  stableSourceKey: string | null,
  fallbackKey: string | null,
): string {
  return JSON.stringify({
    session_id: sessionId || "unknown",
    clarification:
      stableSourceKey ||
      (fallbackKey
        ? JSON.stringify({
            source: "instance",
            instance_key: fallbackKey,
          })
        : createPlanClarificationFingerprint(data)),
  });
}

function boundedIndex(index: number, count: number): number {
  if (count <= 0) return 0;
  return Math.min(Math.max(index, 0), count - 1);
}

function isTextTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement
  );
}

function ChoiceRows({
  options,
  selectedIds,
  focusedIndex,
  allowCustomResponse = false,
  customActive = false,
  onFocusIndexChange,
  onSelect,
  onCustomSelect,
}: {
  options: PlanClarificationOption[];
  selectedIds: string[];
  focusedIndex: number;
  allowCustomResponse?: boolean;
  customActive?: boolean;
  onFocusIndexChange: (index: number) => void;
  onSelect: (optionId: string) => void;
  onCustomSelect?: () => void;
}) {
  const rowRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const allRowsCount = options.length + (allowCustomResponse ? 1 : 0);

  useEffect(() => {
    const focusedRow = rowRefs.current[focusedIndex];
    if (typeof focusedRow?.scrollIntoView === "function") {
      focusedRow.scrollIntoView({ block: "nearest" });
    }
  }, [focusedIndex]);

  return (
    <div className={styles.choiceOptionsViewport}>
      {options.map((option, index) => {
        const selected = selectedIds.includes(option.id);
        const focused = focusedIndex === index;
        return (
          <button
            ref={(node) => {
              rowRefs.current[index] = node;
            }}
            key={option.id}
            type="button"
            className={[
              styles.optionRow,
              focused ? styles.optionRowFocused : "",
              selected ? styles.optionRowSelected : "",
            ]
              .filter(Boolean)
              .join(" ")}
            aria-current={focused ? "true" : undefined}
            aria-pressed={selected}
            onMouseEnter={() => onFocusIndexChange(index)}
            onFocus={() => onFocusIndexChange(index)}
            onClick={() => onSelect(option.id)}
          >
            <span className={styles.optionNumber}>{index + 1}.</span>
            <span className={styles.optionLabel}>{option.label}</span>
            {selected ? <Check aria-hidden="true" size={15} /> : null}
            {focused ? (
              <ChevronsUpDown
                aria-hidden="true"
                className={styles.optionFocusIcon}
                size={14}
              />
            ) : null}
          </button>
        );
      })}
      {allowCustomResponse ? (
        <button
          ref={(node) => {
            rowRefs.current[allRowsCount - 1] = node;
          }}
          type="button"
          className={[
            styles.optionRow,
            focusedIndex === allRowsCount - 1 ? styles.optionRowFocused : "",
            customActive ? styles.optionRowSelected : "",
          ]
            .filter(Boolean)
            .join(" ")}
          aria-current={focusedIndex === allRowsCount - 1 ? "true" : undefined}
          aria-pressed={customActive}
          onMouseEnter={() => onFocusIndexChange(allRowsCount - 1)}
          onFocus={() => onFocusIndexChange(allRowsCount - 1)}
          onClick={onCustomSelect}
        >
          <span className={styles.optionNumber}>{allRowsCount}.</span>
          <span className={styles.optionLabel}>自定义回复</span>
          {customActive ? <Check aria-hidden="true" size={15} /> : null}
          {focusedIndex === allRowsCount - 1 ? (
            <ChevronsUpDown
              aria-hidden="true"
              className={styles.optionFocusIcon}
              size={14}
            />
          ) : null}
        </button>
      ) : null}
    </div>
  );
}

export function PlanClarificationCard({
  data,
  cardInstanceKey,
  cardSourceKey,
}: {
  data: ChatPlanClarificationCardData;
  cardInstanceKey?: string;
  cardSourceKey?: string | null;
}) {
  const currentSessionId = useContextSelector(
    ChatAnywhereSessionsContext,
    (value) => value.currentSessionId,
  );
  const [singleChoice, setSingleChoice] = useState<string>("");
  const [multiChoice, setMultiChoice] = useState<string[]>([]);
  const [textInput, setTextInput] = useState("");
  const [customActive, setCustomActive] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(0);
  const [activeStep, setActiveStep] = useState(0);
  const [formValues, setFormValues] = useState<
    Record<string, string | string[]>
  >({});
  const cardRef = useRef<HTMLElement | null>(null);
  const displayedRef = useRef(false);
  const resolvedSessionId =
    currentSessionId ||
    (window as Window & { currentSessionId?: string }).currentSessionId;
  const submissionKey = useMemo(
    () =>
      createPlanClarificationSubmissionKey(
        data,
        resolvedSessionId,
        cardSourceKey || null,
        cardInstanceKey || null,
      ),
    [cardInstanceKey, cardSourceKey, data, resolvedSessionId],
  );
  const dismissalKey = useMemo(
    () =>
      createPlanClarificationDismissalKey(
        resolvedSessionId,
        cardSourceKey || null,
        createPlanClarificationFingerprint(data),
      ),
    [cardSourceKey, data, resolvedSessionId],
  );
  const seenKey = useMemo(
    () =>
      createPlanClarificationSeenKey(
        data,
        resolvedSessionId,
        cardSourceKey || null,
        cardInstanceKey || null,
      ),
    [cardInstanceKey, cardSourceKey, data, resolvedSessionId],
  );
  const interactionResetKey = cardInstanceKey || dismissalKey;
  const [submitted, setSubmitted] = useState(() =>
    loadSubmittedInteractionKeys(PLAN_CLARIFICATION_STORAGE_KEY).has(
      submissionKey,
    ),
  );
  const [dismissed, setDismissed] = useState(() =>
    loadSubmittedInteractionKeys(PLAN_CLARIFICATION_DISMISSAL_STORAGE_KEY).has(
      dismissalKey,
    ),
  );
  const [alreadySeen, setAlreadySeen] = useState(() =>
    loadSubmittedInteractionKeys(PLAN_CLARIFICATION_SEEN_STORAGE_KEY).has(
      seenKey,
    ),
  );
  const options = data.options || [];
  const fields = data.fields || [];
  const allowsCustomText =
    data.kind === "text" || data.allow_custom_response === true;
  const totalSteps =
    data.kind === "form"
      ? fields.length + (data.allow_custom_response ? 1 : 0)
      : 1;
  const boundedStep = boundedIndex(activeStep, totalSteps);
  const activeField =
    data.kind === "form" && boundedStep < fields.length
      ? fields[boundedStep]
      : undefined;
  const isSupplementStep =
    data.kind === "form" && !activeField && data.allow_custom_response === true;
  const activeOptions =
    activeField?.type === "single_choice" ||
    activeField?.type === "multi_choice"
      ? activeField.options || []
      : options;
  const activeSelectedIds = activeField
    ? Array.isArray(formValues[activeField.id])
      ? (formValues[activeField.id] as string[])
      : typeof formValues[activeField.id] === "string"
      ? [formValues[activeField.id] as string]
      : []
    : data.kind === "single_choice"
    ? singleChoice
      ? [singleChoice]
      : []
    : data.kind === "multi_choice"
    ? multiChoice
    : [];
  const selectedIds =
    data.kind === "single_choice"
      ? singleChoice
        ? [singleChoice]
        : []
      : data.kind === "multi_choice"
      ? multiChoice
      : [];
  const trimmedText = textInput.trim();
  const effectiveChoiceText = customActive ? trimmedText : "";
  const requiredFormFieldsSatisfied = fields.every(
    (field) => !field.required || hasFormValue(formValues[field.id]),
  );
  const formQueryLines = fields
    .map((field) => {
      const formattedValue = formatFormFieldValue(field, formValues[field.id]);
      if (!formattedValue) return "";
      return `${field.label}: ${formattedValue}`;
    })
    .filter(Boolean);
  const disabled =
    data.kind === "text"
      ? !trimmedText
      : data.kind === "form"
      ? !requiredFormFieldsSatisfied ||
        [...formQueryLines, trimmedText].filter(Boolean).length === 0
      : selectedIds.length === 0 && !effectiveChoiceText;
  const currentFieldComplete = activeField
    ? !activeField.required || hasFormValue(formValues[activeField.id])
    : true;
  const isFinalStep = boundedStep >= totalSteps - 1;
  const canGoNext = !isFinalStep && currentFieldComplete;
  const pageTitle =
    data.kind === "form" ? activeField?.label || "补充说明" : data.prompt;
  const showChoiceRows =
    !customActive &&
    (data.kind === "single_choice" ||
      data.kind === "multi_choice" ||
      activeField?.type === "single_choice" ||
      activeField?.type === "multi_choice");
  const showCustomInput =
    data.kind === "text" || customActive || isSupplementStep;

  useEffect(() => {
    setSubmitted(
      loadSubmittedInteractionKeys(PLAN_CLARIFICATION_STORAGE_KEY).has(
        submissionKey,
      ),
    );
    setDismissed(
      loadSubmittedInteractionKeys(
        PLAN_CLARIFICATION_DISMISSAL_STORAGE_KEY,
      ).has(dismissalKey),
    );
    setAlreadySeen(
      loadSubmittedInteractionKeys(PLAN_CLARIFICATION_SEEN_STORAGE_KEY).has(
        seenKey,
      ),
    );
    displayedRef.current = false;
    setSingleChoice("");
    setMultiChoice([]);
    setTextInput("");
    setCustomActive(false);
    setFormValues({});
    setFocusedIndex(0);
    setActiveStep(0);
  }, [dismissalKey, interactionResetKey, seenKey, submissionKey]);

  useEffect(() => {
    if (submitted || dismissed || alreadySeen) return;
    displayedRef.current = true;
  }, [alreadySeen, dismissed, interactionResetKey, submitted]);

  useEffect(() => {
    const handleUserSubmit = () => {
      if (!displayedRef.current || submitted || dismissed || alreadySeen)
        return;
      storeSubmittedInteractionKey(
        PLAN_CLARIFICATION_SEEN_STORAGE_KEY,
        seenKey,
      );
      setAlreadySeen(true);
    };

    document.addEventListener("handleSubmit", handleUserSubmit);
    return () => {
      document.removeEventListener("handleSubmit", handleUserSubmit);
    };
  }, [alreadySeen, dismissed, seenKey, submitted]);

  useEffect(() => {
    if (submitted || dismissed || alreadySeen || !showChoiceRows) return;
    cardRef.current?.focus({ preventScroll: true });
  }, [
    alreadySeen,
    boundedStep,
    dismissed,
    interactionResetKey,
    showChoiceRows,
    submitted,
  ]);

  useEffect(() => {
    setFocusedIndex(0);
  }, [boundedStep]);

  const handleDismiss = () => {
    storeSubmittedInteractionKey(
      PLAN_CLARIFICATION_DISMISSAL_STORAGE_KEY,
      dismissalKey,
    );
    setDismissed(true);
  };

  const handleSubmit = (selectedOverride?: string[]) => {
    const effectiveSelectedIds = selectedOverride || selectedIds;
    const effectiveSelectedLabels = optionLabels(options, effectiveSelectedIds);
    const effectiveText =
      data.kind === "form" || data.kind === "text"
        ? trimmedText
        : effectiveChoiceText;
    const effectiveQuery =
      data.kind === "text"
        ? effectiveText
        : data.kind === "form"
        ? [...formQueryLines, effectiveText].filter(Boolean).join("\n")
        : [effectiveSelectedLabels, effectiveText].filter(Boolean).join("\n");
    const effectiveDisabled =
      data.kind === "text"
        ? !effectiveQuery
        : data.kind === "form"
        ? !requiredFormFieldsSatisfied || !effectiveQuery
        : effectiveSelectedIds.length === 0 && !effectiveText;
    if (effectiveDisabled || submitted) return;
    const payload =
      data.kind === "form"
        ? {
            card_type: "plan_clarification" as const,
            kind: "form" as const,
            form_id: data.form_id,
            field_values: collectFormValues(fields, formValues),
            text: effectiveText || undefined,
          }
        : {
            card_type: "plan_clarification" as const,
            kind: data.kind,
            selected_option_ids: effectiveSelectedIds,
            text: effectiveText || undefined,
          };
    storeSubmittedInteractionKey(PLAN_CLARIFICATION_STORAGE_KEY, submissionKey);
    setSubmitted(true);
    emit({
      type: "handleSubmit",
      data: {
        query: effectiveQuery,
        fileList: [],
        biz_params: {
          plan_interaction_response: payload,
        },
      },
    });
  };

  const goBack = () => {
    if (customActive && data.kind !== "form") {
      setCustomActive(false);
      return;
    }
    if (boundedStep > 0) {
      setActiveStep((current) => boundedIndex(current - 1, totalSteps));
      return;
    }
    handleDismiss();
  };

  const goForward = () => {
    if (!isFinalStep) {
      if (canGoNext) {
        setActiveStep((current) => boundedIndex(current + 1, totalSteps));
      }
      return;
    }
    handleSubmit();
  };

  const selectActiveOption = (optionId: string) => {
    setCustomActive(false);
    if (!activeField) {
      setTextInput("");
    }
    if (activeField) {
      setFormValues((current) => {
        const currentValue = current[activeField.id];
        if (activeField.type === "multi_choice") {
          const currentIds = Array.isArray(currentValue) ? currentValue : [];
          return {
            ...current,
            [activeField.id]: currentIds.includes(optionId)
              ? currentIds.filter((id) => id !== optionId)
              : [...currentIds, optionId],
          };
        }
        return { ...current, [activeField.id]: optionId };
      });
      return;
    }
    if (data.kind === "multi_choice") {
      setMultiChoice((current) =>
        current.includes(optionId)
          ? current.filter((id) => id !== optionId)
          : [...current, optionId],
      );
      return;
    }
    setSingleChoice(optionId);
  };

  const activateCustomResponse = () => {
    setSingleChoice("");
    setMultiChoice([]);
    setCustomActive(true);
  };

  const handleCardKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      goBack();
      return;
    }
    if (isTextTarget(event.target)) {
      if (event.key === "Enter" && !event.shiftKey) {
        if (event.nativeEvent.isComposing) {
          return;
        }
        event.preventDefault();
        goForward();
      }
      return;
    }
    const rowCount =
      activeOptions.length + (data.kind !== "form" && allowsCustomText ? 1 : 0);
    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      event.preventDefault();
      setFocusedIndex((current) =>
        boundedIndex(current + (event.key === "ArrowUp" ? -1 : 1), rowCount),
      );
      return;
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      if (boundedStep > 0) {
        setActiveStep((current) => boundedIndex(current - 1, totalSteps));
      }
      return;
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      goForward();
      return;
    }
    if (/^[1-9]$/.test(event.key)) {
      const index = Number(event.key) - 1;
      if (index < rowCount) {
        event.preventDefault();
        setFocusedIndex(index);
        if (index === activeOptions.length) activateCustomResponse();
        else selectActiveOption(activeOptions[index].id);
      }
      return;
    }
    if (event.key === " ") {
      event.preventDefault();
      const hasCustomRow = data.kind !== "form" && allowsCustomText;
      if (hasCustomRow && focusedIndex === activeOptions.length) {
        activateCustomResponse();
      } else if (activeOptions[focusedIndex]) {
        selectActiveOption(activeOptions[focusedIndex].id);
      }
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (
        data.kind === "single_choice" &&
        !singleChoice &&
        activeOptions[focusedIndex]
      ) {
        const focusedOptionId = activeOptions[focusedIndex].id;
        setSingleChoice(focusedOptionId);
        handleSubmit([focusedOptionId]);
        return;
      }
      goForward();
    }
  };

  if (submitted || dismissed || alreadySeen) return null;

  return (
    <section
      ref={cardRef}
      className={styles.planClarificationCard}
      data-plan-clarification-active="true"
      role="region"
      aria-label={data.prompt}
      tabIndex={0}
      onKeyDown={handleCardKeyDown}
    >
      <header className={styles.cardHeader}>
        <div className={styles.cardHeading}>
          <strong>{pageTitle}</strong>
          {activeField?.required ? <span>必填</span> : null}
        </div>
        <div className={styles.cardPager}>
          <button
            type="button"
            aria-label="上一项"
            disabled={boundedStep === 0}
            onClick={() =>
              setActiveStep((current) => boundedIndex(current - 1, totalSteps))
            }
          >
            <ChevronLeft aria-hidden="true" size={15} />
          </button>
          <span>
            {boundedStep + 1} of {totalSteps}
          </span>
          <button
            type="button"
            aria-label="下一项"
            disabled={!canGoNext}
            onClick={goForward}
          >
            <ChevronRight aria-hidden="true" size={15} />
          </button>
        </div>
      </header>

      {activeField?.description ? (
        <p className={styles.fieldDescription}>{activeField.description}</p>
      ) : null}

      <div className={styles.cardStage}>
        {showChoiceRows ? (
          <ChoiceRows
            options={activeOptions}
            selectedIds={activeSelectedIds}
            focusedIndex={focusedIndex}
            allowCustomResponse={data.kind !== "form" && allowsCustomText}
            customActive={customActive}
            onFocusIndexChange={setFocusedIndex}
            onSelect={selectActiveOption}
            onCustomSelect={activateCustomResponse}
          />
        ) : null}
        {activeField?.type === "text" ? (
          <input
            autoFocus
            className={styles.textField}
            aria-label={activeField.label}
            placeholder={activeField.placeholder || activeField.label}
            value={
              typeof formValues[activeField.id] === "string"
                ? (formValues[activeField.id] as string)
                : ""
            }
            onChange={(event) =>
              setFormValues((current) => ({
                ...current,
                [activeField.id]: event.target.value,
              }))
            }
          />
        ) : null}
        {showCustomInput ? (
          <textarea
            autoFocus
            className={styles.textArea}
            aria-label={pageTitle}
            placeholder={
              data.kind === "text" ? data.prompt : "请输入自定义回复"
            }
            value={textInput}
            onChange={(event) => setTextInput(event.target.value)}
          />
        ) : null}
      </div>

      <footer className={styles.cardFooter}>
        <p className={styles.keyboardHint}>方向键切换选项，Space 选择</p>
        <div className={styles.cardActions}>
          <button
            type="button"
            className={styles.dismissButton}
            aria-label="退出"
            onClick={handleDismiss}
          >
            <span>退出</span>
            <kbd>ESC</kbd>
          </button>
          <button
            type="button"
            className={styles.continueButton}
            aria-label={isFinalStep ? "提交" : "继续"}
            disabled={isFinalStep ? disabled : !canGoNext}
            onClick={goForward}
          >
            <span>{isFinalStep ? "提交" : "继续"}</span>
            <CornerDownLeft aria-hidden="true" size={14} />
          </button>
        </div>
      </footer>
    </section>
  );
}

export function ActivePlanClarificationCard() {
  const clarification = useContextSelector(
    ChatAnywhereMessagesContext,
    (value) => findLatestPlanClarificationCard(value.messages || []),
  );

  if (!clarification) {
    return null;
  }
  return (
    <PlanClarificationCard
      data={clarification.data}
      cardInstanceKey={clarification.instanceKey}
      cardSourceKey={clarification.sourceKey}
    />
  );
}

function PlanList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section className={styles.reviewSection}>
      <h4>{title}</h4>
      <ul>
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

export function PlanReviewCard({ data }: { data: ChatPlanReviewCardData }) {
  const [feedback, setFeedback] = useState("");
  const resolvedByBackend = data.status === "submitted";
  const [submitted, setSubmitted] = useState(false);
  const submittedStorageKey = useMemo(() => data.plan_id, [data.plan_id]);

  useEffect(() => {
    setSubmitted(
      resolvedByBackend || loadSubmittedPlanIds().has(submittedStorageKey),
    );
  }, [resolvedByBackend, submittedStorageKey]);

  const handleDecision = (decision: "revise" | "execute" | "exit_plan") => {
    if (submitted) return;

    const trimmedFeedback = feedback.trim();
    const mode = decision === "revise" ? "plan" : "normal";
    const query =
      decision === "revise"
        ? trimmedFeedback || "Revise the plan"
        : decision === "execute"
        ? `Execute plan ${data.plan_id}`
        : "Exit Plan Mode";

    storeSubmittedPlanId(data.plan_id);
    setSubmitted(true);
    emit({
      type: "handleSubmit",
      data: {
        query,
        fileList: [],
        biz_params: {
          mode,
          plan_interaction_response: {
            card_type: "plan_review",
            plan_id: data.plan_id,
            decision,
            feedback: trimmedFeedback || undefined,
          },
        },
      },
    });
  };

  return (
    <section
      className={styles.planReviewCard}
      data-plan-review-card="true"
      role="region"
      aria-label={data.title}
    >
      <header className={styles.reviewHeader}>
        <div className={styles.reviewHeading}>
          <span className={styles.reviewIcon}>
            <ClipboardCheck aria-hidden="true" size={16} />
          </span>
          <div>
            <strong>{data.title}</strong>
            <p>{data.summary}</p>
          </div>
        </div>
      </header>

      <div className={styles.reviewContent}>
        <PlanList title="Steps" items={data.steps} />
        <PlanList title="Risks" items={data.risks} />
        <PlanList title="Verification" items={data.verification} />
        <textarea
          className={styles.reviewFeedback}
          placeholder="Feedback"
          value={feedback}
          disabled={submitted}
          onChange={(event) => setFeedback(event.target.value)}
        />
      </div>

      <footer className={styles.reviewActions}>
        <button
          type="button"
          className={styles.reviewSecondaryButton}
          disabled={submitted}
          onClick={() => handleDecision("revise")}
        >
          Continue modifying
        </button>
        <button
          type="button"
          className={styles.reviewPrimaryButton}
          disabled={submitted}
          onClick={() => handleDecision("execute")}
        >
          Execute
        </button>
        <button
          type="button"
          className={styles.reviewSecondaryButton}
          disabled={submitted}
          onClick={() => handleDecision("exit_plan")}
        >
          Exit Plan Mode
        </button>
      </footer>
    </section>
  );
}
