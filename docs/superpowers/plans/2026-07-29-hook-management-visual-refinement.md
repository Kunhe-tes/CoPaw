# Hook 管理视觉优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变 Hook 配置数据、接口或运行语义的前提下，将现有事件总览和编辑抽屉优化成“运营总览 + 深度编排工作台”。

**Architecture:** `HookManagementPage` 继续作为 draft、保存、上传和人工测试 API 的唯一所有者。`EventOverview` 只从 draft 派生发布状态、指标、生命周期和事件行；`EventEditorDrawer` 只编排传入的事件编辑内容，并通过回调返回用户操作。纯 view-model helper 提供可测试的事件计数、处理器链摘要和生命周期顺序，避免将业务推导散落在 JSX 中。

**Tech Stack:** React 18、TypeScript、Ant Design 5、@ant-design/icons、Less Modules、Vitest、React Testing Library。

---

## Files and responsibilities

- Create: `console/src/pages/Control/HookManagement/overviewModel.ts` — 事件计数、处理器链标签、生命周期序列的无副作用视图数据。
- Create: `console/src/pages/Control/HookManagement/overviewModel.test.ts` — 固定事件顺序与空/已配置事件摘要的单元测试。
- Modify: `console/src/pages/Control/HookManagement/components/EventOverview.tsx` — 状态横幅、三项指标、生命周期轨道、已配置事件表和未配置事件入口。
- Modify: `console/src/pages/Control/HookManagement/components/EventEditorDrawer.tsx` — 带状态标签、操作区、四个编辑区和编排工作台的事件抽屉。
- Modify: `console/src/pages/Control/HookManagement/index.tsx` — 向总览与抽屉传递保存、草稿、人工测试和已选择编辑器内容，不改变现有 API 调用。
- Modify: `console/src/pages/Control/HookManagement/index.module.less` — 完成总览层级、处理器管线、抽屉双栏和窄屏样式。
- Modify: `console/src/pages/Control/HookManagement/index.test.tsx` — 覆盖参考设计对应的总览状态、抽屉分区、保存与人工测试回归。

## Task 1: 用可测试的视图模型固定总览数据

**Files:**

- Create: `console/src/pages/Control/HookManagement/overviewModel.ts`
- Create: `console/src/pages/Control/HookManagement/overviewModel.test.ts`

- [ ] **Step 1: 写出事件摘要的失败单元测试。**

```ts
import { describe, expect, it } from "vitest";

import { getEventSummary, getLifecycleEvents } from "./overviewModel";

describe("Hook overview model", () => {
  it("returns configured event counts and handler labels in lifecycle order", () => {
    const summary = getEventSummary(
      {
        enabled: true,
        events: {
          PostToolUse: [{ id: "results", matcher: { tools: [] }, hooks: [
            { id: "parse", type: "prompt", prompt: "parse" },
            { id: "record", type: "command", argv: ["echo", "record"] },
          ] }],
          PreToolUse: [{ id: "guards", matcher: { tools: [] }, hooks: [
            { id: "validate", type: "http", url: "https://example.test" },
          ] }],
        },
      },
      "PostToolUse",
    );

    expect(summary).toMatchObject({ groups: 1, handlers: 2, configured: true });
    expect(summary.handlerLabels).toEqual(["Prompt", "Command"]);
    expect(getLifecycleEvents({ enabled: true, events: {} })).toEqual([
      "SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
      "PostToolUseFailure", "BeforeStop", "Stop",
    ]);
  });
});
```

- [ ] **Step 2: 运行测试，确认模块尚不存在。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement/overviewModel.test.ts`

Expected: FAIL，提示无法解析 `./overviewModel`。

- [ ] **Step 3: 实现只读视图模型。**

在 `overviewModel.ts` 中使用现有 `eventMetadata` 的 `order`，不要重新声明事件顺序。实现下列导出；空事件必须返回 `configured: false`、`groups: 0` 和空的 `handlerLabels`。

```ts
export type EventSummary = {
  configured: boolean;
  groups: number;
  handlers: number;
  handlerLabels: string[];
};

