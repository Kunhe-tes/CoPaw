import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildSkillConfigPayload, skillConfigApi } from "./skillConfig";

const mocks = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("../request", () => ({ request: mocks.request }));

describe("skillConfigApi", () => {
  beforeEach(() => {
    mocks.request.mockReset();
  });

  it("normalizes wrapped list responses with snake_case fields", async () => {
    mocks.request.mockResolvedValue({
      data: {
        rows: [
          {
            skill_id: "deposit_maturity",
            skill_name: "存款到期续接",
            sort_order: 2,
            customer_insight_enabled: 1,
          },
        ],
      },
    });

    await expect(skillConfigApi.listSkillConfigs()).resolves.toMatchObject([
      {
        skillId: "deposit_maturity",
        name: "存款到期续接",
        sort: 2,
        customerInsightEnabled: true,
      },
    ]);
  });

  it("uses the specified create endpoint", async () => {
    mocks.request.mockResolvedValue({});

    await skillConfigApi.createSkillConfig({ skillId: "job-1" });

    expect(mocks.request).toHaveBeenCalledWith(
      "/monitor/busiconfig/skill-config/create",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("preserves the response naming convention when building update payloads", () => {
    const payload = buildSkillConfigPayload(
      {
        skillId: "job-1",
        name: "到期提醒",
        sort: 1,
        groupId: "group-1",
        businessCenterEnabled: true,
        customerInsightEnabled: false,
        outboundCallEnabled: true,
      },
      {
        id: 3,
        skillId: "job-1",
        name: "旧名称",
        sort: 9,
        groupId: undefined,
        businessCenterEnabled: false,
        customerInsightEnabled: false,
        outboundCallEnabled: false,
        enabled: true,
        source: {
          id: 3,
          skill_id: "job-1",
          skill_name: "旧名称",
          sort_order: 9,
        },
      },
    );

    expect(payload).toMatchObject({
      id: 3,
      skill_id: "job-1",
      skill_name: "到期提醒",
      sort_order: 1,
      groupId: "group-1",
    });
  });

  it("writes back every field alias accepted by normalization", () => {
    const source = {
      skill_id: "job-1",
      job_name: "旧名称",
      parentSkillId: "old-group",
      businessOpportunityEnabled: false,
    };

    const payload = buildSkillConfigPayload(
      {
        skillId: "job-1",
        name: "新名称",
        sort: 1,
        groupId: "new-group",
        businessCenterEnabled: true,
        customerInsightEnabled: false,
        outboundCallEnabled: false,
      },
      {
        skillId: "job-1",
        name: "旧名称",
        sort: 1,
        groupId: "old-group",
        businessCenterEnabled: false,
        customerInsightEnabled: false,
        outboundCallEnabled: false,
        enabled: true,
        source,
      },
    );

    expect(payload).toMatchObject({
      job_name: "新名称",
      parentSkillId: "new-group",
      businessOpportunityEnabled: true,
    });
    expect(payload).not.toHaveProperty("name");
    expect(payload).not.toHaveProperty("groupId");
    expect(payload).not.toHaveProperty("businessCenterEnabled");
  });
});
