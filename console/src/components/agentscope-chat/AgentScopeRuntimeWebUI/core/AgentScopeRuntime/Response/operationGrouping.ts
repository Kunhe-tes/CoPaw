import type { IAgentScopeRuntimeMessage, IDataContent } from "../types";
import {
  AgentScopeRuntimeContentType,
  AgentScopeRuntimeMessageType,
  AgentScopeRuntimeRunStatus,
} from "../types";

/**
 * Tool call grouping presentation helpers.
 *
 * The backend attaches a validated operation_group object ({ id, title })
 * to tool call messages.  Consecutive tool messages that share the same
 * explicit group id form one default-collapsed operation group in the
 * Console.  Grouping is explicit only: no inference from time, adjacency
 * or tool type (R1), and messages without a declaration keep the legacy
 * individual-card rendering (R16).
 */

export type ToolStepStatus =
  | "running"
  | "success"
  | "failed"
  | "pending"
  | "rejected"
  | "blocked"
  | "canceled";

export type GroupSummaryStatus =
  | "running"
  | "success"
  | "failed"
  | "pending"
  | "warning"
  | "canceled";

export interface OperationGroupInfo {
  id: string;
  title: string;
  instanceKey: string;
}

export interface OperationGroupEntry {
  kind: "group";
  key: string;
  group: OperationGroupInfo;
  steps: IAgentScopeRuntimeMessage[];
}

export interface OperationGroupMessageItem {
  kind: "message";
  message: IAgentScopeRuntimeMessage;
}

export type OperationGroupedItem =
  | OperationGroupEntry
  | OperationGroupMessageItem;

export const OPERATION_GROUP_SAFE_TITLE = "任务操作";

const TOOL_MESSAGE_TYPES = new Set<AgentScopeRuntimeMessageType>([
  AgentScopeRuntimeMessageType.FUNCTION_CALL,
  AgentScopeRuntimeMessageType.FUNCTION_CALL_OUTPUT,
  AgentScopeRuntimeMessageType.PLUGIN_CALL,
  AgentScopeRuntimeMessageType.PLUGIN_CALL_OUTPUT,
  AgentScopeRuntimeMessageType.MCP_CALL,
  AgentScopeRuntimeMessageType.MCP_CALL_OUTPUT,
  AgentScopeRuntimeMessageType.COMPONENT_CALL,
  AgentScopeRuntimeMessageType.COMPONENT_CALL_OUTPUT,
]);

const GOVERNANCE_STATUSES: ToolStepStatus[] = [
  "pending",
  "rejected",
  "blocked",
];

const TOOL_STATUSES: ToolStepStatus[] = ["running", "success", "failed"];

export function isOperationGroupToolMessage(
  message: IAgentScopeRuntimeMessage,
): boolean {
  return TOOL_MESSAGE_TYPES.has(message.type);
}

function isReasoningMessage(message: IAgentScopeRuntimeMessage): boolean {
  return message.type === AgentScopeRuntimeMessageType.REASONING;
}

function isToolStatus(value: unknown): value is ToolStepStatus {
  return (
    typeof value === "string" && TOOL_STATUSES.includes(value as ToolStepStatus)
  );
}

function isGovernance(
  value: unknown,
): value is "pending" | "rejected" | "blocked" {
  return (
    typeof value === "string" &&
    GOVERNANCE_STATUSES.includes(value as ToolStepStatus)
  );
}

function dataBlocks(message: IAgentScopeRuntimeMessage): IDataContent[] {
  return (message.content || []).filter(
    (content): content is IDataContent =>
      content.type === AgentScopeRuntimeContentType.DATA,
  );
}

function blockData(message: IAgentScopeRuntimeMessage, index: number) {
  const data = dataBlocks(message)[index]?.data;
  return data && typeof data === "object" ? data : undefined;
}

export function extractOperationGroup(
  message: IAgentScopeRuntimeMessage,
): OperationGroupInfo | null {
  if (!isOperationGroupToolMessage(message)) return null;
  const data = blockData(message, 0);
  const group = data?.operation_group;
  if (!group || typeof group !== "object") return null;
  const raw = group as Record<string, unknown>;
  const id = typeof raw.id === "string" ? raw.id.trim() : "";
  if (!id) return null;
  const title =
    typeof raw.title === "string" && raw.title.trim()
      ? raw.title.trim()
      : OPERATION_GROUP_SAFE_TITLE;
  return { id, title, instanceKey: id };
}

export function getToolStepStatus(
  message: IAgentScopeRuntimeMessage,
): ToolStepStatus {
  const blocks = dataBlocks(message);
  const terminalData = blocks[1]?.data;
  const inputData = blocks[0]?.data;

  for (const data of [terminalData, inputData]) {
    if (!data || typeof data !== "object") continue;
    const record = data as Record<string, unknown>;
    if (isGovernance(record.tool_governance)) return record.tool_governance;
    if (isToolStatus(record.tool_status)) return record.tool_status;
  }

  switch (message.status) {
    case AgentScopeRuntimeRunStatus.InProgress:
    case AgentScopeRuntimeRunStatus.Created:
      return "running";
    case AgentScopeRuntimeRunStatus.Completed:
      return "success";
    case AgentScopeRuntimeRunStatus.Failed:
      return "failed";
    case AgentScopeRuntimeRunStatus.Canceled:
      return "canceled";
    case AgentScopeRuntimeRunStatus.Rejected:
      return "rejected";
    default:
      return "running";
  }
}

