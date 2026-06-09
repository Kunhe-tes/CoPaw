import { describe, expect, it } from "vitest";
import {
  isOriginYSearch,
  isRuntimeTaskTabsEnabled,
  shouldEnableOriginYTaskTabs,
} from "./origin";

describe("isOriginYSearch", () => {
  it("returns true only when URL origin is uppercase Y", () => {
    expect(isOriginYSearch("?origin=Y")).toBe(true);
    expect(isOriginYSearch("?foo=bar&origin=Y")).toBe(true);
    expect(isOriginYSearch("?origin=N")).toBe(false);
    expect(isOriginYSearch("?origin=y")).toBe(false);
    expect(isOriginYSearch("?foo=bar")).toBe(false);
    expect(isOriginYSearch("")).toBe(false);
  });

  it("treats only explicit runtime switch values as enabled", () => {
    expect(
      isRuntimeTaskTabsEnabled({ enableOriginYTaskTabs: true }),
    ).toBe(true);
    expect(
      isRuntimeTaskTabsEnabled({ enableOriginYTaskTabs: "true" }),
    ).toBe(true);
    expect(isRuntimeTaskTabsEnabled({ enableOriginYTaskTabs: 1 })).toBe(true);
    expect(
      isRuntimeTaskTabsEnabled({ enableOriginYTaskTabs: false }),
    ).toBe(false);
    expect(
      isRuntimeTaskTabsEnabled({ enableOriginYTaskTabs: "false" }),
    ).toBe(false);
    expect(isRuntimeTaskTabsEnabled(undefined)).toBe(false);
  });

  it("enables task tabs only when origin=Y and runtime switch is on", () => {
    expect(
      shouldEnableOriginYTaskTabs("?origin=Y", {
        enableOriginYTaskTabs: true,
      }),
    ).toBe(true);
    expect(
      shouldEnableOriginYTaskTabs("?origin=Y", {
        enableOriginYTaskTabs: false,
      }),
    ).toBe(false);
    expect(
      shouldEnableOriginYTaskTabs("?origin=N", {
        enableOriginYTaskTabs: true,
      }),
    ).toBe(false);
  });
});
