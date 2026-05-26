import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import ReadOnlySessionChat from "./ReadOnlySessionChat";

const tracingApiMock = vi.hoisted(() => ({
  getUserChat: vi.fn(),
}));

vi.mock("../../../../../api/modules/tracing", () => ({
  tracingApi: tracingApiMock,
}));

vi.mock("../../../../Chat/sessionApi", () => ({
  convertMessages: (messages: unknown[]) => messages,
}));

vi.mock("../../../../Chat/components/RuntimeRequestCard", () => ({
  default: () => <div data-testid="runtime-request-card" />,
}));

vi.mock("../../../../Chat/components/RuntimeResponseCard", () => ({
  default: () => <div data-testid="runtime-response-card" />,
}));

vi.mock("@/components/agentscope-chat", () => ({
  AgentScopeRuntimeWebUIComposedProvider: ({
    children,
  }: {
    children: ReactNode;
  }) => <div data-testid="chat-provider">{children}</div>,
  Bubble: {
    List: ({ items }: { items: unknown[] }) => (
      <div data-testid="bubble-list">{items.length}</div>
    ),
  },
}));

describe("ReadOnlySessionChat", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads history with mapped chat id", async () => {
    tracingApiMock.getUserChat.mockResolvedValue({
      messages: [{ id: "message-1", role: "assistant", content: [] }],
    });

    render(
      <ReadOnlySessionChat
        selectedSessionId="cron-task:job-1"
        chatIdBySessionId={{ "cron-task:job-1": "chat-uuid-1" }}
        targetUserId="user-001"
      />,
    );

    await waitFor(() => {
      expect(tracingApiMock.getUserChat).toHaveBeenCalledWith(
        "user-001",
        "chat-uuid-1",
      );
    });
  });

  it("does not call chat detail when mapping is missing", async () => {
    render(
      <ReadOnlySessionChat
        selectedSessionId="cron-task:missing-job"
        chatIdBySessionId={{}}
      />,
    );

    await screen.findByText("暂无聊天内容");
    expect(tracingApiMock.getUserChat).not.toHaveBeenCalled();
  });
});