export function getLifecycleEvents(config: HookConfigDraft): HookEventName[] {
  return (Object.keys(eventMetadata) as HookEventName[]).sort(
    (left, right) => eventMetadata[left].order - eventMetadata[right].order,
  );
}

export function getEventSummary(
  config: HookConfigDraft,
  event: HookEventName,
): EventSummary {
  const groups = config.events[event] ?? [];
  const handlers = groups.flatMap((group) => group.hooks);
  return {
    configured: event in config.events,
    groups: groups.length,
    handlers: handlers.length,
    handlerLabels: handlers.map((handler) =>
      handler.type === "http" ? "HTTP" : handler.type === "prompt" ? "Prompt" : "Command",
    ),
  };
}
```

- [ ] **Step 4: 运行视图模型测试。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement/overviewModel.test.ts`

Expected: PASS，所有 `Hook overview model` 断言通过。

- [ ] **Step 5: 提交独立的视图数据基础。**

```bash
git add console/src/pages/Control/HookManagement/overviewModel.ts \
  console/src/pages/Control/HookManagement/overviewModel.test.ts
git commit -m "feat(hooks): add overview view model"
```

## Task 2: 重建运营总览的信息层级

**Files:**

- Modify: `console/src/pages/Control/HookManagement/components/EventOverview.tsx`
- Modify: `console/src/pages/Control/HookManagement/index.module.less`
- Modify: `console/src/pages/Control/HookManagement/index.test.tsx`

- [ ] **Step 1: 写出总览层级的失败组件测试。**

在现有 `HookManagementPage` 测试中增加：

```tsx
it("shows hook health, lifecycle and processor chains in the overview", async () => {
  render(<HookManagementPage />);

  expect(await screen.findByText("Hook 已启用")).toBeInTheDocument();
  expect(screen.getByText("已配置事件")).toBeInTheDocument();
  expect(screen.getByText("处理器数量")).toBeInTheDocument();
  expect(screen.getByText("生命周期总览")).toBeInTheDocument();
  expect(screen.getByText("PreToolUse")).toBeInTheDocument();
  expect(screen.getByText("Command")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "编辑配置 PreToolUse" })).toBeInTheDocument();
});
```

- [ ] **Step 2: 运行测试，确认当前卡片网格不提供这些元素。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement/index.test.tsx`

Expected: FAIL，找不到 “Hook 已启用” 和 “生命周期总览”。

- [ ] **Step 3: 将 `EventOverview` 改为总览横幅、指标、轨道和事件列表。**

保留现有 props，并从 `getLifecycleEvents(config)` 和 `getEventSummary(config, event)` 派生全部显示内容。添加以下可访问的语义与固定文本：

```tsx
<section aria-label="Hook 状态" className={styles.statusBanner}>
  <div>
    <strong>{config.enabled ? "Hook 已启用" : "Hook 已停用"}</strong>
    <span>{dirty ? "当前配置存在未保存修改" : "当前配置正在生效"}</span>
  </div>
  <span className={styles.globalSwitch}>
    <Switch checked={config.enabled} onChange={onEnabledChange} aria-label="启用 Hook" />
    全局启用
  </span>
