import { describe, expect, it } from "vitest";

import { KEY_TO_LABEL, KEY_TO_PATH } from "./constants";

describe("Console navigation constants", () => {
  it("maps Hook management into the Run Center route", () => {
    expect(KEY_TO_PATH["hook-management"]).toBe("/hook-management");
    expect(KEY_TO_LABEL["hook-management"]).toBe("nav.hookManagement");
  });
});
