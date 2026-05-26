import { describe, expect, it } from "vitest";
import {
  AgentScopeRuntimeContentType,
  AgentScopeRuntimeMessageRole,
  AgentScopeRuntimeMessageType,
  AgentScopeRuntimeRunStatus,
  IAgentScopeRuntimeResponse,
} from "../types";
import { getCompletedReasoningFallbackText } from "./reasoningFallback";

function response(
  overrides: Partial<IAgentScopeRuntimeResponse>,
): IAgentScopeRuntimeResponse {
  return {
    id: "response-1",
    object: "response",
    status: AgentScopeRuntimeRunStatus.Completed,
    created_at: 1,
    output: [],
    ...overrides,
  };
}

describe("getCompletedReasoningFallbackText", () => {
  it("returns the last reasoning text when completed output has no body message", () => {
    const data = response({
      output: [
        {
          id: "reason-1",
          object: "message",
          role: AgentScopeRuntimeMessageRole.ASSISTANT,
          type: AgentScopeRuntimeMessageType.REASONING,
          status: AgentScopeRuntimeRunStatus.Completed,
          content: [
            {
              object: "content",
              type: AgentScopeRuntimeContentType.TEXT,
              text: "  这是被误归类到 think 的正文  ",
              status: AgentScopeRuntimeRunStatus.Completed,
            },
          ],
        },
      ],
    });

    expect(getCompletedReasoningFallbackText(data)).toBe(
      "这是被误归类到 think 的正文",
    );
  });

  it("does not return fallback text before the stream is completed", () => {
    const data = response({
      status: AgentScopeRuntimeRunStatus.InProgress,
      output: [
        {
          id: "reason-1",
          object: "message",
          role: AgentScopeRuntimeMessageRole.ASSISTANT,
          type: AgentScopeRuntimeMessageType.REASONING,
          status: AgentScopeRuntimeRunStatus.InProgress,
          content: [
            {
              object: "content",
              type: AgentScopeRuntimeContentType.TEXT,
              text: "还在流式输出",
              status: AgentScopeRuntimeRunStatus.InProgress,
            },
          ],
        },
      ],
    });

    expect(getCompletedReasoningFallbackText(data)).toBe("");
  });

  it("keeps normal assistant body messages as the source of truth", () => {
    const data = response({
      output: [
        {
          id: "reason-1",
          object: "message",
          role: AgentScopeRuntimeMessageRole.ASSISTANT,
          type: AgentScopeRuntimeMessageType.REASONING,
          status: AgentScopeRuntimeRunStatus.Completed,
          content: [
            {
              object: "content",
              type: AgentScopeRuntimeContentType.TEXT,
              text: "模型思考",
              status: AgentScopeRuntimeRunStatus.Completed,
            },
          ],
        },
        {
          id: "message-1",
          object: "message",
          role: AgentScopeRuntimeMessageRole.ASSISTANT,
          type: AgentScopeRuntimeMessageType.MESSAGE,
          status: AgentScopeRuntimeRunStatus.Completed,
          content: [
            {
              object: "content",
              type: AgentScopeRuntimeContentType.TEXT,
              text: "这是正常正文",
              status: AgentScopeRuntimeRunStatus.Completed,
            },
          ],
        },
      ],
    });

    expect(getCompletedReasoningFallbackText(data)).toBe("");
  });

  it("returns trailing reasoning when earlier body text exists in the same response", () => {
    const data = response({
      output: [
        {
          id: "message-1",
          object: "message",
          role: AgentScopeRuntimeMessageRole.ASSISTANT,
          type: AgentScopeRuntimeMessageType.MESSAGE,
          status: AgentScopeRuntimeRunStatus.Completed,
          content: [
            {
              object: "content",
              type: AgentScopeRuntimeContentType.TEXT,
              text: "前面已经正常展示的正文",
              status: AgentScopeRuntimeRunStatus.Completed,
            },
          ],
        },
        {
          id: "reason-1",
          object: "message",
          role: AgentScopeRuntimeMessageRole.ASSISTANT,
          type: AgentScopeRuntimeMessageType.REASONING,
          status: AgentScopeRuntimeRunStatus.Completed,
          content: [
            {
              object: "content",
              type: AgentScopeRuntimeContentType.TEXT,
              text: "最后被误归类到 Thinking 的正文",
              status: AgentScopeRuntimeRunStatus.Completed,
            },
          ],
        },
      ],
    });

    expect(getCompletedReasoningFallbackText(data)).toBe(
      "最后被误归类到 Thinking 的正文",
    );
  });

  it("returns trailing reasoning for idle historical responses after output is done", () => {
    const data = response({
      status: "idle" as AgentScopeRuntimeRunStatus,
      output: [
        {
          id: "reason-1",
          object: "message",
          role: AgentScopeRuntimeMessageRole.ASSISTANT,
          type: AgentScopeRuntimeMessageType.REASONING,
          status: AgentScopeRuntimeRunStatus.Completed,
          content: [
            {
              object: "content",
              type: AgentScopeRuntimeContentType.TEXT,
              text: "历史记录里的最终 Thinking 正文",
              status: null as unknown as AgentScopeRuntimeRunStatus,
            },
          ],
        },
      ],
    });

    expect(getCompletedReasoningFallbackText(data)).toBe(
      "历史记录里的最终 Thinking 正文",
    );
  });

  it("does not return fallback when visible body appears after reasoning", () => {
    const data = response({
      output: [
        {
          id: "reason-1",
          object: "message",
          role: AgentScopeRuntimeMessageRole.ASSISTANT,
          type: AgentScopeRuntimeMessageType.REASONING,
          status: AgentScopeRuntimeRunStatus.Completed,
          content: [
            {
              object: "content",
              type: AgentScopeRuntimeContentType.TEXT,
              text: "正常思考",
              status: AgentScopeRuntimeRunStatus.Completed,
            },
          ],
        },
        {
          id: "message-1",
          object: "message",
          role: AgentScopeRuntimeMessageRole.ASSISTANT,
          type: AgentScopeRuntimeMessageType.MESSAGE,
          status: AgentScopeRuntimeRunStatus.Completed,
          content: [
            {
              object: "content",
              type: AgentScopeRuntimeContentType.TEXT,
              text: "后续正文已经正常展示",
              status: AgentScopeRuntimeRunStatus.Completed,
            },
          ],
        },
      ],
    });

    expect(getCompletedReasoningFallbackText(data)).toBe("");
  });

  it("does not return fallback when a tool card appears after reasoning", () => {
    const data = response({
      output: [
        {
          id: "reason-1",
          object: "message",
          role: AgentScopeRuntimeMessageRole.ASSISTANT,
          type: AgentScopeRuntimeMessageType.REASONING,
          status: AgentScopeRuntimeRunStatus.Completed,
          content: [
            {
              object: "content",
              type: AgentScopeRuntimeContentType.TEXT,
              text: "正常工具调用前思考",
              status: AgentScopeRuntimeRunStatus.Completed,
            },
          ],
        },
        {
          id: "tool-1",
          object: "message",
          role: AgentScopeRuntimeMessageRole.ASSISTANT,
          type: AgentScopeRuntimeMessageType.MCP_CALL,
          status: AgentScopeRuntimeRunStatus.Completed,
          content: [
            {
              object: "content",
              type: AgentScopeRuntimeContentType.DATA,
              data: {
                name: "read_file",
              },
              status: AgentScopeRuntimeRunStatus.Completed,
            },
          ],
        },
      ],
    });

    expect(getCompletedReasoningFallbackText(data)).toBe("");
  });
});
