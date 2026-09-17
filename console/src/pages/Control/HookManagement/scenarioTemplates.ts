import type {
  HookEventName,
  HookHandlerDraft,
  HookMatcherGroupDraft,
} from "./types";

export type ScenarioTemplateId =
  | "session-start-check"
  | "prompt-preprocess"
  | "tool-audit"
  | "tool-block"
  | "failure-alert";

export type ScenarioEvent = {
  event: HookEventName;
  groups: HookMatcherGroupDraft[];
};

type ScenarioTemplate = {
  id: ScenarioTemplateId;
  label: string;
  description: string;
  event: HookEventName;
  createGroups: () => HookMatcherGroupDraft[];
};

function createTemplatePrompt(
  idPrefix: string,
  prompt: string,
  failPolicy: "allow" | "block",
): HookHandlerDraft {
  return {
    id: `${idPrefix}-${crypto.randomUUID().slice(0, 8)}`,
    type: "prompt",
    prompt,
    if: "",
    timeout: 10,
    statusMessage: "",
    once: false,
    includeConversationSnapshot: false,
    conversationSnapshotLimit: 50,
    failPolicy,
  };
}

function createTemplateGroup(
  id: string,
  handler: HookHandlerDraft,
): HookMatcherGroupDraft {
  return { id, matcher: { tools: [] }, hooks: [handler] };
}

export const scenarioTemplates: ScenarioTemplate[] = [
  {
    id: "session-start-check",
    label: "会话启动检查",
    description: "在会话启动时检查必要前提，并给出继续执行建议。",
    event: "SessionStart",
    createGroups: () => [
      createTemplateGroup(
        "session-start-check",
        createTemplatePrompt(
          "session-check",
          "检查当前会话的启动前提；若存在风险，请说明风险和下一步建议。",
          "allow",
        ),
      ),
    ],
  },
  {
    id: "prompt-preprocess",
    label: "提示词预处理",
    description: "在提示词提交前识别缺失上下文和潜在歧义。",
    event: "UserPromptSubmit",
    createGroups: () => [
      createTemplateGroup(
        "prompt-preprocess",
        createTemplatePrompt(
          "prompt-preprocess",
          "检查用户提示词是否缺少执行所需上下文，并提示需要澄清的内容。",
          "allow",
        ),
      ),
    ],
  },
  {
    id: "tool-audit",
    label: "工具调用审计",
    description: "在工具调用成功后记录可审计的结果摘要。",
    event: "PostToolUse",
    createGroups: () => [
      createTemplateGroup(
        "tool-audit",
        createTemplatePrompt(
          "tool-audit",
          "为本次工具调用生成简洁的审计摘要，包含操作目的、结果和需要跟进的风险。",
          "allow",
        ),
      ),
    ],
  },
  {
    id: "tool-block",
    label: "工具调用拦截",
    description: "在工具调用前检查风险，不符合规则时阻断。",
    event: "PreToolUse",
    createGroups: () => [
      createTemplateGroup(
        "tool-block",
        createTemplatePrompt(
          "tool-block",
          "检查即将执行的工具调用是否违反当前安全或审批规则；存在风险时给出阻断理由。",
          "block",
        ),
      ),
    ],
  },
  {
    id: "failure-alert",
    label: "失败告警",
    description: "在工具调用失败后归纳原因并提示恢复操作。",
    event: "PostToolUseFailure",
    createGroups: () => [
      createTemplateGroup(
        "failure-alert",
        createTemplatePrompt(
          "failure-alert",
          "归纳本次工具调用失败原因，判断是否可重试，并给出建议的恢复操作。",
          "allow",
        ),
      ),
    ],
  },
];

export function createScenarioEvent(id: ScenarioTemplateId): ScenarioEvent {
  const template = scenarioTemplates.find((item) => item.id === id);
  if (!template) throw new Error(`Unknown Hook scenario template: ${id}`);
  return { event: template.event, groups: template.createGroups() };
}
