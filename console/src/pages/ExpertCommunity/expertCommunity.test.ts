import { describe, expect, it } from "vitest";
import type { MarketExpert } from "../../api/modules/market";
import { countExpertBbkIds, matchesExpertSearch } from "./expertCommunity";

function buildExpert(overrides: Partial<MarketExpert> = {}): MarketExpert {
  return {
    item_id: "expert-1",
    name: "reviewer",
    description: "Review changes",
    version: "1.0.0",
    creator_id: "creator-1",
    creator_name: "Alice",
    category_id: 1,
    bbk_ids: ["100"],
    status: "active",
    created_at: "2026-08-21T00:00:00Z",
    updated_at: "2026-08-21T00:00:00Z",
    ...overrides,
  };
}

describe("expert community helpers", () => {
  it("matches name, description, or creator after trimming the query", () => {
    const expert = buildExpert({ description: "审查代码变更" });

    expect(matchesExpertSearch(expert, "  审查代码  ")).toBe(true);
    expect(matchesExpertSearch(expert, "alice")).toBe(true);
    expect(matchesExpertSearch(expert, "missing")).toBe(false);
  });

  it("counts experts by BBK without counting duplicate assignments twice", () => {
    const counts = countExpertBbkIds([
      buildExpert({ bbk_ids: ["100", "200"] }),
      buildExpert({ item_id: "expert-2", bbk_ids: ["100"] }),
      buildExpert({ item_id: "expert-3", bbk_ids: [] }),
    ]);

    expect(counts.get("100")).toBe(2);
    expect(counts.get("200")).toBe(1);
    expect(counts.size).toBe(2);
  });
});
