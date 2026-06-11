import React from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ExpandablePanel from ".";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  setSessionLoading: vi.fn(),
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => mocks.navigate,
}));

vi.mock("@/components/agentscope-chat", () => ({
  useChatAnywhereSessionsState: () => ({
    currentSessionId: "chat-1",
    setSessionLoading: mocks.setSessionLoading,
  }),
}));

describe("ExpandablePanel history", () => {
  it("loads another page when the first page does not fill the panel", async () => {
    const clientHeight = vi
      .spyOn(HTMLElement.prototype, "clientHeight", "get")
      .mockReturnValue(500);
    const scrollHeight = vi
      .spyOn(HTMLElement.prototype, "scrollHeight", "get")
      .mockReturnValue(240);
    const onLoadMoreSessions = vi.fn();

    render(
      <ExpandablePanel
        visible
        type="history"
        onClose={vi.fn()}
        tasks={[]}
        sessions={[{ id: "chat-2", name: "chat two", messages: [] }]}
        hasMoreSessions
        onLoadMoreSessions={onLoadMoreSessions}
        onTaskClick={vi.fn()}
        toolbarRef={{ current: document.createElement("div") }}
      />,
    );

    await waitFor(() => {
      expect(onLoadMoreSessions).toHaveBeenCalledTimes(1);
    });
    clientHeight.mockRestore();
    scrollHeight.mockRestore();
  });

  beforeEach(() => {
    mocks.navigate.mockReset();
    mocks.setSessionLoading.mockReset();
  });

  it("ignores clicks on the already active session", () => {
    const onClose = vi.fn();

    render(
      <ExpandablePanel
        visible
        type="history"
        onClose={onClose}
        tasks={[]}
        sessions={[
          {
            id: "chat-1",
            name: "current chat",
            messages: [],
          },
        ]}
        onTaskClick={vi.fn()}
        toolbarRef={{ current: document.createElement("div") }}
      />,
    );

    fireEvent.click(screen.getByText("current chat"));

    expect(mocks.setSessionLoading).not.toHaveBeenCalled();
    expect(mocks.navigate).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("ignores clicks when the active session is addressed by realId", () => {
    const onClose = vi.fn();

    render(
      <ExpandablePanel
        visible
        type="history"
        onClose={onClose}
        tasks={[]}
        sessions={[
          {
            id: "temp-1",
            realId: "chat-1",
            name: "current chat by real id",
            messages: [],
          } as any,
        ]}
        onTaskClick={vi.fn()}
        toolbarRef={{ current: document.createElement("div") }}
      />,
    );

    fireEvent.click(screen.getByText("current chat by real id"));

    expect(mocks.setSessionLoading).not.toHaveBeenCalled();
    expect(mocks.navigate).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("loads and navigates when clicking a different session", () => {
    const onClose = vi.fn();

    render(
      <ExpandablePanel
        visible
        type="history"
        onClose={onClose}
        tasks={[]}
        sessions={[
          {
            id: "chat-2",
            name: "other chat",
            messages: [],
          },
        ]}
        onTaskClick={vi.fn()}
        toolbarRef={{ current: document.createElement("div") }}
      />,
    );

    fireEvent.click(screen.getByText("other chat"));

    expect(mocks.setSessionLoading).toHaveBeenCalledWith(true);
    expect(mocks.navigate).toHaveBeenCalledWith("/chat/chat-2", {
      replace: true,
    });
    expect(onClose).toHaveBeenCalled();
  });

  it("renders history sessions in the provided page order", () => {
    const { container } = render(
      <ExpandablePanel
        visible
        type="history"
        onClose={vi.fn()}
        tasks={[]}
        sessions={[
          { id: "chat-3", name: "newest chat", messages: [] },
          { id: "chat-2", name: "older chat", messages: [] },
        ]}
        onTaskClick={vi.fn()}
        toolbarRef={{ current: document.createElement("div") }}
      />,
    );

    const rows = within(container).getAllByRole("button");
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining("newest chat"),
      expect.stringContaining("older chat"),
    ]);
  });

  it("renders only the loaded page for a large history result", () => {
    const sessions = Array.from({ length: 50 }, (_, index) => ({
      id: `chat-${index}`,
      name: `chat ${index}`,
      messages: [],
    }));
    const { container } = render(
      <ExpandablePanel
        visible
        type="history"
        onClose={vi.fn()}
        tasks={[]}
        sessions={sessions}
        hasMoreSessions
        onLoadMoreSessions={vi.fn()}
        onTaskClick={vi.fn()}
        toolbarRef={{ current: document.createElement("div") }}
      />,
    );

    expect(
      container.querySelectorAll(".expandable-panel-history-item"),
    ).toHaveLength(50);
    expect(
      within(container).queryByRole("button", { name: "加载更多历史记录" }),
    ).not.toBeInTheDocument();
  });

  it("loads another history page when the collapsed panel scrolls near the bottom", () => {
    const onLoadMoreSessions = vi.fn();
    const { container } = render(
      <ExpandablePanel
        visible
        type="history"
        onClose={vi.fn()}
        tasks={[]}
        sessions={[{ id: "chat-2", name: "chat two", messages: [] }]}
        hasMoreSessions
        onLoadMoreSessions={onLoadMoreSessions}
        onTaskClick={vi.fn()}
        toolbarRef={{ current: document.createElement("div") }}
      />,
    );

    const scrollContainer = container.querySelector(
      ".expandable-panel-content",
    ) as HTMLDivElement;
    Object.defineProperties(scrollContainer, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 500 },
      scrollTop: { configurable: true, value: 230, writable: true },
    });
    fireEvent.scroll(scrollContainer);

    expect(onLoadMoreSessions).toHaveBeenCalledTimes(1);
  });

  it("does not load another page before the collapsed panel nears the bottom", () => {
    const onLoadMoreSessions = vi.fn();
    const { container } = render(
      <ExpandablePanel
        visible
        type="history"
        onClose={vi.fn()}
        tasks={[]}
        sessions={[{ id: "chat-2", name: "chat two", messages: [] }]}
        hasMoreSessions
        onLoadMoreSessions={onLoadMoreSessions}
        onTaskClick={vi.fn()}
        toolbarRef={{ current: document.createElement("div") }}
      />,
    );

    const scrollContainer = container.querySelector(
      ".expandable-panel-content",
    ) as HTMLDivElement;
    Object.defineProperties(scrollContainer, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 500 },
      scrollTop: { configurable: true, value: 100, writable: true },
    });
    fireEvent.scroll(scrollContainer);

    expect(onLoadMoreSessions).not.toHaveBeenCalled();
  });

  it("locks repeated bottom scroll events until loading state changes", () => {
    const onLoadMoreSessions = vi.fn();
    const { container } = render(
      <ExpandablePanel
        visible
        type="history"
        onClose={vi.fn()}
        tasks={[]}
        sessions={[{ id: "chat-2", name: "chat two", messages: [] }]}
        hasMoreSessions
        onLoadMoreSessions={onLoadMoreSessions}
        onTaskClick={vi.fn()}
        toolbarRef={{ current: document.createElement("div") }}
      />,
    );

    const scrollContainer = container.querySelector(
      ".expandable-panel-content",
    ) as HTMLDivElement;
    Object.defineProperties(scrollContainer, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 500 },
      scrollTop: { configurable: true, value: 300, writable: true },
    });
    fireEvent.scroll(scrollContainer);
    fireEvent.scroll(scrollContainer);

    expect(onLoadMoreSessions).toHaveBeenCalledTimes(1);
  });

  it("unlocks bottom loading after the previous page completes", () => {
    const onLoadMoreSessions = vi.fn();
    const props = {
      visible: true,
      type: "history" as const,
      onClose: vi.fn(),
      tasks: [],
      sessions: [{ id: "chat-2", name: "chat two", messages: [] }],
      hasMoreSessions: true,
      onLoadMoreSessions,
      onTaskClick: vi.fn(),
      toolbarRef: { current: document.createElement("div") },
    };
    const { container, rerender } = render(<ExpandablePanel {...props} />);
    const scrollContainer = container.querySelector(
      ".expandable-panel-content",
    ) as HTMLDivElement;
    Object.defineProperties(scrollContainer, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 500 },
      scrollTop: { configurable: true, value: 300, writable: true },
    });

    fireEvent.scroll(scrollContainer);
    rerender(<ExpandablePanel {...props} isLoadingMoreSessions />);
    rerender(<ExpandablePanel {...props} isLoadingMoreSessions={false} />);
    fireEvent.scroll(scrollContainer);

    expect(onLoadMoreSessions).toHaveBeenCalledTimes(2);
  });

  it("disables repeated history loading while a page is in flight", () => {
    const onLoadMoreSessions = vi.fn();
    const { container } = render(
      <ExpandablePanel
        visible
        type="history"
        onClose={vi.fn()}
        tasks={[]}
        sessions={[{ id: "chat-2", name: "chat two", messages: [] }]}
        hasMoreSessions
        isLoadingMoreSessions
        onLoadMoreSessions={onLoadMoreSessions}
        onTaskClick={vi.fn()}
        toolbarRef={{ current: document.createElement("div") }}
      />,
    );

    const scrollContainer = container.querySelector(
      ".expandable-panel-content",
    ) as HTMLDivElement;
    Object.defineProperties(scrollContainer, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 500 },
      scrollTop: { configurable: true, value: 300, writable: true },
    });
    expect(
      within(container).getByRole("status", {
        name: "正在加载历史记录",
      }),
    ).toBeInTheDocument();
    fireEvent.scroll(scrollContainer);
    expect(onLoadMoreSessions).not.toHaveBeenCalled();
  });

  it("offers retry without hiding loaded history after a page failure", () => {
    const onLoadMoreSessions = vi.fn();
    const { container } = render(
      <ExpandablePanel
        visible
        type="history"
        onClose={vi.fn()}
        tasks={[]}
        sessions={[{ id: "chat-2", name: "chat two", messages: [] }]}
        hasMoreSessions
        loadMoreSessionsFailed
        onLoadMoreSessions={onLoadMoreSessions}
        onTaskClick={vi.fn()}
        toolbarRef={{ current: document.createElement("div") }}
      />,
    );

    expect(within(container).getByText("chat two")).toBeInTheDocument();
    const scrollContainer = container.querySelector(
      ".expandable-panel-content",
    ) as HTMLDivElement;
    Object.defineProperties(scrollContainer, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 500 },
      scrollTop: { configurable: true, value: 300, writable: true },
    });
    fireEvent.scroll(scrollContainer);
    expect(onLoadMoreSessions).not.toHaveBeenCalled();
    fireEvent.click(
      within(container).getByRole("button", { name: "重试加载历史记录" }),
    );
    expect(onLoadMoreSessions).toHaveBeenCalledTimes(1);
  });

  it("does not load after the final history page", () => {
    const onLoadMoreSessions = vi.fn();
    const { container } = render(
      <ExpandablePanel
        visible
        type="history"
        onClose={vi.fn()}
        tasks={[]}
        sessions={[{ id: "chat-2", name: "chat two", messages: [] }]}
        onLoadMoreSessions={onLoadMoreSessions}
        onTaskClick={vi.fn()}
        toolbarRef={{ current: document.createElement("div") }}
      />,
    );

    const scrollContainer = container.querySelector(
      ".expandable-panel-content",
    ) as HTMLDivElement;
    Object.defineProperties(scrollContainer, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 500 },
      scrollTop: { configurable: true, value: 300, writable: true },
    });
    fireEvent.scroll(scrollContainer);

    expect(onLoadMoreSessions).not.toHaveBeenCalled();
  });
});

