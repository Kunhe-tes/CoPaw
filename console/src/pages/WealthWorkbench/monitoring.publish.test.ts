import { beforeEach, expect, it, vi } from "vitest";
import * as api from "./api";
import { useWealthStore } from "./store";
import { useIframeStore } from "../../stores/iframeStore";
import {
  defaultMonitoring,
  monitoringScope,
  monitoringStorageKey,
  readMonitoring,
  saveSceneMonitoring,
} from "./monitoring";
import { cycleRange } from "./utils";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  publishPlan: vi.fn(),
}));
const key = (id: string | null) =>
  monitoringStorageKey(monitoringScope(useIframeStore.getState()), id);

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  useIframeStore.setState({ userId: "alice", source: "test", bbk: "bank" });
  useWealthStore.getState().resetPlanForm();
  const [start, end] = cycleRange("本月")!;
  useWealthStore.setState({
    accountId: "rm",
    acting: false,
    draft: {
      name: "监控规划",
      items: [
        {
          id: "scene-1",
          sceneName: "经营场景",
          categoryLabel: "基金",
          categoryCode: "fund",
          mcpRelations: [],
          direction: "经营方向",
          cycle: "本月",
          start,
          end,
          schedule: { type: "daily", hour: 9, minute: 0 },
        },
      ],
    },
  });
});

it("发布成功后按真实规划ID保存监控配置，发布入参不含本地字段", async () => {
  const config = { ...defaultMonitoring(), expectedCompletionRate: 75 };
  saveSceneMonitoring(key(null), "scene-1", config);
  vi.mocked(api.publishPlan).mockResolvedValue({
    plans: [],
    created: true,
    planId: "new-plan",
  });
  expect(await useWealthStore.getState().publishPlan()).toBe(true);
  expect(readMonitoring(key("new-plan"))).toEqual({ "scene-1": config });
  const draft = vi.mocked(api.publishPlan).mock.calls[0][1];
  expect(draft.items[0]).not.toHaveProperty("monitoring");
  expect(draft.items[0]).not.toHaveProperty("expectedCompletionRate");
  expect(readMonitoring(key("other-plan"))).toEqual({});
});

it("编辑已有规划时使用该规划缓存，不混用新建草稿", async () => {
  const config = { ...defaultMonitoring(), expectedCompletionRate: 90 };
  saveSceneMonitoring(key("edit-plan"), "scene-1", config);
  saveSceneMonitoring(key(null), "scene-1", defaultMonitoring());
  useWealthStore.setState({ editingId: "edit-plan" });
  vi.mocked(api.publishPlan).mockResolvedValue({
    plans: [],
    created: false,
    planId: "edit-plan",
  });
  await useWealthStore.getState().publishPlan();
  expect(readMonitoring(key("edit-plan"))["scene-1"]).toEqual(config);
  expect(readMonitoring(key(null))["scene-1"].expectedCompletionRate).toBe(60);
});

it("发布失败保留本地草稿供重试", async () => {
  const config = { ...defaultMonitoring(), cycle: "validity" as const };
  saveSceneMonitoring(key(null), "scene-1", config);
  vi.mocked(api.publishPlan).mockRejectedValue(new Error("发布失败"));
  expect(await useWealthStore.getState().publishPlan()).toBe(false);
  expect(readMonitoring(key(null))["scene-1"]).toEqual(config);
});

it("发布中切换身份或修改草稿不会让旧响应保存到新用户或覆盖新配置", async () => {
  let resolve!: (result: api.PublishResult) => void;
  const originalScope = monitoringScope(useIframeStore.getState());
  const oldConfig = { ...defaultMonitoring(), expectedCompletionRate: 75 };
  saveSceneMonitoring(key(null), "scene-1", oldConfig);
  vi.mocked(api.publishPlan).mockReturnValue(
    new Promise((r) => {
      resolve = r;
    }),
  );
  const publishing = useWealthStore.getState().publishPlan();
  useWealthStore.getState().resetPlanForm();
  useIframeStore.setState({ userId: "bob" });
  saveSceneMonitoring(key(null), "scene-1", defaultMonitoring());
  resolve({ plans: [], created: true, planId: "saved-plan" });
  expect(await publishing).toBe(false);
  expect(
    readMonitoring(monitoringStorageKey(originalScope, "saved-plan"))[
      "scene-1"
    ],
  ).toEqual(oldConfig);
  expect(readMonitoring(key("saved-plan"))).toEqual({});
  expect(readMonitoring(key(null))["scene-1"].expectedCompletionRate).toBe(60);
});
