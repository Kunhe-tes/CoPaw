import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatContentOnlyProvider } from "@/components/agentscope-chat/ChatContentOnlyContext";
import Chat from ".";

const mocks = vi.hoisted(() => ({
  useChatAnywhereSessionLoader: vi.fn(),
}));

vi.mock("@/components/agentscope-chat", () => ({
  useProviderContext: () => ({
    getPrefixCls: (name: string) => `copaw-${name}`,
  }),
}));

vi.mock("use-context-selector", () => ({
  useContextSelector: (
    _context: unknown,
    selector: (value: { messages: Array<{ id: string }> }) => unknown,
  ) => selector({ messages: [{ id: "message-1" }] }),
}));

vi.mock("../Context/ChatAnywhereMessagesContext", () => ({
  ChatAnywhereMessagesContext: {},
}));

vi.mock("../Context/ChatAnywhereSessionsContext", () => ({
  useChatAnywhereSessionLoader: mocks.useChatAnywhereSessionLoader,
}));

vi.mock("./hooks/useChatController", () => ({
  default: () => ({
    handleSubmit: vi.fn(),
    handleCancel: vi.fn(),
  }),
}));

vi.mock("./Input", () => ({
  default: () => <div data-testid="chat-input" />,
}));

vi.mock("./MessageList", () => ({
  default: () => <div data-testid="message-list" />,
}));

vi.mock("./styles", () => ({
  default: () => null,
}));

describe("Chat content-only composition", () => {
  afterEach(() => {
    cleanup();
    mocks.useChatAnywhereSessionLoader.mockReset();
  });

  it("keeps the normal input mounted for interactive chat", () => {
    render(<Chat />);

    expect(screen.getByTestId("message-list")).toBeInTheDocument();
    expect(screen.getByTestId("chat-input")).toBeInTheDocument();
    expect(mocks.useChatAnywhereSessionLoader).toHaveBeenCalledWith({
      finishLoadingWithoutSession: false,
    });
  });

  it("does not mount the input or its paste/upload listeners in content-only mode", () => {
    render(
      <ChatContentOnlyProvider enabled>
        <Chat />
      </ChatContentOnlyProvider>,
    );

    expect(screen.getByTestId("message-list")).toBeInTheDocument();
    expect(screen.queryByTestId("chat-input")).not.toBeInTheDocument();
    expect(mocks.useChatAnywhereSessionLoader).toHaveBeenCalledWith({
      finishLoadingWithoutSession: true,
    });
  });
});
