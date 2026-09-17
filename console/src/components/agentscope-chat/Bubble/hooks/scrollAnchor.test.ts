import { describe, expect, it } from "vitest";
import { getScrollTopAfterAnchorOffset } from "./scrollAnchor";

describe("getScrollTopAfterPrepend", () => {
  it("keeps reverse-list scroll coordinates unchanged when the visible anchor stays put", () => {
    expect(
      getScrollTopAfterAnchorOffset({
        oldScrollTop: 180,
        previousOffset: 96,
        nextOffset: 96,
      }),
    ).toBe(180);
  });

  it("restores the visible bubble when layout shifts it downward", () => {
    expect(
      getScrollTopAfterAnchorOffset({
        oldScrollTop: -600,
        previousOffset: 96,
        nextOffset: 136,
      }),
    ).toBe(-560);
  });
});
