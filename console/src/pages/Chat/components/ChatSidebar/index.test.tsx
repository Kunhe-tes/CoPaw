import React from "react";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { Modal } from "antd";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChatSidebar from ".";
import sessionApi from "../../sessionApi";

interface TestSession {
  id: string;
  name: string;
  messages: unknown[];
  createdAt?: string;
  generating?: boolean;
}

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  setSessions: vi.fn(),
  setSessionLoading: vi.fn(),
  setSelectedAgent: vi.fn(),
  loadMoreSessions: vi.fn(),
  hasMoreSessions: vi.fn(),
  getSessionTotal: vi.fn(),
  getSessions: vi.fn(),
  context: {
    sessions: [
      {
        id: "chat-1",
        name: "first chat",
        messages: [],
        createdAt: "2026-06-10T00:00:00Z",
      },
    ] as TestSession[],
    setSessions: vi.fn(),
    setSessionLoading: vi.fn(),
    getSessions: vi.fn(),
    isSessionsListLoading: false,
  },
  iframeState: {
    bbk: null as string | null,
    source: null as string | null,
  },
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => mocks.navigate,
  useLocation: () => ({ pathname: "/chat" }),
}));

vi.mock("antd", () => ({
  Image: Object.assign(
    ({ src }: { src?: string }) =>
      src ? (
        <img alt="guide-preview" data-testid="guide-image" src={src} />
      ) : null,
    {
      PreviewGroup: ({ children }: { children: React.ReactNode }) => children,
    },
  ),
  Modal: { confirm: vi.fn() },
}));

vi.mock("../ChatTaskList", () => ({ default: () => null }));
vi.mock("./CollapsedToolbar", () => ({ default: () => null }));
vi.mock("./ExpandablePanel", () => ({ default: () => null }));
vi.mock("./HistorySkeleton", () => ({ HistorySkeleton: () => null }));
vi.mock("./HistorySessionRow", () => ({
  HistorySessionRow: ({
    name,
    session,
    onSessionDelete,
  }: {
    name: string;
    session: { id: string; realId?: string };
    onSessionDelete: (
      sessionId: string,
      backendId: string | null,
      sessionName: string,
    ) => void;
  }) => (
    <button
      type="button"
      onClick={() => onSessionDelete(session.id, session.realId || null, name)}
    >
      {name}
    </button>
  ),
}));

vi.mock("use-context-selector", () => ({
  useContextSelector: (
    _context: unknown,
    selector: (value: never) => unknown,
  ) => selector(mocks.context as never),
}));

vi.mock("@/components/agentscope-chat", () => ({
  ChatAnywhereSessionsContext: {},
  useChatAnywhereSessionsState: () => ({
    currentSessionId: null,
    setSessionLoading: mocks.setSessionLoading,
  }),
}));

vi.mock(
  "@/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Context/useChatAnywhereEventEmitter",
  () => ({ default: vi.fn() }),
);

vi.mock("@/stores/agentStore", () => ({
  useAgentStore: () => ({
    selectedAgent: "default",
    setSelectedAgent: mocks.setSelectedAgent,
  }),
}));

vi.mock("@/stores/iframeStore", () => ({
  useIframeStore: (
    selector: (state: { bbk: string | null; source: string | null }) => unknown,
  ) => selector(mocks.iframeState),
}));

vi.mock("@/assets/others/note.png", () => ({ default: "guide-image.png" }));
vi.mock("@/assets/others/sh_note.png", () => ({
  default: "sh-guide-image.png",
}));

vi.mock("../../sessionApi", () => ({
  default: {
    getSessionList: vi.fn(),
    loadMoreSessions: mocks.loadMoreSessions,
    hasMoreSessions: mocks.hasMoreSessions,
    getSessionTotal: mocks.getSessionTotal,
    removeSession: vi.fn(),
  },
}));

