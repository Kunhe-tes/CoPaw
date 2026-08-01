import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatContentOnlyProvider } from "@/components/agentscope-chat/ChatContentOnlyContext";
import MessageList from ".";

const mocks = vi.hoisted(() => ({
  messagesContext: {},
  sessionsContext: {},
  messages: [] as Array<{ id: string }>,
  setMessages: vi.fn(),
  isSessionLoading: false,
  sessionNotFound: false,
}));

const apiMocks = vi.hoisted(() => ({
  getChatHistory: vi.fn(),
  getChatIdForSession: vi.fn(),
  getSession: vi.fn(),
}));

vi.mock("use-context-selector", () => ({
  useContextSelector: (
    context: unknown,
    selector: (value: unknown) => unknown,
  ) => {
    if (context === mocks.messagesContext) {
      return selector({
        messages: mocks.messages,
        setMessages: mocks.setMessages,
      });
    }
    return selector({
      currentSessionId: "chat-1",
      isSessionLoading: mocks.isSessionLoading,
      sessionNotFound: mocks.sessionNotFound,
    });
  },
}));

vi.mock("../../Context/ChatAnywhereMessagesContext", () => ({
  ChatAnywhereMessagesContext: mocks.messagesContext,
}));

vi.mock("../../Context/ChatAnywhereSessionsContext", () => ({
  ChatAnywhereSessionsContext: mocks.sessionsContext,
}));

vi.mock("@/components/agentscope-chat", () => ({
  Bubble: {
    List: ({
      items,
      onReachStart,
    }: {
      items: unknown[];
      onReachStart?: () => void;
    }) => (
      <button data-testid="bubble-list" onClick={onReachStart}>
        {items.length}
      </button>
    ),
  },
  useProviderContext: () => ({
    getPrefixCls: (name: string) => `copaw-${name}`,
  }),
}));

vi.mock("@/api/modules/chat", () => ({
  chatApi: {
    getChatHistory: apiMocks.getChatHistory,
  },
}));

vi.mock("@/pages/Chat/sessionApi", () => ({
  convertMessages: (messages: Array<{ id: string }>) => messages,
  convertArchivedPage: (messages: Array<{ id: string }>) => messages,
  default: {
    getChatIdForSession: apiMocks.getChatIdForSession,
    getSession: apiMocks.getSession,
  },
}));

vi.mock("../../Context/ChatAnywhereOptionsContext", () => ({
  useChatAnywhereOptions: (
    selector: (value: { theme: { bubbleList: object } }) => unknown,
  ) => selector({ theme: { bubbleList: {} } }),
}));

vi.mock("../Welcome", () => ({
  default: () => <div data-testid="welcome">welcome</div>,
}));

vi.mock("antd", () => ({
  Result: ({ title, subTitle }: { title: string; subTitle: string }) => (
    <div data-testid="not-found-result">
      <span>{title}</span>
      <span>{subTitle}</span>
    </div>
  ),
  Spin: () => <div data-testid="spin">loading</div>,
}));

describe("MessageList content-only composition", () => {
  beforeEach(() => {
    mocks.messages = [];
    mocks.setMessages.mockReset();
    mocks.setMessages.mockImplementation((update) => {
      mocks.messages =
        typeof update === "function" ? update(mocks.messages) : update;
    });
    apiMocks.getChatHistory.mockReset();
    apiMocks.getChatIdForSession.mockReset();
    apiMocks.getSession.mockReset();
    apiMocks.getChatIdForSession.mockReturnValue("chat-real-1");
    mocks.isSessionLoading = false;
    mocks.sessionNotFound = false;
  });

  afterEach(() => {
    cleanup();
  });

  it("preserves the normal Welcome surface outside content-only mode", () => {
    render(<MessageList onSubmit={vi.fn()} />);

    expect(screen.getByTestId("welcome")).toBeInTheDocument();
  });

  it("does not mount the input-bearing Welcome surface in content-only mode", () => {
    render(
      <ChatContentOnlyProvider enabled>
        <MessageList onSubmit={vi.fn()} />
      </ChatContentOnlyProvider>,
    );

    expect(screen.queryByTestId("welcome")).not.toBeInTheDocument();
    expect(screen.queryByTestId("bubble-list")).not.toBeInTheDocument();
    expect(screen.queryByTestId("not-found-result")).not.toBeInTheDocument();
  });

  it("renders an unavailable result for an active content-only 404", () => {
    mocks.sessionNotFound = true;

    render(
      <ChatContentOnlyProvider enabled>
        <MessageList onSubmit={vi.fn()} />
      </ChatContentOnlyProvider>,
    );

    expect(screen.getByTestId("not-found-result")).toHaveTextContent(
      "会话不存在",
    );
    expect(screen.getByTestId("not-found-result")).toHaveTextContent(
      "该会话不存在或已被删除",
    );
    expect(screen.queryByTestId("welcome")).not.toBeInTheDocument();
  });

  it("does not replace normal chat with the content-only 404 result", () => {
    mocks.sessionNotFound = true;

    render(<MessageList onSubmit={vi.fn()} />);

    expect(screen.getByTestId("welcome")).toBeInTheDocument();
    expect(screen.queryByTestId("not-found-result")).not.toBeInTheDocument();
  });

  it("keeps the existing session loading state unchanged", () => {
    mocks.isSessionLoading = true;
    mocks.sessionNotFound = true;

    render(
      <ChatContentOnlyProvider enabled>
        <MessageList onSubmit={vi.fn()} />
      </ChatContentOnlyProvider>,
    );

    expect(screen.getByTestId("spin")).toBeInTheDocument();
    expect(screen.queryByTestId("not-found-result")).not.toBeInTheDocument();
  });

  it("keeps loaded messages on the existing Bubble list", () => {
    mocks.messages = [{ id: "message-1" }];

    render(
      <ChatContentOnlyProvider enabled>
        <MessageList onSubmit={vi.fn()} />
      </ChatContentOnlyProvider>,
    );

    expect(screen.getByTestId("bubble-list")).toHaveTextContent("1");
  });

  it("loads archived history with the resolved backend chat ID", async () => {
    mocks.messages = [{ id: "online-message" }];
    apiMocks.getChatHistory.mockResolvedValue({
      messages: [{ id: "archived-message" }],
      boundaries: [],
      has_more: false,
      next_cursor: null,
    });

    render(
      <ChatContentOnlyProvider enabled>
        <MessageList onSubmit={vi.fn()} />
      </ChatContentOnlyProvider>,
    );

    fireEvent.click(screen.getByTestId("bubble-list"));

    await waitFor(() => {
      expect(apiMocks.getChatHistory).toHaveBeenCalledWith(
        "chat-real-1",
        null,
      );
    });
    expect(mocks.messages).toEqual([
      { id: "archived-message" },
      { id: "online-message" },
    ]);
  });

  it("refreshes the active session when a compaction boundary arrives", async () => {
    mocks.messages = [{ id: "old-message" }];
    apiMocks.getSession.mockResolvedValue({
      messages: [{ id: "conversation-compaction-boundary-1" }],
    });

    render(
      <ChatContentOnlyProvider enabled>
        <MessageList onSubmit={vi.fn()} />
      </ChatContentOnlyProvider>,
    );

    document.dispatchEvent(
      new CustomEvent("conversation_compacted", {
        detail: { chat_id: "chat-real-1" },
      }),
    );

    await waitFor(() => {
      expect(apiMocks.getSession).toHaveBeenCalledWith("chat-1");
    });
    expect(mocks.messages).toEqual([
      { id: "conversation-compaction-boundary-1" },
    ]);
  });
});
