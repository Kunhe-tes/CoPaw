import { AgentScopeRuntimeRunStatus } from "../types";

type ToolStatusValue = "running" | "success" | "failed";

type ToolStatusData = {
  tool_status?: unknown;
  [key: string]: unknown;
};

function getToolStatus(data?: ToolStatusData): ToolStatusValue | undefined {
  const status = data?.tool_status;
  if (status === "running" || status === "success" || status === "failed") {
    return status;
  }
  return undefined;
}

export function resolveToolMessageStatus({
  messageStatus,
  hasOutputContent = false,
  inputData,
  outputData,
}: {
  messageStatus: AgentScopeRuntimeRunStatus;
  hasOutputContent?: boolean;
  inputData?: ToolStatusData;
  outputData?: ToolStatusData;
}): AgentScopeRuntimeRunStatus {
  const outputToolStatus = getToolStatus(outputData);
  const inputToolStatus = hasOutputContent ? undefined : getToolStatus(inputData);
  const toolStatus = outputToolStatus || inputToolStatus;

  switch (toolStatus) {
    case "running":
      return AgentScopeRuntimeRunStatus.InProgress;
    case "failed":
      return AgentScopeRuntimeRunStatus.Failed;
    case "success":
      return AgentScopeRuntimeRunStatus.Completed;
    default:
      return messageStatus;
  }
}

export function isToolMessageLoading(status?: string) {
  return status === AgentScopeRuntimeRunStatus.InProgress;
}
