import { act, render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import UserDetailModal from "./index";

const sessionCardListMock = vi.hoisted(() => vi.fn());

const tracingApiMock = vi.hoisted(() => ({
  getUserStats: vi.fn(),
  getSessions: vi.fn(),
  getUserChats: vi.fn(),
  getSessionStats: vi.fn(),
}));

vi.mock("../../../../../api/modules/tracing", () => ({
  tracingApi: tracingApiMock,
}));

vi.mock("./UserStatsHeader", () => ({
  default: () => <div data-testid="user-stats-header" />,
}));

vi.mock("./SessionCardList", () => ({
  default: (props: unknown) => {
    sessionCardListMock(props);
    return <div data-testid="session-card-list" />;
  },
}));

vi.mock("./ReadOnlySessionChat", () => ({
  default: () => <div data-testid="readonly-session-chat" />,
}));

describe("UserDetailModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionCardListMock.mockClear();
    tracingApiMock.getUserStats.mockResolvedValue({});
    tracingApiMock.getSessions.mockResolvedValue({
      items: [
        {
          session_id: "session-older",
          session_name: "历史会话",
          total_traces: 1,
          total_tokens: 12,
          total_skills: 0,
          channel: "web",
          last_active: "2026-05-01T10:00:00Z",
        },
      ],
      total: 1,
    });
    tracingApiMock.getUserChats.mockResolvedValue([
      {
        id: "chat-001",
        session_id: "session-older",
        user_id: "user-001",
        channel: "web",
      },
    ]);
    tracingApiMock.getSessionStats.mockResolvedValue({});
  });

  it("loads sessions and chat mappings for the selected user", async () => {
    render(
      <UserDetailModal
        open
        userId="user-001"
        startDate="2026-05-20"
        endDate="2026-05-20"
        bbkIds="100"
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(tracingApiMock.getSessions).toHaveBeenCalled();
    });

    expect(tracingApiMock.getUserStats).toHaveBeenCalledWith(
      "user-001",
      "2026-05-20",
      "2026-05-20",
      "100",
    );
    expect(tracingApiMock.getSessions).toHaveBeenCalledWith(1, 10, {
      user_id: "user-001",
      bbk_ids: "100",
    });
    expect(tracingApiMock.getUserChats).toHaveBeenCalledWith("user-001");

    await waitFor(() => {
      expect(tracingApiMock.getSessionStats).toHaveBeenCalled();
    });

    expect(tracingApiMock.getSessionStats).toHaveBeenCalledWith(
      "session-older",
      undefined,
      undefined,
      "100",
    );
  });

  it("uses the changed page size when loading another sessions page", async () => {
    render(
      <UserDetailModal
        open
        userId="user-001"
        startDate="2026-05-20"
        endDate="2026-05-20"
        bbkIds="100"
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(sessionCardListMock).toHaveBeenCalled();
    });

    const latestProps =
      sessionCardListMock.mock.calls[
        sessionCardListMock.mock.calls.length - 1
      ][0] as {
        onPageChange: (page: number, pageSize: number) => void;
      };

    await act(async () => {
      latestProps.onPageChange(2, 20);
    });

    await waitFor(() => {
      expect(tracingApiMock.getSessions).toHaveBeenCalledWith(2, 20, {
        user_id: "user-001",
        bbk_ids: "100",
      });
    });
  });

  it("falls back to an empty chat mapping when user chats response is not an array", async () => {
    tracingApiMock.getUserChats.mockResolvedValue({});

    render(
      <UserDetailModal
        open
        userId="user-001"
        startDate="2026-05-20"
        endDate="2026-05-20"
        bbkIds="100"
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(tracingApiMock.getUserChats).toHaveBeenCalledWith("user-001");
    });

    expect(sessionCardListMock).toHaveBeenCalled();
  });
});