</section>
```

在横幅下渲染三个 `article`：`已配置事件`、`处理器数量`、`待发布修改`；待发布修改在 `dirty` 时显示 `1`，否则显示 `0`。生命周期轨道必须渲染全部七个事件，并为已配置事件加 `data-configured="true"`。已配置事件用四列列表展示事件、处理器链、状态、操作；链标签仅使用 `handlerLabels` 的前 3 项，并追加 `+N` 表示剩余项。未配置事件单独显示，每个按钮名称为 `新建规则 ${event}`。总览头的主操作保留为 `新建 Hook 规则`。

- [ ] **Step 4: 以 Less 实现参考图的克制层级。**

在 `index.module.less` 新增并使用 `.statusBanner`、`.metricGrid`、`.metricCard`、`.lifecyclePanel`、`.lifecycleTrack`、`.lifecycleStep`、`.eventTable`、`.eventRow`、`.processorChain`、`.unconfiguredEvents`。状态横幅使用浅蓝灰背景和 1px 边框；指标卡使用三列栅格；生命周期在桌面端单行水平滚动而不是压缩文本；事件行至少包含 64px 高度。手机端（`max-width: 760px`）改为单列指标、可横向滚动的轨道和两行事件摘要，操作按钮保持完整文本。

- [ ] **Step 5: 运行总览相关测试。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement/index.test.tsx`

Expected: PASS，包含新增总览断言和既有保存、冲突、脚本上传断言。

- [ ] **Step 6: 提交总览视觉改造。**

```bash
git add console/src/pages/Control/HookManagement/components/EventOverview.tsx \
  console/src/pages/Control/HookManagement/index.module.less \
  console/src/pages/Control/HookManagement/index.test.tsx
git commit -m "feat(hooks): refine operational overview"
```

## Task 3: 将事件抽屉组织为深度编排工作台

**Files:**

- Modify: `console/src/pages/Control/HookManagement/components/EventEditorDrawer.tsx`
- Modify: `console/src/pages/Control/HookManagement/index.tsx`
- Modify: `console/src/pages/Control/HookManagement/index.module.less`
- Modify: `console/src/pages/Control/HookManagement/index.test.tsx`

- [ ] **Step 1: 写出抽屉分区和测试入口的失败测试。**

```tsx
it("opens a four-section event workspace with the selected handler detail", async () => {
  render(<HookManagementPage />);
  fireEvent.click(await screen.findByRole("button", { name: "编辑配置 PreToolUse" }));

  expect(screen.getByRole("dialog", { name: "编辑 PreToolUse" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "基本设置" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "适用范围" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "处理器编排" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "测试与发布" })).toBeInTheDocument();
  expect(screen.getByText("执行顺序")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "执行人工测试" })).toBeInTheDocument();
});
```

- [ ] **Step 2: 运行测试，确认当前抽屉没有四个标签页。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement/index.test.tsx`

Expected: FAIL，找不到名为 “基本设置” 的 tab。

- [ ] **Step 3: 扩展 `EventEditorDrawer` 的显式内容与保存 props。**

将 props 增加为：

```ts
basicDetails: ReactNode;
scopeDetails: ReactNode;
testDetails: ReactNode;
dirty: boolean;
saving: boolean;
onSave: () => void;
```

抽屉头部显示 `编辑 ${event}`、`草稿`（仅在 `dirty` 时）和已有删除操作；右侧主按钮必须为 `保存并激活`，调用 `onSave` 并显示 `saving`。正文使用 Ant Design `Tabs`，顺序严格为 `基本设置`、`适用范围`、`处理器编排`、`测试与发布`。基本设置渲染 `basicDetails`；适用范围在已有分组摘要后渲染 `scopeDetails`；处理器编排渲染左侧有编号的 handler 卡片和右侧 `details`；测试与发布渲染 `testDetails`。处理器卡片继续保留选择、删除、上移、下移和添加类型，且按钮 `aria-label` 不变。

- [ ] **Step 4: 在页面中组装四个区域，不改变请求语义。**

在 `index.tsx` 中保留 `renderHandlerEditor`、`renderGroupEditor`、`runTest`、现有测试 Modal 和 `save`。新增以下节点并传入抽屉，不能在抽屉中直接调用 API：

```tsx
const basicDetails = (
  <div className={styles.eventBasics}>
    <span className={styles.eventCode}>{editingEvent}</span>
    <p>{editingEvent ? eventMetadata[editingEvent].description : ""}</p>
    <Tag color={draft.enabled ? "success" : "default"}>
      {draft.enabled ? "该事件将参与 Hook 执行" : "全局 Hook 当前已停用"}
    </Tag>
  </div>
);
```

将 `renderGroupEditor()` 传为 `scopeDetails`。将 `renderHandlerEditor()` 传为 `details`；当没有 handler 被选中时传递 “选择一个处理器以编辑详细配置。”。`testDetails` 包含当前事件的处理器数量、`执行人工测试` 按钮，以及 `testResult` 的 JSON 摘要；该按钮仅在选中 handler 时可用，未选中时禁用并给出 `title="请先选择一个处理器"`。抽屉 `onSave={() => void save()}`，使页面级保存与抽屉保存使用同一校验、revision 与冲突逻辑。

- [ ] **Step 5: 实现编排工作台布局。**

在 `index.module.less` 新增 `.drawerHeaderMeta`、`.drawerTabs`、`.pipelineWorkspace`、`.pipelineList`、`.pipelineStep`、`.pipelineStepNumber`、`.selectedPipelineStep`、`.handlerDetailPanel`、`.testPublishPanel`、`.eventBasics`。`.pipelineWorkspace` 在桌面端为 `minmax(250px, .9fr) minmax(320px, 1.1fr)` 两列；处理器步骤使用纵向细线和蓝色圆形序号；被选中步骤使用蓝色边框和淡蓝底；小于 760px 时变为一列、编辑详情置于步骤列表之后。

- [ ] **Step 6: 运行抽屉、人工测试与保存回归。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement/index.test.tsx`

