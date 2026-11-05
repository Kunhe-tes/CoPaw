import { beforeEach, expect, it, vi } from "vitest";
import { request } from "@/api/request";
import { joinInsuranceTracking, removeInsuranceTracking } from "./api";

vi.mock("@/api/request", () => ({ request: vi.fn() }));
vi.mock("@/utils/identity", () => ({ getUserId: () => "qa-user" }));
vi.mock("../../operations", () => ({
  getWorkbenchContext: () => ({
    bbk: "100",
    orgCode: "10001",
    positionId: "RB0101",
  }),
}));
beforeEach(() => {
  vi.clearAllMocks();
});
const customer = { custUid: "c1", skillId: "insurance", bbkOrgId: "10001" };
const values = {
  insurancePlan: "家庭保障",
  intention: 0 as const,
  contactPlans: [
    { date: "2026-11-07", method: 0 as const, content: "企微沟通" },
  ],
};

it("加入请求沿用网关上下文，携带数值枚举和完整计划数组", async () => {
  vi.mocked(request).mockResolvedValue({ code: 200, data: null });
  await joinInsuranceTracking(customer, values, "request-id");
  expect(request).toHaveBeenCalledWith(
    "/agent/workspace/insurance-tracking/add",
    expect.objectContaining({ method: "POST" }),
  );
  const body = JSON.parse(String(vi.mocked(request).mock.calls[0][1]?.body));
  expect(body).toEqual({
    ...customer,
    ...values,
    requestId: "request-id",
    sapId: "qa-user",
    bbkId: "100",
    subBbkId: "10001",
    posId: "RB0101",
    platformSource: "WP",
    pageSource: "WP_AGENT_WORKSPACE_TASK_LIST",
  });
  expect(typeof body.intention).toBe("number");
  expect(typeof body.contactPlans[0].method).toBe("number");
});

it("业务失败与网络失败向上抛出，不返回虚构成功", async () => {
  vi.mocked(request).mockResolvedValueOnce({ code: 500, message: "服务失败" });
  await expect(
    joinInsuranceTracking(customer, values, "request-id"),
  ).rejects.toThrow("服务失败");
  vi.mocked(request).mockRejectedValueOnce(new Error("网络错误"));
  await expect(
    joinInsuranceTracking(customer, values, "request-id"),
  ).rejects.toThrow("网络错误");
});

it("移除接口携带跟踪ID、客户与机构上下文，仅服务端200视为成功", async () => {
  const target = {
    id: "tracking-1",
    custUid: "c1",
    bbkOrgId: "10001",
    name: "林芳",
    intention: 3 as const,
  };
  vi.mocked(request).mockResolvedValueOnce({ code: 200, data: null });
  await removeInsuranceTracking(target, "remove-id");
  expect(request).toHaveBeenCalledWith(
    "/agent/workspace/insurance-tracking/remove",
    expect.objectContaining({ method: "POST" }),
  );
  const body = JSON.parse(String(vi.mocked(request).mock.calls[0][1]?.body));
  expect(body).toMatchObject({
    id: "tracking-1",
    custUid: "c1",
    bbkOrgId: "10001",
    requestId: "remove-id",
    sapId: "qa-user",
    bbkId: "100",
    subBbkId: "10001",
    posId: "RB0101",
  });
  vi.mocked(request).mockResolvedValueOnce({ code: 500, message: "移除异常" });
  await expect(removeInsuranceTracking(target, "remove-id")).rejects.toThrow(
    "移除异常",
  );
});
