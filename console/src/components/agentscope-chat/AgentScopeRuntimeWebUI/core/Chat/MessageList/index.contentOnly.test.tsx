import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatContentOnlyProvider } from "@/components/agentscope-chat/ChatContentOnlyContext";
import MessageList from ".";

const mocks = vi.hoisted(() => ({
  messagesContext: {},
  sessionsContext: {},
  messages: [] as Array<{ id: string }>,
  isSessionLoading: false,
}));

vi.mock("use-context-selector", () => ({
  useContextSelector: (
    context: unknown,
    selector: (value: unknown) => unknown,
  ) => {
    if (context === mocks.messagesContext) {
      return selector({ messages: mocks.messages });
    }
    return selector({
      currentSessionId: "chat-1",
      isSessionLoading: mocks.isSessionLoading,
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
    List: ({ items }: { items: unknown[] }) => (
      <div data-testid="bubble-list">{items.length}</div>
    ),
  },
  useProviderContext: () => ({
    getPrefixCls: (name: string) => `copaw-${name}`,
  }),
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
  Result: ({
    title,
    subTitle,
  }: {
    title: React.ReactNode;
    subTitle: React.ReactNode;
  }) => (
    <div data-testid="not-found">
      {title}
      {subTitle}
    </div>
  ),
  Spin: () => <div data-testid="spin">loading</div>,
}));

describe("MessageList content-only composition", () => {
  beforeEach(() => {
    mocks.messages = [];
    mocks.isSessionLoading = false;
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
  });

  it("shows a friendly not-found state only in content-only mode", () => {
    const { rerender } = render(
      <MessageList onSubmit={vi.fn()} sessionNotFound />,
    );

    expect(screen.queryByTestId("not-found")).not.toBeInTheDocument();
    expect(screen.getByTestId("welcome")).toBeInTheDocument();

    rerender(
      <ChatContentOnlyProvider enabled>
        <MessageList onSubmit={vi.fn()} sessionNotFound />
      </ChatContentOnlyProvider>,
    );

    expect(screen.getByTestId("not-found")).toHaveTextContent(
      "会话不存在当前会话可能已被删除，或访问链接已经失效。",
    );
    expect(screen.queryByTestId("welcome")).not.toBeInTheDocument();
  });

  it("keeps the existing session loading state unchanged", () => {
    mocks.isSessionLoading = true;

    render(
      <ChatContentOnlyProvider enabled>
        <MessageList onSubmit={vi.fn()} />
      </ChatContentOnlyProvider>,
    );

    expect(screen.getByTestId("spin")).toBeInTheDocument();
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
});
