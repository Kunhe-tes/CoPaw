import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TaskRunGroupCard from ".";
import type { ChatTaskRunGroupCardData } from "../../messageMeta";

type TaskRunMessage = ChatTaskRunGroupCardData["finalMessages"][number];
type MockResponseData = {
  id: string;
  output?: Array<{
    id?: string;
    type?: string;
    content?: Array<{
      file_url?: string;
      text?: string;
    }>;
  }>;
};

function getStepResponseIds() {
  return Array.from(
    screen
      .getByTestId("task-run-steps")
      .querySelectorAll("[data-testid^='response-']"),
  ).map((element) => element.getAttribute("data-testid"));
}

vi.mock("../RuntimeRequestCard", () => ({
  default: ({ data }: { data: { id: string } }) => (
    <div data-testid={`request-${data.id}`}>{data.id}</div>
  ),
}));

vi.mock("../RuntimeResponseCard", () => ({
  default: ({
    data,
    showFeedback,
  }: {
    data: MockResponseData;
    showFeedback?: boolean;
  }) => {
    const firstContent = data.output?.[0]?.content?.[0];
    const output = data.output || [];
    return (
      <div
        data-output={firstContent?.text || firstContent?.file_url || ""}
        data-output-count={output.length}
        data-output-ids={output.map((item) => item.id).join(",")}
        data-output-types={output.map((item) => item.type).join(",")}
        data-show-feedback={String(showFeedback)}
        data-testid={`response-${data.id}`}
      >
        {data.id}
      </div>
    );
  },
}));

vi.mock("../ApprovalActionCard", () => ({
  default: ({ data }: { data: { requestId: string } }) => (
    <div data-testid={`approval-${data.requestId}`}>{data.requestId}</div>
  ),
}));

function messageWithResponse(
  messageId: string,
  responseId: string,
): TaskRunMessage {
  return {
    id: messageId,
    role: "assistant",
    cards: [
      {
        code: "AgentScopeRuntimeResponseCard",
        data: {
          id: responseId,
          status: "completed",
          created_at: 0,
          output: [
            {
              id: `${responseId}-message`,
              role: "assistant",
              type: "message",
              status: "completed",
              content: [
                {
                  type: "text",
                  text: responseId,
                },
              ],
            },
          ],
        },
      },
    ],
  };
}

function messageWithAutoPreviewResponse(
  messageId: string,
  responseId: string,
): TaskRunMessage {
  return {
    id: messageId,
    role: "assistant",
    cards: [
      {
        code: "AgentScopeRuntimeResponseCard",
        data: {
          id: responseId,
          status: "completed",
          created_at: 0,
          output: [
            {
              id: `${responseId}-message`,
              role: "assistant",
              type: "message",
              status: "completed",
              content: [
                {
                  type: "file",
                  status: "completed",
                  file_url:
                    "https://example.test/static/report[auto-preview].html",
                  file_name: "report[auto-preview].html",
                },
              ],
            },
          ],
        },
      },
    ],
  };
}

function messageWithAutoPreviewTextResponse(
  messageId: string,
  responseId: string,
): TaskRunMessage {
  return {
    id: messageId,
    role: "assistant",
    cards: [
      {
        code: "AgentScopeRuntimeResponseCard",
        data: {
          id: responseId,
          status: "completed",
          created_at: 0,
          output: [
            {
              id: `${responseId}-reasoning`,
              role: "assistant",
              type: "reasoning",
              status: "completed",
              content: [
                {
                  type: "text",
                  text:
                    "URL是：\n" +
                    "https://example.test/static/customer-list-auto-preview-1780020020982.html\n\n" +
                    "这是一个预览页面。",
                },
              ],
            },
          ],
        },
      },
    ],
  };
}

function taskRunData(
  overrides: Partial<ChatTaskRunGroupCardData> = {},
): ChatTaskRunGroupCardData {
  return {
    runId: "run-1",
    runIndex: 0,
    taskName: "daily-check",
    finalMessages: [messageWithResponse("final-message", "final-response")],
    stepMessages: [messageWithResponse("step-message", "step-response")],
    ...overrides,
  } as ChatTaskRunGroupCardData;
}

