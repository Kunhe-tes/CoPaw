import React from "react";
import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChatSessionInitializer from ".";

const mocks = vi.hoisted(() => ({
  isContentOnly: false,
  navigate: vi.fn(),
  setCurrentSessionId: vi.fn(),
  setSessionNotFound: vi.fn(),
  setSelectedAgent: vi.fn(),
  sessions: [
    {
      id: "chat-2",
      name: "other chat",
      messages: [],
      meta: { agent_id: "agent-b" },
    },
  ],
  currentSessionId: "chat-1",
  pathname: "/chat/chat-2",
  selectedAgent: "agent-a",
}));

vi.mock("react-router-dom", () => ({
  useLocation: () => ({ pathname: mocks.pathname }),
  useNavigate: () => mocks.navigate,
}));

vi.mock("@/components/agentscope-chat", () => ({
  useChatAnywhereSessionsState: () => ({
    sessions: mocks.sessions,
    currentSessionId: mocks.currentSessionId,
    setCurrentSessionId: mocks.setCurrentSessionId,
    setSessionNotFound: mocks.setSessionNotFound,
  }),
}));

vi.mock("@/components/agentscope-chat/ChatContentOnlyContext", () => ({
  useChatContentOnly: () => mocks.isContentOnly,
}));

vi.mock("@/stores/agentStore", () => ({
  useAgentStore: (selector?: (value: unknown) => unknown) => {
    const store = {
      selectedAgent: mocks.selectedAgent,
      setSelectedAgent: mocks.setSelectedAgent,
    };
    return selector ? selector(store) : store;
  },
}));

describe("ChatSessionInitializer", () => {
  beforeEach(() => {
    sessionStorage.clear();
    mocks.isContentOnly = false;
    mocks.navigate.mockReset();
    mocks.setCurrentSessionId.mockReset();
    mocks.setSessionNotFound.mockReset();
    mocks.setSelectedAgent.mockReset();
    mocks.sessions = [
      {
        id: "chat-2",
        name: "other chat",
        messages: [],
        meta: { agent_id: "agent-b" },
      },
    ];
    mocks.currentSessionId = "chat-1";
    mocks.pathname = "/chat/chat-2";
    mocks.selectedAgent = "agent-a";
  });

  it("aligns the selected agent before loading a session bound to another agent", () => {
    render(<ChatSessionInitializer />);

    expect(mocks.setSelectedAgent).toHaveBeenCalledWith("agent-b");
    expect(mocks.setCurrentSessionId).toHaveBeenCalledWith("chat-2");
    expect(mocks.navigate).not.toHaveBeenCalled();
  });

  it("selects a deep-linked session that is not in the current page", () => {
    mocks.pathname = "/chat/chat-101";

    render(<ChatSessionInitializer />);

    expect(mocks.setCurrentSessionId).toHaveBeenCalledWith("chat-101");
  });

  it("does not replace an active local pending session during real id resolution", () => {
    mocks.currentSessionId = "1777001065201000";
    mocks.pathname = "/chat/chat-real-1";

    render(<ChatSessionInitializer />);

    expect(mocks.setCurrentSessionId).not.toHaveBeenCalled();
  });

  it("marks an unmapped temporary deep link as unavailable in content-only mode", () => {
    mocks.isContentOnly = true;
    mocks.pathname = "/chat/1777001065201000";
    mocks.sessions = [];

    render(<ChatSessionInitializer />);

    expect(mocks.setCurrentSessionId).toHaveBeenCalledWith(undefined);
    expect(mocks.setSessionNotFound).toHaveBeenCalledWith(true);
    expect(mocks.navigate).not.toHaveBeenCalled();
  });

  it("preserves normal temporary-session selection outside content-only mode", () => {
    mocks.pathname = "/chat/1777001065201000";

    render(<ChatSessionInitializer />);

    expect(mocks.setCurrentSessionId).toHaveBeenCalledWith("1777001065201000");
    expect(mocks.setSessionNotFound).not.toHaveBeenCalled();
  });

  it("resolves a mapped temporary deep link in content-only mode", () => {
    mocks.isContentOnly = true;
    mocks.pathname = "/chat/1777001065201000";
    sessionStorage.setItem(
      "copaw_resolved_chat_ids",
      JSON.stringify({
        "1777001065201000": "chat-2",
      }),
    );

    render(<ChatSessionInitializer />);

    expect(mocks.setSessionNotFound).not.toHaveBeenCalled();
    expect(mocks.setCurrentSessionId).toHaveBeenCalledWith("chat-2");
    expect(mocks.navigate).toHaveBeenCalledWith("/chat/chat-2", {
      replace: true,
    });
  });
});
