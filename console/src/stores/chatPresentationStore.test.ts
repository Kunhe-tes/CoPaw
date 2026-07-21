import { beforeEach, describe, expect, it } from "vitest";
import {
  initializeChatPresentationFromUrl,
  isChatContentOnlyRequested,
  useChatPresentationStore,
} from "./chatPresentationStore";

describe("chatPresentationStore", () => {
  beforeEach(() => {
    initializeChatPresentationFromUrl("/chat/chat-1", "");
  });

  it("accepts only the exact lower-case true query value", () => {
    expect(
      isChatContentOnlyRequested(
        "/chat/chat-1",
        "?source=ruice&showContentOnly=true",
      ),
    ).toBe(true);

    for (const search of [
      "",
      "?showContentOnly=",
      "?showContentOnly=false",
      "?showContentOnly=1",
      "?showContentOnly=TRUE",
    ]) {
      expect(isChatContentOnlyRequested("/chat/chat-1", search)).toBe(false);
    }
  });

  it("requires a concrete chat route and supports the Console basename", () => {
    expect(
      isChatContentOnlyRequested(
        "/console/chat/chat-1",
        "?showContentOnly=true",
      ),
    ).toBe(true);
    expect(isChatContentOnlyRequested("/chat", "?showContentOnly=true")).toBe(
      false,
    );
    expect(isChatContentOnlyRequested("/models", "?showContentOnly=true")).toBe(
      false,
    );
  });

  it("keeps the startup preference after the URL query is no longer present", () => {
    initializeChatPresentationFromUrl("/chat/chat-1", "?showContentOnly=true");

    expect(useChatPresentationStore.getState().showContentOnly).toBe(true);
    expect(isChatContentOnlyRequested("/chat/chat-1", "")).toBe(false);
    expect(useChatPresentationStore.getState().showContentOnly).toBe(true);
  });

  it("resets to normal mode on a new startup without the opt-in parameter", () => {
    initializeChatPresentationFromUrl("/chat/chat-1", "?showContentOnly=true");
    initializeChatPresentationFromUrl("/chat/chat-1", "");

    expect(useChatPresentationStore.getState().showContentOnly).toBe(false);
  });
});
