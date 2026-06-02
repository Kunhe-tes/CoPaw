import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { useRef } from "react";
import ConversationQuickNav from ".";
import { ChatAnywhereMessagesContext } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/ChatAnywhereMessagesContext";
import { ChatAnywhereSessionsContext } from "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/ChatAnywhereSessionsContext";
import type { IAgentScopeRuntimeWebUIMessage } from "@/components/agentscope-chat";

function makeUserMessage(
  id: string,
  text: string,
): IAgentScopeRuntimeWebUIMessage {
  return {
    id,
    role: "user",
    msgStatus: "finished",
    cards: [
      {
        code: "AgentScopeRuntimeRequestCard",
        data: {
          input: [
            {
              content: [{ type: "text", text }],
            },
          ],
        },
      },
    ],
  } as unknown as IAgentScopeRuntimeWebUIMessage;
}

function renderWithContexts(children: ReactNode) {
  const messages = [makeUserMessage("question-1", "原聊天页问题")];
  return render(
    <ChatAnywhereSessionsContext.Provider
      value={{
        sessions: [],
        setSessions: vi.fn(),
        getSessions: () => [],
        currentSessionId: "session-1",
        setCurrentSessionId: vi.fn(),
        getCurrentSessionId: () => "session-1",
        isSessionLoading: false,
        setSessionLoading: vi.fn(),
        isSessionsListLoading: false,
        setSessionsListLoading: vi.fn(),
      }}
    >
      <ChatAnywhereMessagesContext.Provider
        value={{
          messages,
          setMessages: vi.fn(),
          getMessages: () => messages,
        }}
      >
        {children}
      </ChatAnywhereMessagesContext.Provider>
    </ChatAnywhereSessionsContext.Provider>,
  );
}

function ScopedQuickNav() {
  const scrollRootRef = useRef<HTMLDivElement | null>(null);
  const messages = [makeUserMessage("modal-question-1", "弹窗聊天记录问题")];

  return (
    <div ref={scrollRootRef}>
      <div className="swe-bubble-list-scroll">
        <div id="modal-question-1" className="swe-bubble" />
      </div>
      <ConversationQuickNav
        messages={messages}
        scrollRootRef={scrollRootRef}
      />
    </div>
  );
}

describe("ConversationQuickNav", () => {
  beforeAll(() => {
    class ResizeObserverMock {
      observe = vi.fn();
      unobserve = vi.fn();
      disconnect = vi.fn();
    }
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);
  });

  afterEach(() => {
    cleanup();
  });

  it("keeps reading chat page context when optional props are not provided", async () => {
    renderWithContexts(
      <>
        <div className="swe-bubble-list-scroll">
          <div id="question-1" className="swe-bubble" />
        </div>
        <ConversationQuickNav />
      </>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", {
          name: /第 1 次问题: 原聊天页问题/,
        }),
      ).toBeInTheDocument();
    });
  });

  it("uses scoped messages and DOM when optional props are provided", async () => {
    renderWithContexts(
      <>
        <div className="swe-bubble-list-scroll">
          <div id="question-1" className="swe-bubble" />
        </div>
        <ScopedQuickNav />
      </>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", {
          name: /第 1 次问题: 弹窗聊天记录问题/,
        }),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", {
        name: /原聊天页问题/,
      }),
    ).not.toBeInTheDocument();
  });
});
