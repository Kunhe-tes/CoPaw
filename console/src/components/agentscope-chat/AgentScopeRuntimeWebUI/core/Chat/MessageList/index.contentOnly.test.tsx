import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { forwardRef, useImperativeHandle, useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatContentOnlyProvider } from "@/components/agentscope-chat/ChatContentOnlyContext";
import MessageList from ".";

const mocks = vi.hoisted(() => ({
  messagesContext: {},
  sessionsContext: {},
  messages: [] as Array<{ id: string; history?: boolean }>,
  setMessages: vi.fn(),
  isSessionLoading: false,
  sessionNotFound: false,
  currentSessionId: "chat-1",
}));

const apiMocks = vi.hoisted(() => ({
  getChatHistory: vi.fn(),
  getChatIdForSession: vi.fn(),
  getSession: vi.fn(),
  scrollToBottom: vi.fn(),
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
      currentSessionId: mocks.currentSessionId,
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
    List: forwardRef(
      (
        {
          items,
          onReachStart,
          onBottomStateChange,
          topContent,
        }: {
          items: unknown[];
          onReachStart?: () => void;
          onBottomStateChange?: (isAtBottom: boolean) => void;
          topContent?: React.ReactNode;
        },
        ref,
      ) => {
        const scrollRef = useRef<HTMLDivElement | null>(null);
        useImperativeHandle(ref, () => ({
          getScrollElement: () => scrollRef.current,
          scrollToBottom: apiMocks.scrollToBottom,
        }));
        return (
          <div
            data-testid="bubble-list"
            onPointerMove={onReachStart}
            ref={(element) => {
              scrollRef.current = element;
              if (!element) return;
              Object.defineProperties(element, {
                clientHeight: { configurable: true, value: 400 },
                scrollHeight: { configurable: true, value: 1000 },
                scrollTop: {
                  configurable: true,
                  value: 0,
                  writable: true,
                },
              });
            }}
          >
            {topContent}
            {items.length}
            <button
              onClick={() => onBottomStateChange?.(false)}
              type="button"
            >
              标记为浏览历史
            </button>
          </div>
        );
      },
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
  convertArchivedPage: (
    messages: Array<{ id: string }>,
    boundaries: Array<{ id: string }> = [],
  ) => [
    ...messages,
    ...boundaries.map((boundary) => ({
      id: `conversation-compaction-${boundary.id}`,
    })),
  ],
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
    apiMocks.scrollToBottom.mockReset();
    apiMocks.getChatIdForSession.mockReturnValue("chat-real-1");
    mocks.isSessionLoading = false;
    mocks.sessionNotFound = false;
    mocks.currentSessionId = "chat-1";
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

  it("does not request archived history until normal scrolling enters the preload range", async () => {
    mocks.messages = [{ id: "online-message", history: true }];
    render(
      <ChatContentOnlyProvider enabled>
        <MessageList onSubmit={vi.fn()} />
      </ChatContentOnlyProvider>,
    );

    const bubbleList = screen.getByTestId("bubble-list");
    bubbleList.scrollTop = -300;
    fireEvent.scroll(bubbleList);

    expect(apiMocks.getChatHistory).not.toHaveBeenCalled();
  });

  it("loads archived history with the resolved backend chat ID while normal scrolling nears the top", async () => {
    mocks.messages = [{ id: "online-message", history: true }];
    let resolveHistory!: (page: {
      messages: Array<{ id: string }>;
      boundaries: never[];
      has_more: boolean;
      next_cursor: null;
    }) => void;
    apiMocks.getChatHistory.mockReturnValue(
      new Promise((resolve) => {
        resolveHistory = resolve;
      }),
    );

    render(
      <ChatContentOnlyProvider enabled>
        <MessageList onSubmit={vi.fn()} />
      </ChatContentOnlyProvider>,
    );

    const bubbleList = screen.getByTestId("bubble-list");
    bubbleList.scrollTop = -380;
    fireEvent.scroll(bubbleList);

    expect(screen.getByRole("status")).toHaveTextContent(
      "正在加载更早的消息…",
    );
    expect(screen.getByRole("status")).toHaveStyle({ flexShrink: "0" });
    expect(screen.getByTestId("bubble-list")).toContainElement(
      screen.getByRole("status"),
    );

    await waitFor(() => {
      expect(apiMocks.getChatHistory).toHaveBeenCalledWith("chat-real-1", null);
    });
    resolveHistory({
      messages: [{ id: "archived-message" }],
      boundaries: [],
      has_more: false,
      next_cursor: null,
    });
    await waitFor(() => {
      expect(mocks.messages).toEqual([
        { id: "archived-message", history: true },
        { id: "online-message", history: true },
      ]);
    });
    expect(screen.getByRole("status")).not.toHaveTextContent(
      "已到达会话开始处",
    );
    expect(mocks.messages).toEqual([
      { id: "archived-message", history: true },
      { id: "online-message", history: true },
    ]);
  });

  it("only shows the start-of-conversation state when a terminal page adds no history", async () => {
    mocks.messages = [{ id: "online-message", history: true }];
    apiMocks.getChatHistory.mockResolvedValue({
      messages: [],
      boundaries: [],
      has_more: false,
      next_cursor: null,
    });

    render(
      <ChatContentOnlyProvider enabled>
        <MessageList onSubmit={vi.fn()} />
      </ChatContentOnlyProvider>,
    );

    const bubbleList = screen.getByTestId("bubble-list");
    bubbleList.scrollTop = -380;
    fireEvent.scroll(bubbleList);

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        "已到达会话开始处",
      );
    });
    expect(mocks.messages).toEqual([{ id: "online-message", history: true }]);
  });

  it("keeps loaded messages and exposes a retry action when history loading fails", async () => {
    mocks.messages = [{ id: "online-message", history: true }];
    apiMocks.getChatHistory.mockRejectedValueOnce(new Error("offline"));
    apiMocks.getChatHistory.mockResolvedValueOnce({
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

    const bubbleList = screen.getByTestId("bubble-list");
    bubbleList.scrollTop = -380;
    fireEvent.scroll(bubbleList);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("加载历史消息失败");
    });
    expect(mocks.messages).toEqual([{ id: "online-message", history: true }]);

    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => {
      expect(apiMocks.getChatHistory).toHaveBeenCalledTimes(2);
    });
    expect(mocks.messages).toEqual([
      { id: "archived-message", history: true },
      { id: "online-message", history: true },
    ]);
  });

  it("does not pull the reader back to the latest message after they enter history", () => {
    mocks.messages = [{ id: "online-message" }];
    const rendered = render(
      <ChatContentOnlyProvider enabled>
        <MessageList onSubmit={vi.fn()} />
      </ChatContentOnlyProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "标记为浏览历史" }));
    mocks.messages = [
      { id: "online-message" },
      { id: "new-message" },
    ];
    rendered.rerender(
      <ChatContentOnlyProvider enabled>
        <MessageList onSubmit={vi.fn()} />
      </ChatContentOnlyProvider>,
    );

    expect(apiMocks.scrollToBottom).not.toHaveBeenCalled();
  });

  it("keeps an existing compaction divider when its archive page is loaded", async () => {
    mocks.messages = [
      { id: "conversation-compaction-boundary-1", history: true },
      { id: "online-message", history: true },
    ];
    apiMocks.getChatHistory.mockResolvedValue({
      messages: [{ id: "archived-message" }],
      boundaries: [{ id: "boundary-1" }],
      has_more: false,
      next_cursor: null,
    });

    render(
      <ChatContentOnlyProvider enabled>
        <MessageList onSubmit={vi.fn()} />
      </ChatContentOnlyProvider>,
    );

    const bubbleList = screen.getByTestId("bubble-list");
    bubbleList.scrollTop = -380;
    fireEvent.scroll(bubbleList);

    await waitFor(() => {
      expect(mocks.messages).toEqual([
        { id: "archived-message", history: true },
        { id: "conversation-compaction-boundary-1", history: true },
        { id: "online-message", history: true },
      ]);
    });
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

  it("does not let an earlier compaction refresh overwrite a switched session", async () => {
    mocks.messages = [{ id: "message-for-chat-1" }];
    let resolveSession!: (value: { messages: Array<{ id: string }> }) => void;
    apiMocks.getSession.mockReturnValue(
      new Promise((resolve) => {
        resolveSession = resolve;
      }),
    );
    apiMocks.getChatIdForSession.mockImplementation((sessionId: string) =>
      sessionId === "chat-1" ? "chat-real-1" : "chat-real-2",
    );

    const rendered = render(
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

    mocks.currentSessionId = "chat-2";
    mocks.messages = [{ id: "message-for-chat-2" }];
    rendered.rerender(
      <ChatContentOnlyProvider enabled>
        <MessageList onSubmit={vi.fn()} />
      </ChatContentOnlyProvider>,
    );
    resolveSession({ messages: [{ id: "stale-message-for-chat-1" }] });

    await Promise.resolve();
    expect(mocks.messages).toEqual([{ id: "message-for-chat-2" }]);
  });
});
