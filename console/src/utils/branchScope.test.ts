import { describe, expect, it } from "vitest";
import {
  getScopedBranchFilter,
  HEAD_OFFICE_BBK_ID,
} from "./branchScope";

describe("getScopedBranchFilter", () => {
  it("keeps branch selector editable for head office users", () => {
    expect(getScopedBranchFilter("100")).toEqual({
      isHeadOffice: true,
      lockedBbkId: undefined,
    });
  });

  it("locks branch selector to the current branch for branch users", () => {
    expect(getScopedBranchFilter("200")).toEqual({
      isHeadOffice: false,
      lockedBbkId: "200",
    });
  });

  it("keeps existing editable behavior when branch context is unavailable", () => {
    expect(getScopedBranchFilter(null)).toEqual({
      isHeadOffice: true,
      lockedBbkId: undefined,
    });
    expect(HEAD_OFFICE_BBK_ID).toBe("100");
  });
});
