import { describe, expect, it } from "vitest";
import { resolveMainLayoutPresentation } from "./presentation";

describe("resolveMainLayoutPresentation", () => {
  it("hides the global shell on the first content-only chat render", () => {
    const presentation = resolveMainLayoutPresentation({
      hideMenu: false,
      pathname: "/chat/chat-1",
      search: "?showContentOnly=true",
    });

    expect(presentation.hideGlobalShell).toBe(true);
    expect(presentation.contentOnlyRoute).toMatchObject({
      enabled: true,
      chatId: "chat-1",
    });
  });

  it("ignores showContentOnly on non-chat routes", () => {
    const presentation = resolveMainLayoutPresentation({
      hideMenu: false,
      pathname: "/models",
      search: "?showContentOnly=true",
    });

    expect(presentation.hideGlobalShell).toBe(false);
    expect(presentation.contentOnlyRoute.enabled).toBe(false);
  });

  it("preserves the existing hideMenu and origin-derived shell behavior", () => {
    expect(
      resolveMainLayoutPresentation({
        hideMenu: true,
        pathname: "/chat/chat-1",
        search: "?origin=Y",
      }).hideGlobalShell,
    ).toBe(true);
  });

  it("restores the normal shell as soon as the opt-in value is removed or changed", () => {
    const enabled = resolveMainLayoutPresentation({
      hideMenu: false,
      pathname: "/chat/chat-1",
      search: "?showContentOnly=true",
    });
    const removed = resolveMainLayoutPresentation({
      hideMenu: false,
      pathname: "/chat/chat-1",
      search: "",
    });
    const changed = resolveMainLayoutPresentation({
      hideMenu: false,
      pathname: "/chat/chat-1",
      search: "?showContentOnly=True",
    });

    expect(enabled.hideGlobalShell).toBe(true);
    expect(removed.hideGlobalShell).toBe(false);
    expect(changed.hideGlobalShell).toBe(false);
  });
});
