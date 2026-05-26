import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import useSuggestionsPolling from "./useSuggestionsPolling";
import type { CurrentQARef } from "./currentQARef";

const mocks = vi.hoisted(() => ({
  sessionsContext: {},
  fetchSuggestions: vi.fn(),
  getSessionList: vi.fn(),
  getRealIdForSession: vi.fn(),
  updateMessage: vi.fn(),
  iframeSource: null as string | null,
}));

vi.mock("@/api/modules/suggestions", () => ({
  fetchSuggestions: mocks.fetchSuggestions,
}));

vi.mock("use-context-selector", () => ({
  createContext: vi.fn(() => ({})),
  useContextSelector: (
    context: unknown,
    selector: (value: unknown) => unknown,
  ) => {
    if (context === mocks.sessionsContext) {
      return selector({ currentSessionId: "session-1" });
    }
    return selector({});
  },
}));

vi.mock("../../Context/ChatAnywhereSessionsContext", () => ({
  ChatAnywhereSessionsContext: mocks.sessionsContext,
}));

vi.mock("../../Context/ChatAnywhereOptionsContext", () => ({
  useChatAnywhereOptions: (selector: (value: unknown) => unknown) =>
    selector({
      session: {
        api: {
          getSessionList: mocks.getSessionList,
          getRealIdForSession: mocks.getRealIdForSession,
        },
      },
    }),
}));

vi.mock("@/stores/iframeStore", () => ({
  useIframeStore: (selector: (value: unknown) => unknown) =>
    selector({ source: mocks.iframeSource }),
}));

let hookApi: ReturnType<typeof useSuggestionsPolling>;
let root: Root | undefined;
let container: HTMLDivElement | undefined;

function createCurrentQARef(): CurrentQARef {
  return {
    current: {
      request: {
        cards: [
          {
            data: {
              input: [
                {
                  content: [{ type: "text", text: "用户问题" }],
                },
              ],
            },
          },
        ],
      },
      response: {
        id: "response-1",
        role: "assistant",
        cards: [
          {
            data: {
              id: "response-1",
              output: [
                {
                  id: "message-1",
                  role: "assistant",
                  type: "message",
                  content: [{ type: "text", text: "助手回答" }],
                },
              ],
            },
          },
        ],
      },
    },
  } as CurrentQARef;
}

function Harness(props: { currentQARef: CurrentQARef }) {
  hookApi = useSuggestionsPolling({
    currentQARef: props.currentQARef,
    updateMessage: mocks.updateMessage,
  });
  return null;
}

function renderHarness(currentQARef: CurrentQARef) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root?.render(<Harness currentQARef={currentQARef} />);
  });
}

describe("useSuggestionsPolling", () => {
  beforeEach(() => {
    mocks.fetchSuggestions.mockReset();
    mocks.getSessionList.mockReset();
    mocks.getRealIdForSession.mockReset();
    mocks.updateMessage.mockReset();
    mocks.iframeSource = null;
    mocks.getRealIdForSession.mockReturnValue("chat-1");
    mocks.getSessionList.mockResolvedValue(undefined);
  });

  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    container?.remove();
    root = undefined;
    container = undefined;
  });

  it("extracts local Q&A and updates response with frontend suggestions", async () => {
    const currentQARef = createCurrentQARef();
    mocks.fetchSuggestions.mockResolvedValue(["前端问题"]);

    renderHarness(currentQARef);

    await act(async () => {
      await hookApi.pollSuggestions();
    });

    expect(mocks.getSessionList).toHaveBeenCalled();
    expect(mocks.fetchSuggestions).toHaveBeenCalledWith({
      chatId: "chat-1",
      turnId: "response-1",
      userMessage: "用户问题",
      assistantMessage: "助手回答",
    });
    expect(currentQARef.current.response?.cards?.[0]?.data.suggestions).toEqual(
      ["前端问题"],
    );
    expect(mocks.updateMessage).toHaveBeenCalledWith(
      currentQARef.current.response,
    );
  });

  it("uses session id when real chat id is unavailable", async () => {
    const currentQARef = createCurrentQARef();
    mocks.getRealIdForSession.mockReturnValue(null);
    mocks.fetchSuggestions.mockResolvedValue(["前端问题"]);

    renderHarness(currentQARef);

    await act(async () => {
      await hookApi.pollSuggestions();
    });

    expect(mocks.fetchSuggestions).toHaveBeenCalledWith(
      expect.objectContaining({ chatId: "session-1" }),
    );
  });

  it("does not call suggestions API when request or response text is missing", async () => {
    const currentQARef = createCurrentQARef();
    currentQARef.current.request!.cards[0].data.input = [
      {
        content: [],
      },
    ];

    renderHarness(currentQARef);

    await act(async () => {
      await hookApi.pollSuggestions();
    });

    expect(mocks.fetchSuggestions).not.toHaveBeenCalled();
    expect(mocks.updateMessage).not.toHaveBeenCalled();
  });

  it("does not call suggestions API when source is ruice", async () => {
    const currentQARef = createCurrentQARef();
    mocks.iframeSource = "ruice";

    renderHarness(currentQARef);

    await act(async () => {
      await hookApi.pollSuggestions();
    });

    expect(mocks.getSessionList).not.toHaveBeenCalled();
    expect(mocks.fetchSuggestions).not.toHaveBeenCalled();
    expect(mocks.updateMessage).not.toHaveBeenCalled();
  });
});