describe("ChatSidebar infinite history scrolling", () => {
  beforeEach(() => {
    mocks.navigate.mockReset();
    mocks.setSessions.mockReset();
    mocks.setSessionLoading.mockReset();
    mocks.setSelectedAgent.mockReset();
    mocks.loadMoreSessions.mockReset();
    mocks.hasMoreSessions.mockReset();
    mocks.getSessionTotal.mockReset();
    mocks.getSessions.mockReset();
    vi.mocked(Modal.confirm).mockReset();
    vi.mocked(sessionApi.getSessionList).mockReset();
    vi.mocked(sessionApi.removeSession).mockReset();
    mocks.context.setSessions = mocks.setSessions;
    mocks.context.setSessionLoading = mocks.setSessionLoading;
    mocks.context.getSessions = mocks.getSessions;
    mocks.iframeState.bbk = null;
    mocks.iframeState.source = null;
    mocks.hasMoreSessions.mockReturnValue(true);
    mocks.getSessionTotal.mockReturnValue(120);
    mocks.getSessions.mockImplementation(() => mocks.context.sessions);
    mocks.loadMoreSessions.mockResolvedValue([
      ...mocks.context.sessions,
      {
        id: "chat-2",
        name: "second chat",
        messages: [],
        createdAt: "2026-06-09T00:00:00Z",
      },
    ]);
  });

  it("loads the next page when the expanded sidebar reaches the bottom", async () => {
    const { container } = render(<ChatSidebar tasks={[]} />);
    const scrollContainer = container.querySelector(
      ".chat-sidebar-content-record-list",
    ) as HTMLDivElement;
    Object.defineProperties(scrollContainer, {
      clientHeight: { configurable: true, value: 300 },
      scrollHeight: { configurable: true, value: 800 },
      scrollTop: { configurable: true, value: 440, writable: true },
    });

    fireEvent.scroll(scrollContainer);

    await waitFor(() => {
      expect(mocks.loadMoreSessions).toHaveBeenCalledTimes(1);
    });
    expect(mocks.setSessions).toHaveBeenCalledWith(
      expect.arrayContaining([expect.objectContaining({ id: "chat-2" })]),
    );
  });

  it("shows the backend history total instead of only the loaded row count", () => {
    const { getAllByText } = render(<ChatSidebar tasks={[]} />);

    expect(getAllByText("历史记录(120)").length).toBeGreaterThan(0);
  });

  it("subtracts visible task count from the history total", () => {
    const tasks = [
      { id: "task-1", task: { unread_execution_count: 0 } },
      { id: "task-2", task: { unread_execution_count: 0 } },
    ];

    const { getAllByText } = render(<ChatSidebar tasks={tasks as never} />);

    expect(getAllByText("历史记录(118)").length).toBeGreaterThan(0);
  });

  it("excludes the deleted session when refreshing after delete", async () => {
    const nextSessions = [
      {
        id: "chat-2",
        name: "second chat",
        messages: [],
        createdAt: "2026-06-09T00:00:00Z",
      },
    ];
    vi.mocked(sessionApi.removeSession).mockResolvedValue(nextSessions);
    vi.mocked(sessionApi.getSessionList).mockResolvedValue(nextSessions);
    mocks.getSessions.mockReturnValue([
      ...mocks.context.sessions,
      ...nextSessions,
    ]);
    mocks.hasMoreSessions.mockReturnValue(false);

    const { getAllByText } = render(<ChatSidebar tasks={[]} />);
    mocks.setSessions.mockClear();

    fireEvent.click(getAllByText("first chat")[0]);
    await vi.mocked(Modal.confirm).mock.calls[0]?.[0]?.onOk?.();

    await waitFor(() => {
      expect(mocks.setSessions).toHaveBeenCalledWith([
        expect.objectContaining({ id: "chat-2" }),
      ]);
    });
    expect(mocks.setSessions).not.toHaveBeenCalledWith(
      expect.arrayContaining([expect.objectContaining({ id: "chat-1" })]),
    );
  });

  it("preserves a concurrently created session and generating state when a page resolves", async () => {
    let resolvePage: (sessions: TestSession[]) => void = () => undefined;
    mocks.loadMoreSessions.mockReturnValueOnce(
      new Promise((resolve) => {
        resolvePage = resolve;
      }),
    );
    const { container } = render(<ChatSidebar tasks={[]} />);
    const scrollContainer = container.querySelector(
      ".chat-sidebar-content-record-list",
    ) as HTMLDivElement;
    Object.defineProperties(scrollContainer, {
      clientHeight: { configurable: true, value: 300 },
      scrollHeight: { configurable: true, value: 800 },
      scrollTop: { configurable: true, value: 440, writable: true },
    });

    fireEvent.scroll(scrollContainer);
    mocks.getSessions.mockReturnValue([
      {
        id: "local-new",
        name: "new chat",
        messages: [],
        generating: true,
        createdAt: "2026-06-11T00:00:00Z",
      },
      {
        ...mocks.context.sessions[0],
        generating: true,
      },
    ]);
    resolvePage([
      { ...mocks.context.sessions[0], generating: false },
      {
        id: "chat-2",
        name: "second chat",
        messages: [],
        createdAt: "2026-06-09T00:00:00Z",
      },
    ]);

    await waitFor(() => {
      expect(mocks.setSessions).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({ id: "local-new", generating: true }),
          expect.objectContaining({ id: "chat-1", generating: true }),
          expect.objectContaining({ id: "chat-2" }),
        ]),
      );
    });
  });

  it("uses the Shanghai guide image when bbk is 121 and source is RMASSIST", () => {
    mocks.iframeState.bbk = "121";
    mocks.iframeState.source = "RMASSIST";

    const { container } = render(<ChatSidebar tasks={[]} showGuide />);
    const guide = container.querySelector(
      '[data-testid="guide-image"]',
    ) as HTMLImageElement;

    expect(guide).toHaveAttribute("src", "sh-guide-image.png");
  });

  it("hides the operation guide when source is not RMASSIST", () => {
    mocks.iframeState.bbk = "121";
    mocks.iframeState.source = "OTHER";

    const { container } = render(<ChatSidebar tasks={[]} showGuide />);

    expect(container.querySelector(".chat-sidebar-footer")).toBeNull();
    expect(container.querySelector('[data-testid="guide-image"]')).toBeNull();
    expect(
      container.querySelector(".chat-sidebar-content-record-list"),
    ).toHaveClass("chat-sidebar-content-record-list--without-guide");
  });

  it("hides the operation guide when bbk is not 121", () => {
    mocks.iframeState.bbk = "100";
    mocks.iframeState.source = "RMASSIST";

    const { container } = render(<ChatSidebar tasks={[]} showGuide />);

    expect(container.querySelector(".chat-sidebar-footer")).toBeNull();
    expect(container.querySelector('[data-testid="guide-image"]')).toBeNull();
  });

  it("hides the operation guide unless it is enabled", () => {
    mocks.iframeState.bbk = "121";
    mocks.iframeState.source = "RMASSIST";

    const { container } = render(<ChatSidebar tasks={[]} />);

    expect(container.querySelector(".chat-sidebar-footer")).toBeNull();
    expect(container.querySelector('[data-testid="guide-image"]')).toBeNull();
  });

  it("shows the operation guide when it is enabled", () => {
    mocks.iframeState.bbk = "121";
    mocks.iframeState.source = "RMASSIST";

    const { container } = render(<ChatSidebar tasks={[]} showGuide />);

    expect(container.querySelector(".chat-sidebar-footer")).toHaveTextContent(
      "操作指南",
    );
    expect(
      container.querySelector('[data-testid="guide-image"]'),
    ).toBeInTheDocument();
    expect(
      container.querySelector(".chat-sidebar-content-record-list"),
    ).not.toHaveClass("chat-sidebar-content-record-list--without-guide");
  });
});
