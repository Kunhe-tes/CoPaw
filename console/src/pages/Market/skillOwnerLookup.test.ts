import { describe, expect, it } from "vitest";
import {
  buildSkillOwnerRows,
  resolveMarketSkillName,
} from "./skillOwnerLookup";

describe("skillOwnerLookup", () => {
  it("uses stable market skill_name before display name", () => {
    expect(
      resolveMarketSkillName({
        item_id: "market-1",
        name: "Pretty Name",
        skill_name: "stable-name",
      }),
    ).toBe("stable-name");
  });

  it("matches tenant skills by name and returns version status", () => {
    const rows = buildSkillOwnerRows({
      marketSkill: {
        item_id: "market-1",
        name: "sales-helper",
        version: "2.0.0",
      },
      tenants: [
        {
          tenant_id: "user-a",
          tenant_name: "Alice",
          bbk_id: "1001",
        },
        {
          tenant_id: "user-b",
          tenant_name: "Bob",
          bbk_id: "2002",
        },
      ],
      skillsByTenant: {
        "user-a": [
          {
            skill_name: "sales-helper",
            display_name: "Sales Helper",
            source: "market",
            description: "",
            version: "1.0.0",
            received_version: "1.0.0",
            distributed_by: "admin",
            is_received: true,
            has_update: false,
            enabled: true,
          },
        ],
        "user-b": [
          {
            skill_name: "other-helper",
            display_name: "Other Helper",
            source: "market",
            description: "",
            version: "2.0.0",
            received_version: "2.0.0",
            distributed_by: "admin",
            is_received: true,
            has_update: false,
            enabled: true,
          },
        ],
      },
    });

    expect(rows).toEqual([
      {
        tenant_id: "user-a",
        tenant_name: "Alice",
        bbk_id: "1001",
        skill_name: "sales-helper",
        market_version: "2.0.0",
        installed_version: "1.0.0",
        received_version: "1.0.0",
        enabled: true,
        has_update: true,
        match_source: "name_match",
      },
    ]);
  });

  it("treats user-side has_update as needing update", () => {
    const rows = buildSkillOwnerRows({
      marketSkill: {
        item_id: "market-1",
        name: "review-helper",
        version: "2.0.0",
      },
      tenants: [
        {
          tenant_id: "user-a",
          tenant_name: null,
          bbk_id: null,
        },
      ],
      skillsByTenant: {
        "user-a": [
          {
            skill_name: "review-helper",
            display_name: "Review Helper",
            source: "market",
            description: "",
            version: "2.0.0",
            received_version: null,
            distributed_by: "admin",
            is_received: true,
            has_update: true,
            enabled: false,
          },
        ],
      },
    });

    expect(rows[0].has_update).toBe(true);
    expect(rows[0].installed_version).toBe("2.0.0");
    expect(rows[0].enabled).toBe(false);
  });
});
