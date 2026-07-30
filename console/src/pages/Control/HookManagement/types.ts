import type {
  HookConfig,
  HookContext,
  HookHandler,
  HookMatcherGroup,
} from "@/api/modules/hookManagement";

export type HookEventName =
  | "SessionStart"
  | "UserPromptSubmit"
  | "PreToolUse"
  | "PostToolUse"
  | "PostToolUseFailure"
  | "BeforeStop"
  | "Stop";

export type HookHandlerType = HookHandler["type"];

export type HookHandlerDraft = HookHandler & {
  id: string;
  type: HookHandlerType;
};

export type HookMatcherGroupDraft = HookMatcherGroup & {
  id: string;
  matcher: { tools: string[] };
  hooks: HookHandlerDraft[];
};

export type HookConfigDraft = HookConfig & {
  enabled: boolean;
  events: Partial<Record<HookEventName, HookMatcherGroupDraft[]>>;
};

export type HookContextDraft = HookContext;

export type HookTreeSelection =
  | { kind: "root" }
  | { kind: "group"; event: HookEventName; groupId: string }
  | {
      kind: "handler";
      event: HookEventName;
      groupId: string;
      handlerId: string;
    };
