import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { WPlusSopEntryProposal } from "@/api/types/wplusSop";
import { WPLUS_SOP_REPLAY_EVENT } from "../../wplusSopEntryEvents";
import WPlusSopEntryCard from "./index";

const apiMock = vi.hoisted(() => ({
  confirmEntry: vi.fn(),
  rejectEntry: vi.fn(),
}));
const createRequestIdMock = vi.hoisted(() => vi.fn());

vi.mock("@/api/modules/wplusSop", () => ({
  wplusSopApi: apiMock,
}));

vi.mock("@/pages/WPlusSopWorkspace/sessionView", () => ({
  createCommandRequestId: createRequestIdMock,
}));

const proposal: WPlusSopEntryProposal = {
  object: "wplus_sop_entry_proposal",
  status: "completed",
  proposal_id: "proposal-1",
  mode: "implicit",
  chat_id: "chat-1",
  session_id: "logical-1",
  title: "进入 W+ SOP 工作台",
  message: "CoPaw 将替你完成预跑。",
};

function renderCard() {
  return render(
    <MemoryRouter initialEntries={["/chat/chat-1"]}>
      <Routes>
        <Route
          path="/chat/:chatId"
          element={<WPlusSopEntryCard data={proposal} />}
        />
        <Route
          path="/wplus-sop/:sessionId"
          element={<h1>W+ 工作台已打开</h1>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("WPlusSopEntryCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createRequestIdMock.mockReset();
    createRequestIdMock
      .mockReturnValueOnce("cmd-confirm")
      .mockReturnValueOnce("cmd-reject");
  });

  afterEach(() => {
    cleanup();
  });

  it("confirms the proposal and navigates to its persisted session", async () => {
    apiMock.confirmEntry.mockResolvedValue({
      accepted: true,
      session: { session_id: "sop-1" },
    });
    renderCard();

    fireEvent.click(screen.getByRole("button", { name: "进入工作台" }));

    expect(
      await screen.findByRole("heading", { name: "W+ 工作台已打开" }),
    ).toBeInTheDocument();
    expect(apiMock.confirmEntry).toHaveBeenCalledWith(
      "proposal-1",
      "cmd-confirm",
    );
  });

  it("reuses the confirm request id after an uncertain failure", async () => {
    apiMock.confirmEntry
      .mockRejectedValueOnce(new TypeError("network interrupted"))
      .mockResolvedValueOnce({
        accepted: true,
        session: { session_id: "sop-1" },
      });
    renderCard();

    fireEvent.click(screen.getByRole("button", { name: "进入工作台" }));
    expect(await screen.findByText(/工作台没有成功创建/)).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /进入工作台/ }),
      ).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: /进入工作台/ }));

    expect(
      await screen.findByRole("heading", { name: "W+ 工作台已打开" }),
    ).toBeInTheDocument();
    expect(apiMock.confirmEntry).toHaveBeenNthCalledWith(
      1,
      "proposal-1",
      "cmd-confirm",
    );
    expect(apiMock.confirmEntry).toHaveBeenNthCalledWith(
      2,
      "proposal-1",
      "cmd-confirm",
    );
    expect(createRequestIdMock).toHaveBeenCalledTimes(1);
  });

  it("rejects and emits a one-time suppressed replay request", async () => {
    apiMock.rejectEntry.mockResolvedValue({
      proposal_id: "proposal-1",
      status: "rejected",
      suppression_token: "suppress-once",
      original_request: { text: "继续原请求" },
    });
    const listener = vi.fn();
    document.addEventListener(WPLUS_SOP_REPLAY_EVENT, listener);
    renderCard();

    fireEvent.click(screen.getByRole("button", { name: "留在 Chat" }));

    await waitFor(() => expect(listener).toHaveBeenCalledTimes(1));
    const event = listener.mock.calls[0][0] as CustomEvent;
    expect(event.detail).toEqual({
      query: "继续原请求",
      proposal_id: "proposal-1",
      suppression_token: "suppress-once",
    });
    expect(screen.getByText("已留在当前 Chat")).toBeInTheDocument();
    document.removeEventListener(WPLUS_SOP_REPLAY_EVENT, listener);
  });

  it("reuses the reject request id after an uncertain failure", async () => {
    createRequestIdMock.mockReset().mockReturnValue("cmd-reject");
    apiMock.rejectEntry
      .mockRejectedValueOnce(new TypeError("network interrupted"))
      .mockResolvedValueOnce({
        proposal_id: "proposal-1",
        status: "rejected",
        suppression_token: "suppress-once",
        original_request: { text: "继续原请求" },
      });
    renderCard();

    fireEvent.click(screen.getByRole("button", { name: "留在 Chat" }));
    expect(await screen.findByText(/无法继续原 Chat 请求/)).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /留在 Chat/ }),
      ).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: /留在 Chat/ }));

    expect(await screen.findByText("已留在当前 Chat")).toBeInTheDocument();
    expect(apiMock.rejectEntry).toHaveBeenNthCalledWith(
      1,
      "proposal-1",
      "cmd-reject",
    );
    expect(apiMock.rejectEntry).toHaveBeenNthCalledWith(
      2,
      "proposal-1",
      "cmd-reject",
    );
    expect(createRequestIdMock).toHaveBeenCalledTimes(1);
  });
});