describe("ExpandablePanel tasks", () => {
  beforeEach(() => {
    mocks.navigate.mockReset();
    mocks.setSessionLoading.mockReset();
  });

  it("shows completed status instead of scheduled result preview", () => {
    render(
      <ExpandablePanel
        visible
        type="tasks"
        onClose={vi.fn()}
        tasks={[
          {
            id: "job-1",
            name: "daily task",
            enabled: true,
            schedule: {
              type: "cron",
              cron: "0 9 * * *",
              timezone: "Asia/Shanghai",
            },
            task_type: "agent",
            request: {
              input: [{ role: "user", content: "ping" }],
            },
            dispatch: {
              type: "channel",
              channel: "console",
              target: {
                user_id: "user-1",
                session_id: "session-1",
              },
            },
            task: {
              visible_in_my_tasks: true,
              has_scheduled_result: true,
              latest_scheduled_preview: "scheduled result preview",
              unread_execution_count: 0,
              is_running: false,
              is_paused: false,
              pause_reason: null,
              last_scheduled_run_at: "2026-05-21T08:00:00Z" as any,
            },
          } as any,
        ]}
        sessions={[]}
        onTaskClick={vi.fn()}
        toolbarRef={{ current: document.createElement("div") }}
      />,
    );

    expect(screen.getByText("已完成")).toBeInTheDocument();
    expect(screen.queryByText("scheduled result preview")).toBeNull();
  });

  it("shows unread badge without hiding task actions", () => {
    const { container } = render(
      <ExpandablePanel
        visible
        type="tasks"
        onClose={vi.fn()}
        tasks={[
          {
            id: "job-1",
            name: "daily task",
            enabled: true,
            schedule: {
              type: "cron",
              cron: "0 9 * * *",
              timezone: "Asia/Shanghai",
            },
            task_type: "agent",
            request: {
              input: [{ role: "user", content: "ping" }],
            },
            dispatch: {
              type: "channel",
              channel: "console",
              target: {
                user_id: "user-1",
                session_id: "session-1",
              },
            },
            task: {
              visible_in_my_tasks: true,
              has_scheduled_result: true,
              latest_scheduled_preview: "",
              unread_execution_count: 3,
              is_running: false,
              is_paused: false,
              pause_reason: null,
            },
          } as any,
        ]}
        sessions={[]}
        onTaskClick={vi.fn()}
        toolbarRef={{ current: document.createElement("div") }}
      />,
    );

    expect(screen.getByText("3")).toBeInTheDocument();
    expect(
      container.querySelector(".expandable-panel-task-action-trigger"),
    ).toBeInTheDocument();
  });
});
