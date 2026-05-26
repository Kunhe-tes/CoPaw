import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AgentScopeRuntimeResponseCard from "./Card";
import {
  AgentScopeRuntimeContentType,
  AgentScopeRuntimeMessageRole,
  AgentScopeRuntimeMessageType,
  AgentScopeRuntimeRunStatus,
  IAgentScopeRuntimeMessage,
  IAgentScopeRuntimeResponse,
} from "../types";

vi.mock("@/components/agentscope-chat", () => ({
  Bubble: {
    Spin: () => <div data-testid="spin" />,
  },
  Markdown: ({ content }: { content: string }) => (
    <div data-testid="markdown">{content}</div>
  ),
}));

vi.mock("./Message", () => ({
  default: ({ data }: { data: IAgentScopeRuntimeMessage }) => (
    <div data-testid="message">{data.content?.[0]?.type}</div>
  ),
}));

vi.mock("./Reasoning", () => ({
  default: ({ data }: { data: IAgentScopeRuntimeMessage }) => (
    <div data-testid="reasoning">{data.content?.[0]?.type}</div>
  ),
}));

vi.mock("./Tool", () => ({
  default: () => <div data-testid="tool" />,
}));

vi.mock("./Error", () => ({
  default: () => <div data-testid="error" />,
}));

vi.mock("./Actions", () => ({
  default: () => <div data-testid="actions" />,
}));

vi.mock("./Suggestions", () => ({
  default: () => <div data-testid="suggestions" />,
}));

vi.mock("./RetryStatusMessage", () => ({
  default: () => <div data-testid="retry-status" />,
}));

function textMessage(
  id: string,
  text: string,
  type = AgentScopeRuntimeMessageType.MESSAGE,
): IAgentScopeRuntimeMessage {
  return {
    id,
    object: "message",
    role: AgentScopeRuntimeMessageRole.ASSISTANT,
    type,
    status: AgentScopeRuntimeRunStatus.Completed,
    content: [
      {
        object: "content",
        type: AgentScopeRuntimeContentType.TEXT,
        text,
        status: AgentScopeRuntimeRunStatus.Completed,
      },
    ],
  };
}

function response(
  output: IAgentScopeRuntimeMessage[],
): IAgentScopeRuntimeResponse {
  return {
    id: "response-1",
    object: "response",
    status: AgentScopeRuntimeRunStatus.Completed,
    created_at: 1,
    output,
  };
}

describe("AgentScopeRuntimeResponseCard", () => {
  it("renders fallback markdown when the final visible output is reasoning", () => {
    render(
      <AgentScopeRuntimeResponseCard
        data={response([
          textMessage("message-1", "前置正文"),
          textMessage(
            "reason-1",
            "最后被误归类到 Thinking 的正文",
            AgentScopeRuntimeMessageType.REASONING,
          ),
        ])}
      />,
    );

    expect(
      screen.getByText("最后被误归类到 Thinking 的正文"),
    ).toBeInTheDocument();
  });

  it("does not render fallback markdown when normal body text is the final output", () => {
    render(
      <AgentScopeRuntimeResponseCard
        data={response([
          textMessage(
            "reason-1",
            "正常思考",
            AgentScopeRuntimeMessageType.REASONING,
          ),
          textMessage("message-1", "最终正文"),
        ])}
      />,
    );

    expect(screen.queryByText("正常思考")).not.toBeInTheDocument();
  });
});
