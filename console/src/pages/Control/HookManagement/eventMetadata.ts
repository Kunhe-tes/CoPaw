import type { HookEventName } from "./types";

export const eventMetadata: Record<
  HookEventName,
  { label: string; description: string; order: number }
> = {
  SessionStart: {
    label: "会话启动",
    description: "在新的 Agent 会话启动时触发。",
    order: 1,
  },
  UserPromptSubmit: {
    label: "提交提示词",
    description: "在用户提示词提交给 Agent 前触发。",
    order: 2,
  },
  PreToolUse: {
    label: "工具调用前",
    description: "在 Agent 调用工具前触发。",
    order: 3,
  },
  PostToolUse: {
    label: "工具调用后",
    description: "在 Agent 成功完成工具调用后触发。",
    order: 4,
  },
  PostToolUseFailure: {
    label: "工具调用失败",
    description: "在 Agent 的工具调用失败后触发。",
    order: 5,
  },
  BeforeStop: {
    label: "停止前",
    description: "在 Agent 准备停止前触发。",
    order: 6,
  },
  Stop: {
    label: "停止",
    description: "在 Agent 停止时触发。",
    order: 7,
  },
};
