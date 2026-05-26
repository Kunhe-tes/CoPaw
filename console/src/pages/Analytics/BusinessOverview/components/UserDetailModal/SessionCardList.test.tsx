import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { message } from "antd";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { copyToClipboard } from "../../../../../utils/clipboard";
import SessionCardList from "./SessionCardList";

vi.mock("../../../../../utils/clipboard", () => ({
  copyToClipboard: vi.fn(),
}));

const sessions = [
  {
    session_id: "session-active-001",
    session_name: "经营分析会话",
    total_traces: 8,
    total_tokens: 12800,
    total_skills: 2,
    channel: "console",
    user_id: "user-active-001",
    first_active: "2026-05-25T09:00:00Z",
    last_active: "2026-05-25T09:30:00Z",
  },
];

function renderList(onSelect = vi.fn()) {
  render(
    <SessionCardList
      sessions={sessions}
      total={1}
      page={1}
      pageSize={10}
      loading={false}
      selectedSessionId={null}
      onSelect={onSelect}
      onPageChange={vi.fn()}
    />,
  );
}

describe("SessionCardList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("copies session id without selecting the session card", async () => {
    const onSelect = vi.fn();
    const success = vi.spyOn(message, "success").mockImplementation(vi.fn());
    vi.mocked(copyToClipboard).mockResolvedValue(true);

    renderList(onSelect);
    fireEvent.click(screen.getByRole("button", { name: "复制会话 ID" }));

    await waitFor(() => {
      expect(copyToClipboard).toHaveBeenCalledWith("session-active-001");
    });
    expect(success).toHaveBeenCalledWith("会话 ID 已复制");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("shows an error when session id cannot be copied", async () => {
    const error = vi.spyOn(message, "error").mockImplementation(vi.fn());
    vi.mocked(copyToClipboard).mockResolvedValue(false);

    renderList();
    fireEvent.click(screen.getByRole("button", { name: "复制会话 ID" }));

    await waitFor(() => {
      expect(error).toHaveBeenCalledWith("会话 ID 复制失败");
    });
  });
});