describe("TaskRunGroupCard", () => {
  afterEach(() => {
    cleanup();
  });

  it("collapses step messages behind a step toggle", () => {
    render(<TaskRunGroupCard data={taskRunData()} />);

    expect(screen.getByTestId("response-final-response")).toBeInTheDocument();
    expect(screen.getByTestId("task-run-toggle")).toBeInTheDocument();
    expect(screen.queryByTestId("task-run-steps")).toBeNull();
    expect(screen.queryByTestId("response-step-response")).toBeNull();

    fireEvent.click(screen.getByTestId("task-run-toggle"));

    expect(screen.getByTestId("task-run-steps")).toBeInTheDocument();
    expect(screen.getByTestId("response-step-response")).toBeInTheDocument();
  });

  it("keeps historical step messages behind the step toggle after expanding history", () => {
    render(
      <TaskRunGroupCard data={taskRunData({ collapsedByDefault: true })} />,
    );

    fireEvent.click(screen.getByTestId("task-run-result-toggle"));

    expect(screen.getByTestId("response-final-response")).toBeInTheDocument();
    expect(screen.getByTestId("task-run-toggle")).toBeInTheDocument();
    expect(screen.queryByTestId("task-run-steps")).toBeNull();

    fireEvent.click(screen.getByTestId("task-run-toggle"));

    expect(screen.getByTestId("task-run-steps")).toBeInTheDocument();
    expect(screen.getByTestId("response-step-response")).toBeInTheDocument();
  });

  it("shows only the auto-preview HTML card outside and moves all run messages into steps", () => {
    render(
      <TaskRunGroupCard
        data={taskRunData({
          finalMessages: [
            messageWithResponse("final-message", "final-response"),
          ],
          stepMessages: [
            messageWithResponse("step-message", "step-response"),
            messageWithAutoPreviewResponse(
              "preview-message",
              "preview-response",
            ),
          ],
        })}
      />,
    );

    expect(screen.getByTestId("response-preview-response")).toBeInTheDocument();
    expect(screen.getByTestId("response-preview-response")).toHaveAttribute(
      "data-show-feedback",
      "true",
    );
    expect(screen.queryByTestId("response-final-response")).toBeNull();
    expect(screen.queryByTestId("response-step-response")).toBeNull();
    expect(screen.queryByTestId("task-run-steps")).toBeNull();

    fireEvent.click(screen.getByTestId("task-run-toggle"));

    expect(screen.getByTestId("task-run-steps")).toBeInTheDocument();
    expect(screen.getByTestId("response-step-response")).toBeInTheDocument();
    expect(screen.getAllByTestId("response-preview-response")).toHaveLength(1);
    expect(getStepResponseIds()).toEqual([
      "response-step-response",
    ]);
    expect(screen.getByTestId("response-step-response")).toHaveAttribute(
      "data-show-feedback",
      "false",
    );
    expect(screen.getByTestId("response-step-response")).toHaveAttribute(
      "data-output-ids",
      "step-response-message,preview-response-message,final-response-message",
    );
  });

  it("detects an auto-preview HTML URL embedded in step reasoning text", () => {
    render(
      <TaskRunGroupCard
        data={taskRunData({
          finalMessages: [
            messageWithResponse("final-message", "final-response"),
          ],
          stepMessages: [
            messageWithAutoPreviewTextResponse(
              "reasoning-message",
              "reasoning-response",
            ),
          ],
        })}
      />,
    );

    expect(screen.getByTestId("response-reasoning-response")).toHaveAttribute(
      "data-output",
      "[customer-list-auto-preview-1780020020982.html](https://example.test/static/customer-list-auto-preview-1780020020982.html)",
    );
    expect(screen.queryByTestId("response-final-response")).toBeNull();

    fireEvent.click(screen.getByTestId("task-run-toggle"));

    expect(screen.getAllByTestId("response-reasoning-response")).toHaveLength(
      2,
    );
    expect(getStepResponseIds()).toEqual([
      "response-reasoning-response",
    ]);
    expect(screen.getAllByTestId("response-reasoning-response")[1]).toHaveAttribute(
      "data-output-ids",
      "reasoning-response-reasoning,final-response-message",
    );
    expect(screen.getAllByTestId("response-reasoning-response")[1]).toHaveAttribute(
      "data-output-types",
      "reasoning,message",
    );
  });
});
