import type { IDataContent, IAgentScopeRuntimeMessage } from "../types";
import {
  AgentScopeRuntimeContentType,
  AgentScopeRuntimeMessageType,
  AgentScopeRuntimeRunStatus,
} from "../types";

export function getToolMessageKey(data: {
  call_id?: string;
  id?: string;
  tool_call_id?: string;
  name?: string;
  tool_name?: string;
  tool?: string;
  mcp_tool_name?: string;
}) {
  return (
    data.call_id ||
    data.id ||
    data.tool_call_id ||
    data.name ||
    data.tool_name ||
    data.tool ||
    data.mcp_tool_name
  );
}

export function maybeToolOutput(message: IAgentScopeRuntimeMessage) {
  return [
    AgentScopeRuntimeMessageType.FUNCTION_CALL_OUTPUT,
    AgentScopeRuntimeMessageType.PLUGIN_CALL_OUTPUT,
    AgentScopeRuntimeMessageType.COMPONENT_CALL_OUTPUT,
    AgentScopeRuntimeMessageType.MCP_CALL_OUTPUT,
  ].includes(message.type);
}

export function maybeToolInput(message: IAgentScopeRuntimeMessage) {
  return [
    AgentScopeRuntimeMessageType.FUNCTION_CALL,
    AgentScopeRuntimeMessageType.PLUGIN_CALL,
    AgentScopeRuntimeMessageType.COMPONENT_CALL,
    AgentScopeRuntimeMessageType.MCP_CALL,
  ].includes(message.type);
}

type ToolFrame = {
  message: IAgentScopeRuntimeMessage;
  content: IDataContent;
};

type ToolPair = {
  index: number;
  callId?: string;
  name?: string;
  input?: ToolFrame;
  output?: ToolFrame;
};

function firstString(...values: unknown[]): string | undefined {
  return values.find(
    (value): value is string => typeof value === "string" && value.length > 0,
  );
}

function readToolPair(
  message: IAgentScopeRuntimeMessage,
  index: number,
): ToolPair | undefined {
  if (!maybeToolInput(message) && !maybeToolOutput(message)) return;
  const first = message.content?.[0];
  if (first?.type !== AgentScopeRuntimeContentType.DATA || !first.data) return;

  // Merged tool cards retain the input and output in the first two slots.
  const second = message.content[1];
  const merged = second?.type === AgentScopeRuntimeContentType.DATA;
  const data = first.data;
  const outputData = merged ? second.data : undefined;
  return {
    index,
    callId: firstString(
      data.call_id,
      data.id,
      data.tool_call_id,
      outputData?.call_id,
      outputData?.id,
      outputData?.tool_call_id,
    ),
    name: firstString(data.name, data.tool_name, data.tool, data.mcp_tool_name),
    input:
      merged || maybeToolInput(message)
        ? { message, content: first }
        : undefined,
    output:
      merged || maybeToolOutput(message)
        ? { message, content: merged ? second : first }
        : undefined,
  };
}

function isRunning(frame: ToolFrame) {
  return [
    AgentScopeRuntimeRunStatus.Created,
    AgentScopeRuntimeRunStatus.InProgress,
  ].includes(frame.message.status);
}

function combineToolPairs(target: ToolPair, source: ToolPair) {
  target.input = source.input ?? target.input;
  if (
    source.output &&
    (!target.output || isRunning(target.output) || !isRunning(source.output))
  ) {
    target.output = source.output;
  }
}

export function mergeToolMessages(messages: IAgentScopeRuntimeMessage[]) {
  const explicitPairs = new Map<string, ToolPair>();
  const pairsByIndex = new Map<number, ToolPair>();
  const pairsByName = new Map<string, Set<ToolPair>>();

  messages.forEach((message, index) => {
    const frame = readToolPair(message, index);
    if (!frame) return;
    const pair = (frame.callId && explicitPairs.get(frame.callId)) || frame;
    combineToolPairs(pair, frame);
    if (frame.callId) explicitPairs.set(frame.callId, pair);
    pairsByIndex.set(index, pair);
    if (frame.name) {
      const namedPairs = pairsByName.get(frame.name) || new Set<ToolPair>();
      namedPairs.add(pair);
      pairsByName.set(frame.name, namedPairs);
    }
  });

  // Legacy names are safe only when the entire response has one possible pair.
  for (const namedPairs of pairsByName.values()) {
    if (namedPairs.size !== 2) continue;
    const [first, second] = [...namedPairs].sort((a, b) => a.index - b.index);
    if (first.callId && second.callId) continue;
    if (Boolean(first.input) === Boolean(second.input)) continue;
    if (Boolean(first.output) === Boolean(second.output)) continue;
    combineToolPairs(first, second);
    pairsByIndex.set(second.index, first);
  }

  return messages.flatMap((message, index) => {
    const pair = pairsByIndex.get(index);
    if (!pair) return [message];
    if (pair.index !== index) return [];
    if (!pair.input || !pair.output) {
      return [pair.output?.message ?? pair.input?.message ?? message];
    }
    return [
      {
        ...pair.output.message,
        content: [pair.input.content, pair.output.content],
      },
    ];
  });
}
