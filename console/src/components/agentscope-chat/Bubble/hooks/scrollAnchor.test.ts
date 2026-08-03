import { describe, expect, it } from "vitest";
import { getScrollTopAfterPrepend } from "./scrollAnchor";

describe("getScrollTopAfterPrepend", () => {
  it("adds the inserted height for a top-origin list", () => {
    expect(
      getScrollTopAfterPrepend({
        clientHeight: 400,
        newScrollHeight: 1200,
        oldScrollHeight: 1000,
        oldScrollTop: 180,
        order: "asc",
      }),
    ).toBe(380);
  });

  it("preserves the native reverse scroll coordinate", () => {
    expect(
      getScrollTopAfterPrepend({
        clientHeight: 400,
        newScrollHeight: 1200,
        oldScrollHeight: 1000,
        oldScrollTop: -600,
        order: "desc",
      }),
    ).toBe(-600);
  });
});
