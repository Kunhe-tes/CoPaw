import {
  AgentScopeRuntimeContentType,
  AgentScopeRuntimeMessageType,
  AgentScopeRuntimeRunStatus,
  IAgentScopeRuntimeMessage,
  IAgentScopeRuntimeResponse,
} from "../types";

function hasVisibleMessageContent(message: IAgentScopeRuntimeMessage) {
  if (message.type !== AgentScopeRuntimeMessageType.MESSAGE) {
    return false;
  }

  return Boolean(
    message.content?.some((content) => {
      switch (content.type) {
        case AgentScopeRuntimeContentType.TEXT:
          return Boolean(content.text?.trim());
        case AgentScopeRuntimeContentType.REFUSAL:
          return Boolean(content.refusal?.trim());
        case AgentScopeRuntimeContentType.IMAGE:
          return Boolean(content.image_url);
        case AgentScopeRuntimeContentType.VIDEO:
          return Boolean(content.video_url);
        case AgentScopeRuntimeContentType.FILE:
          return Boolean(
            content.file_url || content.file_name || content.fileName,
          );
        case AgentScopeRuntimeContentType.AUDIO:
          return Boolean(content.audio_url || content.data);
        case AgentScopeRuntimeContentType.DATA:
          return Boolean(content.data);
        default:
          return false;
      }
    }),
  );
}

function getReasoningText(message: IAgentScopeRuntimeMessage) {
  if (message.type !== AgentScopeRuntimeMessageType.REASONING) {
    return "";
  }

  return (
    message.content
      ?.filter((content) => content.type === AgentScopeRuntimeContentType.TEXT)
      .map((content) => content.text?.trim())
      .filter(Boolean)
      .join("\n\n") || ""
  );
}

function hasRenderableNonReasoningOutput(message: IAgentScopeRuntimeMessage) {
  if (message.type === AgentScopeRuntimeMessageType.REASONING) {
    return false;
  }

  if (message.type === AgentScopeRuntimeMessageType.HEARTBEAT) {
    return false;
  }

  if (hasVisibleMessageContent(message)) {
    return true;
  }

  return Boolean(
    message.message ||
      message.code ||
      message.content?.some((content) => {
        if (content.type === AgentScopeRuntimeContentType.DATA) {
          return Boolean(content.data);
        }
        return true;
      }),
  );
}

function isGeneratingStatus(status: unknown) {
  return (
    status === AgentScopeRuntimeRunStatus.Created ||
    status === AgentScopeRuntimeRunStatus.InProgress
  );
}

function isResponseReadyForFallback(
  response: IAgentScopeRuntimeResponse,
  messages: IAgentScopeRuntimeMessage[],
) {
  if (response.status === AgentScopeRuntimeRunStatus.Completed) {
    return true;
  }

  if (String(response.status) !== "idle") {
    return false;
  }

  return !messages.some((message) => {
    if (isGeneratingStatus(message.status)) {
      return true;
    }

    return message.content?.some((content) =>
      isGeneratingStatus(content.status),
    );
  });
}

export function getCompletedReasoningFallbackText(
  response: IAgentScopeRuntimeResponse,
  messages: IAgentScopeRuntimeMessage[] = response.output,
) {
  if (!isResponseReadyForFallback(response, messages)) {
    return "";
  }

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (hasRenderableNonReasoningOutput(message)) {
      return "";
    }

    const reasoningText = getReasoningText(message);
    if (reasoningText) {
      return reasoningText;
    }
  }

  return "";
}