Expected: PASS，新增抽屉工作台断言和现有 `执行人工测试`、处理器重排、409 冲突断言通过。

- [ ] **Step 7: 提交抽屉工作台。**

```bash
git add console/src/pages/Control/HookManagement/components/EventEditorDrawer.tsx \
  console/src/pages/Control/HookManagement/index.tsx \
  console/src/pages/Control/HookManagement/index.module.less \
  console/src/pages/Control/HookManagement/index.test.tsx
git commit -m "feat(hooks): refine event editor workspace"
```

## Task 4: 执行完整验证并检查影响范围

**Files:**

- Modify: `console/src/pages/Control/HookManagement/overviewModel.ts`
- Modify: `console/src/pages/Control/HookManagement/components/EventOverview.tsx`
- Modify: `console/src/pages/Control/HookManagement/components/EventEditorDrawer.tsx`
- Modify: `console/src/pages/Control/HookManagement/index.tsx`
- Modify: `console/src/pages/Control/HookManagement/index.module.less`
- Modify: `console/src/pages/Control/HookManagement/index.test.tsx`

- [ ] **Step 1: 运行所有 Hook 管理单元和组件测试。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement`

Expected: PASS，`draft`、场景模板、视图模型和页面测试全部通过。

- [ ] **Step 2: 运行 Console 类型检查和生产构建。**

Run: `cd console && pnpm build`

Expected: PASS，TypeScript 无错误且 Vite 生成生产构建。

- [ ] **Step 3: 手工验证响应式视觉。**

Run: `cd console && pnpm dev --host 127.0.0.1 --port 4173`

Expected: 页面在桌面宽度显示状态横幅、三项指标、生命周期轨道和事件表；在 760px 宽度下指标与抽屉编排区变为单列，操作文字不被截断。

- [ ] **Step 4: 执行变更影响分析。**

Run: GitNexus `detect_changes({ scope: "all", repo: "CoPaw" })`，并检查改动是否仅映射到 Hook Management Console 页面及其测试。

Expected: 不出现 Hook runtime、配置保存 API 或租户隔离执行流程的意外改动。

- [ ] **Step 5: 提交验证后的实现。**

```bash
git add console/src/pages/Control/HookManagement
git commit -m "test(hooks): verify management visual redesign"
```
