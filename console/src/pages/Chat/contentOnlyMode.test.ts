import { describe, expect, it } from "vitest";
import { resolveChatContentOnlyRoute } from "./contentOnlyMode";

describe("resolveChatContentOnlyRoute", () => {
  it("activates a requested presentation on a concrete chat route", () => {
    expect(resolveChatContentOnlyRoute("/chat/chat-123", true)).toEqual({
      chatId: "chat-123",
      enabled: true,
      isChatRoute: true,
    });

    expect(resolveChatContentOnlyRoute("/chat/chat-123", false).enabled).toBe(
      false,
    );
  });

  it("does not activate without a concrete chat target", () => {
    expect(resolveChatContentOnlyRoute("/chat", true)).toEqual({
      enabled: false,
      isChatRoute: true,
    });
  });

  it("ignores the requested presentation on non-chat routes", () => {
    expect(resolveChatContentOnlyRoute("/models", true)).toEqual({
      enabled: false,
      isChatRoute: false,
    });
  });
});
