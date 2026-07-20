import { describe, expect, it } from "vitest";
import { resolveChatContentOnlyRoute } from "./contentOnlyMode";

describe("resolveChatContentOnlyRoute", () => {
  it("activates only for an exact lower-case true value on a chat route", () => {
    expect(
      resolveChatContentOnlyRoute("/chat/chat-123", "?showContentOnly=true"),
    ).toEqual({
      chatId: "chat-123",
      enabled: true,
      isChatRoute: true,
    });

    for (const search of [
      "",
      "?showContentOnly=",
      "?showContentOnly=false",
      "?showContentOnly=1",
      "?showContentOnly=TRUE",
    ]) {
      expect(
        resolveChatContentOnlyRoute("/chat/chat-123", search).enabled,
      ).toBe(false);
    }
  });

  it("does not activate without a concrete chat target", () => {
    expect(
      resolveChatContentOnlyRoute("/chat", "?showContentOnly=true"),
    ).toEqual({
      enabled: false,
      isChatRoute: true,
    });
  });

  it("ignores the parameter on non-chat routes", () => {
    expect(
      resolveChatContentOnlyRoute("/models", "?showContentOnly=true"),
    ).toEqual({
      enabled: false,
      isChatRoute: false,
    });
  });

  it("does not depend on iframe or source state", () => {
    const direct = resolveChatContentOnlyRoute(
      "/chat/chat-123",
      "?source=ruice&showContentOnly=true",
    );
    const anotherSource = resolveChatContentOnlyRoute(
      "/chat/chat-123",
      "?source=another&showContentOnly=true",
    );

    expect(direct).toEqual(anotherSource);
    expect(direct.enabled).toBe(true);
  });
});
