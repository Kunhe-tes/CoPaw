import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Checkbox,
  Flex,
  Input,
  Radio,
  Select,
  Space,
  Typography,
} from "antd";
import {
  ArrowLeft,
  ArrowRight,
  ClipboardCheck,
} from "lucide-react";
import {
  ChatAnywhereSessionsContext,
  type IAgentScopeRuntimeWebUIMessage,
  OperateCard,
} from "@/components/agentscope-chat";
import { ChatAnywhereMessagesContext } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/ChatAnywhereMessagesContext";
import { emit } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/useChatAnywhereEventEmitter";
import type {
  ChatPlanClarificationCardData,
  PlanClarificationField,
  ChatPlanReviewCardData,
  PlanClarificationOption,
} from "../messageMeta";
import styles from "./PlanInteractionCards.module.less";
import { useContextSelector } from "use-context-selector";

const PLAN_CLARIFICATION_STORAGE_KEY = "copaw_submitted_plan_clarifications";
const PLAN_REVIEW_STORAGE_KEY = "copaw_submitted_plan_reviews";
const PLAN_INTERACTION_CARD_CODE = "PlanInteraction";

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

function findLatestPlanClarificationCard(
  messages: IAgentScopeRuntimeWebUIMessage[],
): ChatPlanClarificationCardData | null {
  for (
    let messageIndex = messages.length - 1;
    messageIndex >= 0;
    messageIndex -= 1
  ) {
    const cards = messages[messageIndex]?.cards || [];
    for (let cardIndex = cards.length - 1; cardIndex >= 0; cardIndex -= 1) {
      const card = cards[cardIndex];
      if (
        card.code === PLAN_INTERACTION_CARD_CODE &&
        isPlanClarificationCardData(card.data)
      ) {
        return card.data;
      }
    }
  }
  return null;
}

function createPlanClarificationSubmissionKey(
  data: ChatPlanClarificationCardData,
  sessionId: string | undefined,
): string {
  return JSON.stringify({
    session_id: sessionId || "unknown",
    kind: data.kind,
    prompt: data.prompt,
    form_id: data.form_id,
    options: data.options || [],
    fields: data.fields || [],
    allow_custom_response: data.allow_custom_response === true,
  });
}

function getInitialFormStep(fields: PlanClarificationField[]): number {
  return fields.length > 0 ? 0 : 0;
}

function getBoundedFormStep(step: number, totalSteps: number): number {
  if (totalSteps <= 0) return 0;
  return Math.min(Math.max(step, 0), totalSteps - 1);
}

