import { useEffect, useMemo, useState } from "react";
import { Button, Checkbox, Flex, Input, Radio, Space, Typography } from "antd";
import { ClipboardCheck, FileQuestion } from "lucide-react";
import { OperateCard } from "@/components/agentscope-chat";
import { emit } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/useChatAnywhereEventEmitter";
import type {
  ChatPlanClarificationCardData,
  ChatPlanReviewCardData,
  PlanClarificationOption,
} from "../messageMeta";

const PLAN_REVIEW_STORAGE_KEY = "copaw_submitted_plan_reviews";

function loadSubmittedPlanIds(): Set<string> {
  try {
    const raw = sessionStorage.getItem(PLAN_REVIEW_STORAGE_KEY);
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

function storeSubmittedPlanId(planId: string): void {
  if (!planId) return;
  const submittedIds = loadSubmittedPlanIds();
  submittedIds.add(planId);
  try {
    sessionStorage.setItem(
      PLAN_REVIEW_STORAGE_KEY,
      JSON.stringify(Array.from(submittedIds)),
    );
  } catch {
    return;
  }
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

export function PlanClarificationCard({
  data,
}: {
  data: ChatPlanClarificationCardData;
}) {
  const [singleChoice, setSingleChoice] = useState<string>("");
  const [multiChoice, setMultiChoice] = useState<string[]>([]);
  const [textInput, setTextInput] = useState("");
  const options = data.options || [];
  const selectedIds =
    data.kind === "single_choice"
      ? singleChoice
        ? [singleChoice]
        : []
      : data.kind === "multi_choice"
      ? multiChoice
      : [];
  const query =
    data.kind === "text_input"
      ? textInput.trim()
      : optionLabels(options, selectedIds);
  const disabled =
    data.kind === "text_input" ? !query : selectedIds.length === 0;

  const handleSubmit = () => {
    if (disabled) return;
    emit({
      type: "handleSubmit",
      data: {
        query,
        fileList: [],
        biz_params: {
          plan_interaction_response: {
            card_type: "plan_clarification",
            kind: data.kind,
            selected_option_ids: selectedIds,
            text: data.kind === "text_input" ? query : undefined,
          },
        },
      },
    });
  };

  return (
    <OperateCard
      header={{
        icon: <FileQuestion size={16} />,
        title: "Plan clarification",
        description: data.prompt,
      }}
      body={{
        defaultOpen: true,
        children: (
          <OperateCard.LineBody>
            {data.kind === "single_choice" ? (
              <Radio.Group
                value={singleChoice}
                onChange={(event) => setSingleChoice(event.target.value)}
              >
                <Space direction="vertical">
                  {options.map((option) => (
                    <Radio key={option.id} value={option.id}>
                      {option.label}
                    </Radio>
                  ))}
                </Space>
              </Radio.Group>
            ) : null}
            {data.kind === "multi_choice" ? (
              <Checkbox.Group
                value={multiChoice}
                onChange={(values) => setMultiChoice(values.map(String))}
              >
                <Space direction="vertical">
                  {options.map((option) => (
                    <Checkbox key={option.id} value={option.id}>
                      {option.label}
                    </Checkbox>
                  ))}
                </Space>
              </Checkbox.Group>
            ) : null}
            {data.kind === "text_input" ? (
              <Input.TextArea
                autoSize={{ minRows: 2, maxRows: 5 }}
                placeholder={data.prompt}
                value={textInput}
                onChange={(event) => setTextInput(event.target.value)}
              />
            ) : null}
            <Flex justify="flex-end" style={{ marginTop: 12 }}>
              <Button type="primary" disabled={disabled} onClick={handleSubmit}>
                Submit
              </Button>
            </Flex>
          </OperateCard.LineBody>
        ),
      }}
    />
  );
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
