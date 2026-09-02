import { describe, expect, it } from "vitest";
import { buildChatShareUrl } from "./shareUrl";
import { isShareableTurn } from "./shareSelection";

describe("ChatActionGroup turn selection", () => {
  it("only enables turns with an authoritative completed status", () => {
    const statuses = { completed: "completed", running: "running" };
    expect(isShareableTurn("completed", statuses)).toBe(true);
    expect(isShareableTurn("running", statuses)).toBe(false);
    expect(isShareableTurn("missing", statuses)).toBe(false);
  });
});

describe("ChatActionGroup share URL", () => {
  it("preserves the console basename when building a public link", () => {
    expect(
      buildChatShareUrl("/chat-share/token-1", {
        origin: "https://example.test",
        pathname: "/console/chat/abc",
      }),
    ).toBe("https://example.test/console/chat-share/token-1");
  });

  it("does not duplicate an already-prefixed share path", () => {
    expect(
      buildChatShareUrl("/console/chat-share/token-1", {
        origin: "https://example.test",
        pathname: "/console/chat/abc",
      }),
    ).toBe("https://example.test/console/chat-share/token-1");
  });
});
