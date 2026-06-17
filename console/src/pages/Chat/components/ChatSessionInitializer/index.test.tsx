import React from "react";
import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChatSessionInitializer from ".";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  setCurrentSessionId: vi.fn(),
  setSelectedAgent: vi.fn(),
  sessions: [
    {
      id: "chat-2",
      name: "other chat",
      messages: [],
      meta: { agent_id: "agent-b" },
    },
  ] as Array<{
    id: string;
    realId?: string;
    name: string;
    messages: unknown[];
    meta?: Record<string, unknown>;
  }>,
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
  }),
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
    mocks.navigate.mockReset();
    mocks.setCurrentSessionId.mockReset();
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

  it("selects a URL chat id for detail loading when it is outside the loaded page", () => {
    mocks.pathname = "/chat/chat-outside-page";
    mocks.sessions = [
      {
        id: "chat-visible",
        name: "visible chat",
        messages: [],
        meta: { agent_id: "agent-a" },
      },
    ];

    render(<ChatSessionInitializer />);

    expect(mocks.setCurrentSessionId).toHaveBeenCalledWith(
      "chat-outside-page",
    );
    expect(mocks.setSelectedAgent).not.toHaveBeenCalled();
    expect(mocks.navigate).not.toHaveBeenCalled();
  });

  it("keeps the active pending session when the URL points at its resolved chat id", () => {
    mocks.pathname = "/chat/chat-real-1";
    mocks.currentSessionId = "local-123";
    mocks.sessions = [
      {
        id: "local-123",
        realId: "chat-real-1",
        name: "pending chat",
        messages: [],
        meta: { agent_id: "agent-a" },
      },
    ];

    render(<ChatSessionInitializer />);

    expect(mocks.setCurrentSessionId).not.toHaveBeenCalled();
    expect(mocks.setSelectedAgent).not.toHaveBeenCalled();
    expect(mocks.navigate).not.toHaveBeenCalled();
  });
});
