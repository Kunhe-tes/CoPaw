import { beforeEach, expect, it, vi } from "vitest";
import { useIframeStore } from "../../stores/iframeStore";
import {
  defaultMonitoring,
  monitoringScope,
  monitoringStorageKey,
  readMonitoring,
  saveSceneMonitoring,
} from "./monitoring";

beforeEach(() => localStorage.clear());

it("首次配置默认为每日09:00、当日、60%，日期数组独立", () => {
  const first = defaultMonitoring();
  expect(first).toEqual({
    schedule: { type: "daily", hour: 9, minute: 0, daysOfWeek: ["mon"] },
    cycle: "today",
    expectedCompletionRate: 60,
  });
  first.schedule.daysOfWeek.push("tue");
  expect(defaultMonitoring().schedule.daysOfWeek).toEqual(["mon"]);
});

it("按用户来源和规划隔离，重读保留多个场景配置", () => {
  const context = useIframeStore.getState();
  const scope = monitoringScope({ ...context, userId: "alice", source: "one" });
  const key = monitoringStorageKey(scope, "plan-1");
  const config = { ...defaultMonitoring(), expectedCompletionRate: 75 };
  expect(saveSceneMonitoring(key, "scene-1", config)).toBe(true);
  saveSceneMonitoring(key, "scene-2", defaultMonitoring());
  expect(readMonitoring(key)).toEqual({
    "scene-1": config,
    "scene-2": defaultMonitoring(),
  });
  expect(readMonitoring(monitoringStorageKey(scope, "plan-2"))).toEqual({});
  expect(readMonitoring(monitoringStorageKey(scope, null))).toEqual({});
  for (const patch of [
    { userId: "bob" },
    { source: "two" },
    { bbk: "another" },
  ]) {
    const other = monitoringScope({
      ...context,
      userId: "alice",
      source: "one",
      ...patch,
    });
    expect(readMonitoring(monitoringStorageKey(other, "plan-1"))).toEqual({});
  }
});

it("损坏或不合法的缓存不会使页面崩溃或回显错误值", () => {
  localStorage.setItem("key", "broken");
  expect(readMonitoring("key")).toEqual({});
  localStorage.setItem(
    "key",
    JSON.stringify({
      bad: { ...defaultMonitoring(), expectedCompletionRate: 101 },
      good: defaultMonitoring(),
    }),
  );
  expect(readMonitoring("key")).toEqual({ good: defaultMonitoring() });
});

it("存储不可用时返回失败，不影响页面运行", () => {
  const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("quota");
  });
  expect(saveSceneMonitoring("key", "scene", defaultMonitoring())).toBe(false);
  spy.mockRestore();
});