export function getToolStepKey(message: IAgentScopeRuntimeMessage): string {
  for (const data of [blockData(message, 0), blockData(message, 1)]) {
    if (data && typeof data === "object") {
      const record = data as Record<string, unknown>;
      const key = record.call_id || record.id || record.tool_call_id;
      if (typeof key === "string" && key) return key;
    }
  }
  return message.id;
}

const SUMMARY_PRECEDENCE: GroupSummaryStatus[] = [
  "failed",
  "pending",
  "running",
  "warning",
  "canceled",
  "success",
];

function toSummaryStatus(status: ToolStepStatus): GroupSummaryStatus {
  if (status === "rejected" || status === "blocked") return "warning";
  return status;
}

export function aggregateGroupStatus(
  steps: IAgentScopeRuntimeMessage[],
): GroupSummaryStatus {
  let best: GroupSummaryStatus = "success";
  for (const step of steps) {
    if (!isOperationGroupToolMessage(step)) continue;
    const summary = toSummaryStatus(getToolStepStatus(step));
    if (
      SUMMARY_PRECEDENCE.indexOf(summary) < SUMMARY_PRECEDENCE.indexOf(best)
    ) {
      best = summary;
    }
  }
  return best;
}

const SHELL_TOOL_STATUS_TEXT: Record<ToolStepStatus, string> = {
  running: "正在执行命令行操作",
  success: "命令行操作已完成",
  failed: "命令行操作未成功",
  pending: "命令行操作待审批",
  rejected: "命令行操作已拒绝",
  blocked: "命令行操作已拦截",
  canceled: "命令行操作已取消",
};

const BACKGROUND_TOOL_STATUS_TEXT: Record<ToolStepStatus, string> = {
  running: "正在启动后台任务",
  success: "后台任务已启动",
  failed: "后台任务启动失败",
  pending: "后台任务待审批",
  rejected: "后台任务已拒绝",
  blocked: "后台任务已拦截",
  canceled: "后台任务已取消",
};

function readToolName(message: IAgentScopeRuntimeMessage): string {
  const data = blockData(message, 0) || blockData(message, 1);
  const record = data as Record<string, unknown> | undefined;
  const name =
    record?.name || record?.tool_name || record?.tool || record?.mcp_tool_name;
  return typeof name === "string" ? name : "";
}

function isGenericToolSummary(value: string): boolean {
  return /^(开始执行操作|正在工具操作|工具操作)$/.test(value.trim());
}

export function getToolStepText(message: IAgentScopeRuntimeMessage): string {
  const toolName = readToolName(message);
  const status = getToolStepStatus(message);
  if (toolName === "execute_shell_command")
    return SHELL_TOOL_STATUS_TEXT[status];
  if (toolName === "start_background_process")
    return BACKGROUND_TOOL_STATUS_TEXT[status];

  const inputData = blockData(message, 0) as
    | Record<string, unknown>
    | undefined;
  const terminalData = blockData(message, 1) as
    | Record<string, unknown>
    | undefined;
  const callSummary = inputData?.summary;
  if (
    typeof callSummary === "string" &&
    callSummary.trim() &&
    !isGenericToolSummary(callSummary)
  ) {
    return callSummary.trim();
  }
  const outputSummary = terminalData?.output_summary;
  if (typeof outputSummary === "string" && outputSummary.trim()) {
    return outputSummary.trim();
  }
  if (typeof callSummary === "string" && callSummary.trim()) {
    return callSummary.trim();
  }
  return toolName ? "工具调用：" + toolName : "工具操作";
}

export function groupOperationMessages(messages: IAgentScopeRuntimeMessage[]): {
  items: OperationGroupedItem[];
  groups: OperationGroupEntry[];
} {
  const items: OperationGroupedItem[] = [];
  const groups: OperationGroupEntry[] = [];
  let openSteps: IAgentScopeRuntimeMessage[] = [];
  let openGroupId = "";

  const flush = () => {
    if (openSteps.length === 0) return;
    const first = openSteps[0];
    const info = extractOperationGroup(first);
    if (!info) {
      for (const step of openSteps) {
        items.push({ kind: "message", message: step });
      }
      openSteps = [];
      openGroupId = "";
      return;
    }
    const instanceKey = info.id + ":" + getToolStepKey(first);
    const entry: OperationGroupEntry = {
      kind: "group",
      key: instanceKey,
      group: { ...info, instanceKey },
      steps: openSteps,
    };
    groups.push(entry);
    items.push(entry);
    openSteps = [];
    openGroupId = "";
  };

  for (const message of messages) {
    const groupInfo = isOperationGroupToolMessage(message)
      ? extractOperationGroup(message)
      : null;
    if (groupInfo) {
      if (openSteps.length === 0) {
        openGroupId = groupInfo.id;
        openSteps.push(message);
      } else if (openGroupId === groupInfo.id) {
        openSteps.push(message);
      } else {
        flush();
        openGroupId = groupInfo.id;
        openSteps.push(message);
      }
      continue;
    }
    if (openSteps.length > 0 && isReasoningMessage(message)) {
      openSteps.push(message);
      continue;
    }
    // User-facing text, errors and ungrouped tool calls close the open group.
    // Reasoning is handled above so it stays in stream order within the group.
    flush();
    items.push({ kind: "message", message });
  }
  flush();

  return { items, groups };
}
