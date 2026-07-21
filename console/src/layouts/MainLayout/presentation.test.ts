import { describe, expect, it } from "vitest";
import { resolveMainLayoutPresentation } from "./presentation";

describe("resolveMainLayoutPresentation", () => {
  it("hides the global shell on the first content-only chat render", () => {
    const presentation = resolveMainLayoutPresentation({
      hideMenu: false,
      pathname: "/chat/chat-1",
      showContentOnly: true,
    });

    expect(presentation.hideGlobalShell).toBe(true);
    expect(presentation.contentOnlyRoute).toMatchObject({
      enabled: true,
      chatId: "chat-1",
    });
  });

  it("ignores content-only presentation on non-chat routes", () => {
    const presentation = resolveMainLayoutPresentation({
      hideMenu: false,
      pathname: "/models",
      showContentOnly: true,
    });

    expect(presentation.hideGlobalShell).toBe(false);
    expect(presentation.contentOnlyRoute.enabled).toBe(false);
  });

  it("preserves the existing hideMenu and origin-derived shell behavior", () => {
    expect(
      resolveMainLayoutPresentation({
        hideMenu: true,
        pathname: "/chat/chat-1",
        showContentOnly: false,
      }).hideGlobalShell,
    ).toBe(true);
  });

  it("preserves normal shell behavior when content-only was not requested", () => {
    const enabled = resolveMainLayoutPresentation({
      hideMenu: false,
      pathname: "/chat/chat-1",
      showContentOnly: true,
    });
    const normal = resolveMainLayoutPresentation({
      hideMenu: false,
      pathname: "/chat/chat-1",
      showContentOnly: false,
    });

    expect(enabled.hideGlobalShell).toBe(true);
    expect(normal.hideGlobalShell).toBe(false);
  });
});
