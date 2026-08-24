import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  buildSkillConfigCreatePayload,
  buildSkillConfigUpdatePayload,
  skillConfigApi,
} from "./skillConfig";

const mocks = vi.hoisted(() => ({ request: vi.fn() }));

vi.mock("../request", () => ({ request: mocks.request }));

describe("skillConfigApi", () => {
  beforeEach(() => {
    mocks.request.mockReset();
  });

  it("loads activity classes with the fixed paging parameters", async () => {
    mocks.request.mockResolvedValue({
      code: 0,
      message: "success",
      data: {
        code: "success",
        errMsg: null,
        totalRows: "1",
        data: [
          {
            bbkOrgId: "571",
            actvClsCd: "group-1",
            actvClsNm: "重点客群",
            actvClsCmt: "重点客户活动分类",
            disSeqNbr: "2",
          },
        ],
      },
    });

    await expect(skillConfigApi.listActivityClasses("571")).resolves.toEqual([
      {
        bbkOrgId: "571",
        activityClassId: "group-1",
        activityClassName: "重点客群",
        description: "重点客户活动分类",
        displayOrder: "2",
      },
    ]);
    expect(mocks.request).toHaveBeenCalledWith(
      "/monitor/busiconfig/actv-cls/list",
      {
        method: "POST",
        body: JSON.stringify({ bbkOrgId: "571", pageNum: 999, startRow: 0 }),
      },
    );
  });

  it("rejects unsuccessful activity class gateway responses", async () => {
    mocks.request.mockResolvedValue({
      code: 0,
      message: "success",
      data: {
        code: "failure",
        errMsg: "网关查询失败",
        totalRows: "0",
        data: [],
      },
    });

    await expect(skillConfigApi.listActivityClasses("571")).rejects.toThrow(
      "网关查询失败",
    );
  });

  it("normalizes wrapped list responses with snake_case fields", async () => {
    mocks.request.mockResolvedValue({
      code: 0,
      message: "success",
      data: [
        {
          skill_id: "deposit_maturity",
          bbk_id: "571",
          skill_name: "存款到期续接",
          bbk_name: "杭州分行",
          sort_order: 2,
          customer_insight_enabled: 1,
          tele_visit_enabled: 1,
          opportunity_center_enabled: 1,
          actv_cls_cd: "group-1",
          actv_cls_nm: "重点客群",
          created_at: "2026-08-17T09:00:00",
          updated_at: "2026-08-17T10:00:00",
        },
      ],
    });

    await expect(skillConfigApi.listSkillConfigs("571")).resolves.toMatchObject(
      [
        {
          skillId: "deposit_maturity",
          bbkId: "571",
          name: "存款到期续接",
          bbkName: "杭州分行",
          sort: 2,
          customerInsightEnabled: true,
          outboundCallEnabled: true,
          businessCenterEnabled: true,
          groupId: "group-1",
          groupName: "重点客群",
          createdAt: "2026-08-17T09:00:00",
          updatedAt: "2026-08-17T10:00:00",
        },
      ],
    );
    expect(mocks.request).toHaveBeenCalledWith(
      "/monitor/busiconfig/skill-config/list",
      {
        method: "POST",
        body: JSON.stringify({ bbk_id: "571" }),
      },
    );
  });

  it("rejects unsuccessful list business responses", async () => {
    mocks.request.mockResolvedValue({
      code: 1,
      message: "分行不存在",
      data: [],
    });

    await expect(skillConfigApi.listSkillConfigs("571")).rejects.toThrow(
      "分行不存在",
    );
  });

  it("posts the selected skill id when loading details", async () => {
    mocks.request.mockResolvedValue({
      code: 0,
      message: "success",
      data: {
        skill_id: "job-1",
        bbk_id: "571",
        skill_name: "到期提醒",
        bbk_name: "杭州分行",
        sort_order: 1,
        customer_insight_enabled: 1,
        tele_visit_enabled: 0,
        opportunity_center_enabled: 1,
        actv_cls_cd: "group-1",
        actv_cls_nm: "重点客群",
        created_at: "2026-08-17T09:00:00",
        updated_at: "2026-08-17T10:00:00",
      },
    });

    await expect(
      skillConfigApi.getSkillConfigDetail("job-1", "571"),
    ).resolves.toMatchObject({
      skillId: "job-1",
      bbkId: "571",
      name: "到期提醒",
      bbkName: "杭州分行",
      sort: 1,
      customerInsightEnabled: true,
      outboundCallEnabled: false,
      businessCenterEnabled: true,
      groupId: "group-1",
      groupName: "重点客群",
      createdAt: "2026-08-17T09:00:00",
      updatedAt: "2026-08-17T10:00:00",
    });

    expect(mocks.request).toHaveBeenCalledWith(
      "/monitor/busiconfig/skill-config/detail",
      {
        method: "POST",
        body: JSON.stringify({ skill_id: "job-1", bbk_id: "571" }),
      },
    );
  });

  it("rejects unsuccessful detail business responses", async () => {
    mocks.request.mockResolvedValue({
      code: 3,
      message: "配置不存在",
      data: {},
    });

    await expect(
      skillConfigApi.getSkillConfigDetail("job-1", "571"),
    ).rejects.toThrow("配置不存在");
  });

  it("posts the selected SKILL identifiers when loading preview stats", async () => {
    mocks.request.mockResolvedValue({
      code: 0,
      message: "success",
      data: { uv: 25, pv: 156 },
    });

    await expect(
      skillConfigApi.getPreviewStats("job-1", "571"),
    ).resolves.toEqual({ uv: 25, pv: 156 });
    expect(mocks.request).toHaveBeenCalledWith(
      "/monitor/busiconfig/skill-config/preview-stats",
      {
        method: "POST",
        body: JSON.stringify({ skill_id: "job-1", bbk_id: "571" }),
      },
    );
  });

  it("rejects unsuccessful preview stats responses", async () => {
    mocks.request.mockResolvedValue({
      code: 2,
      message: "查看数据查询失败",
      data: {},
    });

    await expect(
      skillConfigApi.getPreviewStats("job-1", "571"),
    ).rejects.toThrow("查看数据查询失败");
  });

  it("posts the selected SKILL identifiers when loading value return stats", async () => {
    mocks.request.mockResolvedValue({
      code: 0,
      message: "success",
      data: {
        contact_count: 150,
        list_count: 500,
        contact_rate: 30,
        accept_count: 300,
        accept_rate: 60,
        aum_increase: 1233.89,
        wealth_product_amount: 984.31,
      },
    });

    await expect(
      skillConfigApi.getValueReturnStats("job-1", "571"),
    ).resolves.toEqual({
      contactCount: 150,
      listCount: 500,
      contactRate: 30,
      acceptCount: 300,
      acceptRate: 60,
      aumIncrease: 1233.89,
      wealthProductAmount: 984.31,
    });
    expect(mocks.request).toHaveBeenCalledWith(
      "/monitor/busiconfig/skill-config/value-return-stats",
      {
        method: "POST",
        body: JSON.stringify({ skill_id: "job-1", bbk_id: "571" }),
      },
    );
  });

  it("rejects unsuccessful value return stats responses", async () => {
    mocks.request.mockResolvedValue({
      code: 2,
      message: "回检数据查询失败",
      data: {},
    });

    await expect(
      skillConfigApi.getValueReturnStats("job-1", "571"),
    ).rejects.toThrow("回检数据查询失败");
  });

  it("posts the selected SKILL identifiers when loading exposure stats", async () => {
    mocks.request.mockResolvedValue({
      code: 0,
      message: "success",
      data: {
        total_count: 1000,
        items: [
          {
            seq: 1,
            event_target_id: "module-001",
            event_target_name: "方案模块A",
            exposure_count: 450,
            exposure_rate: "45.00%",
          },
        ],
      },
    });

    await expect(
      skillConfigApi.getSkillExposureStats("job-1", "571"),
    ).resolves.toEqual({
      totalCount: 1000,
      items: [
        {
          sequence: 1,
          targetId: "module-001",
          targetName: "方案模块A",
          exposureCount: 450,
          exposureRate: "45.00%",
        },
      ],
    });
    expect(mocks.request).toHaveBeenCalledWith(
      "/monitor/busiconfig/skill-config/skill-exposure-stats",
      {
        method: "POST",
        body: JSON.stringify({ skill_id: "job-1", bbk_id: "571" }),
      },
    );
  });

  it("rejects unsuccessful exposure stats responses", async () => {
    mocks.request.mockResolvedValue({
      code: 2,
      message: "曝光统计查询失败",
      data: {},
    });

    await expect(
      skillConfigApi.getSkillExposureStats("job-1", "571"),
    ).rejects.toThrow("曝光统计查询失败");
  });

  it("posts the create payload and normalizes the successful response", async () => {
    const payload = buildSkillConfigCreatePayload(
      {
        skillId: "job-1",
        name: "到期提醒",
        sort: 2,
        groupId: "group-1",
        businessCenterEnabled: true,
        customerInsightEnabled: false,
        outboundCallEnabled: true,
      },
      "571",
      "杭州分行",
      "重点客群",
    );
    mocks.request.mockResolvedValue({
      code: 0,
      message: "success",
      data: {
        ...payload,
        created_at: "2026-08-17T09:00:00",
        updated_at: "2026-08-17T10:00:00",
      },
    });

    await expect(
      skillConfigApi.createSkillConfig(payload),
    ).resolves.toMatchObject({
      skillId: "job-1",
      bbkId: "571",
      name: "到期提醒",
      bbkName: "杭州分行",
      sort: 2,
      customerInsightEnabled: false,
      outboundCallEnabled: true,
      businessCenterEnabled: true,
      groupId: "group-1",
      groupName: "重点客群",
    });

    expect(mocks.request).toHaveBeenCalledWith(
      "/monitor/busiconfig/skill-config/create",
      {
        method: "POST",
        body: JSON.stringify({
          skill_id: "job-1",
          bbk_id: "571",
          skill_name: "到期提醒",
          bbk_name: "杭州分行",
          sort_order: 2,
          customer_insight_enabled: 0,
          tele_visit_enabled: 1,
          opportunity_center_enabled: 1,
          actv_cls_cd: "group-1",
          actv_cls_nm: "重点客群",
        }),
      },
    );
  });

  it("rejects invalid create payloads and unsuccessful responses", async () => {
    expect(() =>
      buildSkillConfigCreatePayload(
        {
          skillId: "",
          name: "到期提醒",
          sort: 0,
          businessCenterEnabled: false,
          customerInsightEnabled: false,
          outboundCallEnabled: false,
        },
        "571",
        "杭州分行",
      ),
    ).toThrow("技能ID不能为空且不能超过100个字符");

    mocks.request.mockResolvedValue({
      code: 4,
      message: "配置已存在",
      data: {},
    });
    await expect(
      skillConfigApi.createSkillConfig({
        skill_id: "job-1",
        bbk_id: "571",
        skill_name: "到期提醒",
        bbk_name: "杭州分行",
      }),
    ).rejects.toThrow("配置已存在");
  });

  it("posts the update payload and normalizes the successful response", async () => {
    const payload = buildSkillConfigUpdatePayload(
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
        skillId: "job-1",
        bbkId: "571",
        name: "旧名称",
        bbkName: "杭州分行",
        sort: 9,
        businessCenterEnabled: false,
        customerInsightEnabled: false,
        outboundCallEnabled: false,
        enabled: true,
        source: {},
      },
      "000",
      "重点客群",
    );
    mocks.request.mockResolvedValue({
      code: 0,
      message: "success",
      data: {
        ...payload,
        created_at: "2026-08-17T09:00:00",
        updated_at: "2026-08-17T10:00:00",
      },
    });

    await expect(
      skillConfigApi.updateSkillConfig(payload),
    ).resolves.toMatchObject({
      skillId: "job-1",
      bbkId: "571",
      name: "到期提醒",
      bbkName: "杭州分行",
      sort: 1,
      businessCenterEnabled: true,
      customerInsightEnabled: false,
      outboundCallEnabled: true,
      groupId: "group-1",
      groupName: "重点客群",
    });

    expect(mocks.request).toHaveBeenCalledWith(
      "/monitor/busiconfig/skill-config/update",
      {
        method: "POST",
        body: JSON.stringify({
          skill_id: "job-1",
          bbk_id: "571",
          skill_name: "到期提醒",
          bbk_name: "杭州分行",
          sort_order: 1,
          customer_insight_enabled: 0,
          tele_visit_enabled: 1,
          opportunity_center_enabled: 1,
          actv_cls_cd: "group-1",
          actv_cls_nm: "重点客群",
        }),
      },
    );
  });

  it("rejects unsuccessful update business responses", async () => {
    mocks.request.mockResolvedValue({ code: 2, message: "更新失败", data: {} });

    await expect(
      skillConfigApi.updateSkillConfig({ skill_id: "job-1", bbk_id: "571" }),
    ).rejects.toThrow("更新失败");
  });
});
