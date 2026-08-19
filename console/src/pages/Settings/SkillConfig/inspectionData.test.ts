import { describe, expect, it } from "vitest";
import type { SkillValueReturnStats } from "@/api/modules/skillConfig";
import { buildSkillInspectionData } from "./inspectionData";

function buildValueReturnStats(
  amounts: Pick<SkillValueReturnStats, "aumIncrease" | "wealthProductAmount">,
): SkillValueReturnStats {
  return {
    contactCount: 0,
    listCount: 0,
    contactRate: 0,
    acceptCount: 0,
    acceptRate: 0,
    ...amounts,
  };
}

describe("buildSkillInspectionData", () => {
  it("keeps amounts below 10000 in yuan and switches the boundary to ten-thousands", () => {
    const data = buildSkillInspectionData(
      undefined,
      buildValueReturnStats({
        aumIncrease: 9999.99,
        wealthProductAmount: 10000,
      }),
    );

    expect(data.sections[2].metrics).toEqual([
      expect.objectContaining({ value: "9999.99", suffix: "元" }),
      expect.objectContaining({ value: "1", suffix: "万元" }),
    ]);
  });

  it("converts large yuan amounts to ten-thousands with at most two decimals", () => {
    const data = buildSkillInspectionData(
      undefined,
      buildValueReturnStats({
        aumIncrease: 123456.78,
        wealthProductAmount: 100000000,
      }),
    );

    expect(data.sections[2].metrics).toEqual([
      expect.objectContaining({ value: "12.35", suffix: "万元" }),
      expect.objectContaining({ value: "10000", suffix: "万元" }),
    ]);
  });

  it("does not append a currency unit when an amount is unavailable", () => {
    const data = buildSkillInspectionData();

    expect(
      data.sections[2].metrics.map((metric) => [metric.value, metric.suffix]),
    ).toEqual([
      ["--", undefined],
      ["--", undefined],
    ]);
  });
});
