import { describe, expect, it } from "vitest";
import { displaySkillName, type SkillUsage } from "./tracing";

const baseSkill = (overrides: Partial<SkillUsage> = {}): SkillUsage => ({
  skill_name: "weather",
  count: 1,
  avg_duration_ms: 0,
  ...overrides,
});

describe("displaySkillName", () => {
  it("prefers cn_name when present", () => {
    expect(
      displaySkillName(baseSkill({ cn_name: "天气查询" })),
    ).toBe("天气查询");
  });

  it("falls back to skill_name when cn_name is missing", () => {
    expect(displaySkillName(baseSkill())).toBe("weather");
  });

  it("falls back to skill_name when cn_name is empty string", () => {
    expect(displaySkillName(baseSkill({ cn_name: "" }))).toBe("weather");
  });

  it("falls back to skill_name when cn_name is whitespace only", () => {
    expect(displaySkillName(baseSkill({ cn_name: "   " }))).toBe("weather");
  });
});