function PlanClarificationFieldInput({
  field,
  value,
  onChange,
}: {
  field: PlanClarificationField;
  value: string | string[] | undefined;
  onChange: (value: string | string[]) => void;
}) {
  if (field.type === "select") {
    return (
      <Select
        aria-label={field.label}
        className={styles.fieldControl}
        placeholder={field.placeholder || field.label}
        value={typeof value === "string" ? value : undefined}
        options={(field.options || []).map((option) => ({
          value: option.id,
          label: option.label,
        }))}
        onChange={(nextValue) => onChange(String(nextValue))}
      />
    );
  }

  if (field.type === "multiselect") {
    return (
      <Select
        mode="multiple"
        aria-label={field.label}
        className={styles.fieldControl}
        placeholder={field.placeholder || field.label}
        value={Array.isArray(value) ? value : []}
        options={(field.options || []).map((option) => ({
          value: option.id,
          label: option.label,
        }))}
        onChange={(nextValue) => {
          const selectedValues = Array.isArray(nextValue) ? nextValue : [];
          onChange(selectedValues.map(String));
        }}
      />
    );
  }

  if (field.type === "textarea") {
    return (
      <Input.TextArea
        aria-label={field.label}
        autoSize={{ minRows: 3, maxRows: 6 }}
        className={styles.fieldControl}
        placeholder={field.placeholder || field.label}
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }

  return (
    <Input
      aria-label={field.label}
      className={styles.fieldControl}
      placeholder={field.placeholder || field.label}
      value={typeof value === "string" ? value : ""}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

function PlanClarificationFormSteps({
  fields,
  formValues,
  textInput,
  allowCustomResponse,
  disabled,
  onFieldChange,
  onTextInputChange,
  onSubmit,
}: {
  fields: PlanClarificationField[];
  formValues: Record<string, string | string[]>;
  textInput: string;
  allowCustomResponse: boolean;
  disabled: boolean;
  onFieldChange: (fieldId: string, value: string | string[]) => void;
  onTextInputChange: (value: string) => void;
  onSubmit: () => void;
}) {
  const hasCustomResponseStep = allowCustomResponse;
  const totalSteps = fields.length + (hasCustomResponseStep ? 1 : 0);
  const [activeStep, setActiveStep] = useState(() =>
    getInitialFormStep(fields),
  );
  const boundedStep = getBoundedFormStep(activeStep, totalSteps);
  const activeField =
    boundedStep < fields.length ? fields[boundedStep] : undefined;
  const isCustomResponseStep = !activeField && hasCustomResponseStep;
  const currentFieldComplete = activeField
    ? !activeField.required || hasFormValue(formValues[activeField.id])
    : true;
  const canGoBack = boundedStep > 0;
  const canGoNext = boundedStep < totalSteps - 1 && currentFieldComplete;
  const isFinalStep = totalSteps === 0 || boundedStep === totalSteps - 1;
  const hasCompletedAnswers = fields.some((field) =>
    hasFormValue(formValues[field.id]),
  );
  const stageViewportClassName = [
    styles.formStageViewport,
    activeField?.type === "textarea" || isCustomResponseStep
      ? styles.formStageViewportExpanded
      : styles.formStageViewportCompact,
  ].join(" ");

  useEffect(() => {
    setActiveStep((current) => getBoundedFormStep(current, totalSteps));
  }, [totalSteps]);

  const goBack = () => {
    if (!canGoBack) return;
    setActiveStep((current) => getBoundedFormStep(current - 1, totalSteps));
  };

  const goNext = () => {
    if (!canGoNext) return;
    setActiveStep((current) => getBoundedFormStep(current + 1, totalSteps));
  };

  return (
    <div className={styles.formStepper}>
      <div className={styles.formStage}>
        <div className={styles.formStageMeta}>
          <span className={styles.formStageCount}>
            {totalSteps > 0 ? `${boundedStep + 1}/${totalSteps}` : "0/0"}
          </span>
          {activeField?.required ? (
            <span className={styles.formStageRequired}>Required</span>
          ) : null}
        </div>
        <Typography.Text className={styles.formStageTitle} strong>
          {activeField?.label || "Additional context"}
        </Typography.Text>

        {activeField?.description ? (
          <Typography.Text className={styles.formStageDescription}>
            {activeField.description}
          </Typography.Text>
        ) : null}

        {hasCompletedAnswers ? (
          <div className={styles.answerStrip}>
            {fields.map((field, index) => {
              const formattedValue = formatFormFieldValue(
                field,
                formValues[field.id],
              );
              if (!formattedValue) return null;
              return (
                <button
                  key={field.id}
                  type="button"
                  className={styles.answerPill}
                  onClick={() => setActiveStep(index)}
                >
                  <span>{field.label}</span>
                  <strong>{formattedValue}</strong>
                </button>
              );
            })}
          </div>
        ) : null}

        <div className={stageViewportClassName}>
          {activeField ? (
            <PlanClarificationFieldInput
              field={activeField}
              value={formValues[activeField.id]}
              onChange={(value) => onFieldChange(activeField.id, value)}
            />
          ) : null}

          {isCustomResponseStep ? (
            <Input.TextArea
              autoSize={{ minRows: 3, maxRows: 6 }}
              className={styles.fieldControl}
              placeholder="Custom response"
              value={textInput}
              onChange={(event) => onTextInputChange(event.target.value)}
            />
          ) : null}
        </div>
      </div>

      <Flex justify="space-between" align="center" className={styles.formNav}>
        <Button
          icon={<ArrowLeft size={14} />}
          disabled={!canGoBack}
          onClick={goBack}
        >
          Back
        </Button>
        {isFinalStep ? (
          <Button type="primary" disabled={disabled} onClick={onSubmit}>
            Submit
          </Button>
        ) : (
          <Button
            type="primary"
            icon={<ArrowRight size={14} />}
            iconPosition="end"
            disabled={!canGoNext}
            onClick={goNext}
          >
            Next
          </Button>
        )}
      </Flex>
    </div>
  );
}

export function PlanClarificationCard({
  data,
}: {
  data: ChatPlanClarificationCardData;
}) {
  const currentSessionId = useContextSelector(
    ChatAnywhereSessionsContext,
    (value) => value.currentSessionId,
  );
  const [singleChoice, setSingleChoice] = useState<string>("");
  const [multiChoice, setMultiChoice] = useState<string[]>([]);
  const [textInput, setTextInput] = useState("");
  const [formValues, setFormValues] = useState<
    Record<string, string | string[]>
  >({});
  const submissionKey = useMemo(
    () =>
      createPlanClarificationSubmissionKey(
        data,
        currentSessionId ||
          (window as Window & { currentSessionId?: string }).currentSessionId,
      ),
    [currentSessionId, data],
  );
  const [submitted, setSubmitted] = useState(() =>
    loadSubmittedInteractionKeys(PLAN_CLARIFICATION_STORAGE_KEY).has(
      submissionKey,
    ),
  );
  const options = data.options || [];
  const fields = data.fields || [];
  const selectedIds =
    data.kind === "single_choice"
      ? singleChoice
        ? [singleChoice]
        : []
      : data.kind === "multi_choice"
      ? multiChoice
      : [];
  const trimmedText = textInput.trim();
  const selectedLabels = optionLabels(options, selectedIds);
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
  const allowsCustomText =
    data.kind === "text_input" || data.allow_custom_response === true;
  const queryParts =
    data.kind === "text_input"
      ? [trimmedText]
      : data.kind === "form"
      ? [...formQueryLines, trimmedText].filter(Boolean)
      : [selectedLabels, trimmedText].filter(Boolean);
  const query = queryParts.join("\n");
  const disabled =
    data.kind === "text_input"
      ? !query
      : data.kind === "form"
      ? !requiredFormFieldsSatisfied || !query
      : selectedIds.length === 0 && !trimmedText;

  useEffect(() => {
    setSubmitted(
      loadSubmittedInteractionKeys(PLAN_CLARIFICATION_STORAGE_KEY).has(
        submissionKey,
      ),
    );
  }, [submissionKey]);

  const handleSubmit = () => {
    if (disabled || submitted) return;
    const payload =
      data.kind === "form"
        ? {
            card_type: "plan_clarification" as const,
            kind: "form" as const,
            form_id: data.form_id,
            field_values: collectFormValues(fields, formValues),
            text: trimmedText || undefined,
          }
        : {
            card_type: "plan_clarification" as const,
            kind: data.kind,
            selected_option_ids: selectedIds,
            text: trimmedText || undefined,
          };
    storeSubmittedInteractionKey(PLAN_CLARIFICATION_STORAGE_KEY, submissionKey);
    setSubmitted(true);
    emit({
      type: "handleSubmit",
      data: {
        query,
        fileList: [],
        biz_params: {
          plan_interaction_response: payload,
        },
      },
    });
  };

  if (submitted) return null;
  const choiceOptionsNeedScrollHint = options.length > 3;

  return (
    <div className={styles.planClarificationCard}>
      <div className={styles.planClarificationBody}>
        {data.kind !== "form" ? (
          <Typography.Text strong className={styles.choicePrompt}>
            {data.prompt}
          </Typography.Text>
        ) : null}
        {data.kind === "single_choice" ? (
          <div className={styles.choiceOptionsViewport}>
            {choiceOptionsNeedScrollHint ? (
              <span aria-hidden="true" className={styles.choiceScrollHint}>
                <span className={styles.choiceScrollTrack}>
                  <span className={styles.choiceScrollThumb} />
                </span>
              </span>
            ) : null}
            <Radio.Group
              value={singleChoice}
              onChange={(event) => setSingleChoice(event.target.value)}
            >
              <Space direction="vertical" className={styles.choiceOptionList}>
                {options.map((option) => (
                  <Radio key={option.id} value={option.id}>
                    {option.label}
                  </Radio>
                ))}
              </Space>
            </Radio.Group>
          </div>
        ) : null}
        {data.kind === "multi_choice" ? (
          <div className={styles.choiceOptionsViewport}>
            {choiceOptionsNeedScrollHint ? (
              <span aria-hidden="true" className={styles.choiceScrollHint}>
                <span className={styles.choiceScrollTrack}>
                  <span className={styles.choiceScrollThumb} />
                </span>
              </span>
            ) : null}
            <Checkbox.Group
              value={multiChoice}
              onChange={(values) => setMultiChoice(values.map(String))}
            >
              <Space direction="vertical" className={styles.choiceOptionList}>
                {options.map((option) => (
                  <Checkbox key={option.id} value={option.id}>
                    {option.label}
                  </Checkbox>
                ))}
              </Space>
            </Checkbox.Group>
          </div>
        ) : null}
        {data.kind === "text_input" ? (
          <Input.TextArea
            autoSize={{ minRows: 2, maxRows: 5 }}
            placeholder={data.prompt}
            value={textInput}
            onChange={(event) => setTextInput(event.target.value)}
          />
        ) : null}
        {data.kind === "form" ? (
          <PlanClarificationFormSteps
            fields={fields}
            formValues={formValues}
            textInput={textInput}
            allowCustomResponse={allowsCustomText}
            disabled={disabled}
            onFieldChange={(fieldId, value) =>
              setFormValues((current) => ({
                ...current,
                [fieldId]: value,
              }))
            }
            onTextInputChange={setTextInput}
            onSubmit={handleSubmit}
          />
        ) : null}
        {data.kind !== "text_input" &&
        data.kind !== "form" &&
        allowsCustomText ? (
          <Input.TextArea
            autoSize={{ minRows: 2, maxRows: 5 }}
            placeholder="Custom response"
            className={styles.choiceCustomResponse}
            value={textInput}
            onChange={(event) => setTextInput(event.target.value)}
          />
        ) : null}
        {data.kind !== "form" ? (
          <Flex justify="flex-end" className={styles.cardActions}>
            <Button type="primary" disabled={disabled} onClick={handleSubmit}>
              Submit
            </Button>
          </Flex>
        ) : null}
      </div>
    </div>
  );
}

export function ActivePlanClarificationCard() {
  const data = useContextSelector(ChatAnywhereMessagesContext, (value) =>
    findLatestPlanClarificationCard(value.messages || []),
  );

  if (!data) return null;
  return <PlanClarificationCard data={data} />;
}

function PlanList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <Typography.Text strong>{title}</Typography.Text>
      <ul style={{ margin: "6px 0 0", paddingInlineStart: 20 }}>
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
    </div>
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
    <OperateCard
      header={{
        icon: <ClipboardCheck size={16} />,
        title: data.title,
        description: data.summary,
      }}
      body={{
        defaultOpen: true,
        children: (
          <OperateCard.LineBody>
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <PlanList title="Steps" items={data.steps} />
              <PlanList title="Risks" items={data.risks} />
              <PlanList title="Verification" items={data.verification} />
              <PlanList title="Open questions" items={data.open_questions} />
              <Typography.Text type="secondary">
                Confidence: {Math.round(data.confidence * 100)}%
              </Typography.Text>
              <Input.TextArea
                autoSize={{ minRows: 2, maxRows: 4 }}
                placeholder="Feedback"
                value={feedback}
                disabled={submitted}
                onChange={(event) => setFeedback(event.target.value)}
              />
              <Flex wrap gap={8}>
                <Button
                  disabled={submitted}
                  onClick={() => handleDecision("revise")}
                >
                  Continue modifying
                </Button>
                <Button
                  type="primary"
                  disabled={submitted}
                  onClick={() => handleDecision("execute")}
                >
                  Execute
                </Button>
                <Button
                  disabled={submitted}
                  onClick={() => handleDecision("exit_plan")}
                >
                  Exit Plan Mode
                </Button>
              </Flex>
            </Space>
          </OperateCard.LineBody>
        ),
      }}
    />
  );
}
