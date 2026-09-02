import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { prepareShareMessages } from "./shareView";

vi.mock("react-router-dom", () => ({
  useParams: () => ({ token: "token-1" }),
}));

vi.mock("@/api/modules/chat", () => ({
  chatApi: {
    getChatShare: vi.fn().mockResolvedValue({
      chat_name: "测试会话",
      messages: [{ id: "message-1", role: "user", content: "你好" }],
    }),
  },
}));

vi.mock("antd", () => ({
  Alert: ({ message }: { message: string }) => <div>{message}</div>,
  Empty: ({ description }: { description: string }) => <div>{description}</div>,
  Spin: () => <div>loading</div>,
}));

vi.mock("@/components/agentscope-chat", () => ({
  Bubble: {
    List: ({ classNames }: { classNames?: { wrapper?: string } }) => (
      <div className={classNames?.wrapper} data-testid="share-bubble-list" />
    ),
  },
  AgentScopeRuntimeWebUIComposedProvider: ({
    children,
  }: {
    children: React.ReactNode;
  }) => <>{children}</>,
  HtmlPreviewTrackingProvider: ({
    children,
  }: {
    children: React.ReactNode;
  }) => <>{children}</>,
}));

vi.mock("../Chat/sessionApi", () => ({
  convertMessages: (messages: unknown[]) => messages,
}));

vi.mock("../Chat/components/RuntimeRequestCard", () => ({
  default: () => null,
}));
vi.mock(
  "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/AgentScopeRuntime/Response/Card",
  () => ({ default: () => null }),
);

describe("ChatSharePage message preparation", () => {
  it("keeps structured cards and maps unknown cards to a read-only view", () => {
    const [message] = prepareShareMessages([
      {
        id: "turn-1",
        role: "assistant",
        cards: [
          { code: "AgentScopeRuntimeResponseCard", data: {} },
          { code: "ApprovalAction", data: { requestId: "approval-1" } },
          { code: "PlanInteraction", data: { planId: "plan-1" } },
          { code: "TaskRunGroupCard", data: { runId: "run-1" } },
          { code: "ResponseFeedback", data: { responseId: "response-1" } },
          { code: "UnknownCard", data: { value: "kept" } },
        ],
      },
    ] as never);
    expect(message.cards?.map((card) => card.code)).toEqual([
      "AgentScopeRuntimeResponseCard",
      "ApprovalAction",
      "PlanInteraction",
      "TaskRunGroupCard",
      "ResponseFeedback",
      "ReadOnlyStructuredCard",
    ]);
    expect(message.cards?.[message.cards.length - 1]?.data).toEqual({
      code: "UnknownCard",
      data: { value: "kept" },
    });
  });

  it("renders a bounded message viewport for long read-only conversations", async () => {
    const { default: ChatSharePage } = await import(".");
    render(<ChatSharePage />);

    await waitFor(() => {
      expect(screen.getByTestId("share-bubble-list")).toBeInTheDocument();
    });
    expect(screen.getByTestId("share-message-viewport")).toBeInTheDocument();
  });
});
