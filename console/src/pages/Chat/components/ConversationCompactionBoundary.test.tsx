import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Cards from "@/components/agentscope-chat/Bubble/Cards";
import type { ChatCompactionBoundary } from "@/api/types/chat";
import ConversationCompactionBoundary from "./ConversationCompactionBoundary";

const cardConfigState = vi.hoisted(() => ({
  current: {} as Record<
    string,
    (props: { data: ChatCompactionBoundary }) => JSX.Element
  >,
}));

vi.mock("@/components/agentscope-chat", () => ({
  useChatAnywhere: () => ({}),
  useCustomCardsContext: () => cardConfigState.current,
}));

describe("ConversationCompactionBoundary", () => {
  it("directs users to scroll upward for archived history", () => {
    cardConfigState.current = {
      ConversationCompactionBoundary,
    };

    render(
      <Cards
        cards={[
          {
            code: "ConversationCompactionBoundary",
            data: {
              id: "boundary-1",
              archived_message_count: 3,
              first_message_id: "message-1",
              last_message_id: "message-3",
              created_at: "2026-08-03T00:00:00Z",
            },
          },
        ]}
        id="boundary-card"
      />,
    );

    const separator = screen.getByRole("separator");
    expect(separator).toHaveTextContent("会话已压缩 · 上滚查看历史内容");
    expect(separator).not.toHaveTextContent("条消息已归档");
    expect(separator).toHaveAttribute(
      "aria-label",
      "会话已压缩 · 上滚查看历史内容",
    );
    expect(separator.firstElementChild).toHaveStyle({ flex: "1 1 0%" });
    expect(separator.lastElementChild).toHaveStyle({ flex: "1 1 0%" });
  });
});
