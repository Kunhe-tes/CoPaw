# Hook 管理页重设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Hook 管理页改为事件总览、完整场景模板和抽屉式事件编辑，同时保持现有 Hook 配置格式与 API 不变。

**Architecture:** `HookManagementPage` 保留加载、保存、脚本库和现有测试 API 调用，成为 draft 的唯一所有者。事件总览与编辑抽屉拆分为专职组件；纯函数负责事件摘要、场景模板和处理器重排，所有结果仍映射回 `HookConfigDraft.events[event][group].hooks`。

**Tech Stack:** React 18、TypeScript、Ant Design 5、@dnd-kit/sortable、Immer、Vitest、React Testing Library、Less Modules。

---

## Files and responsibilities

- Create: `console/src/pages/Control/HookManagement/eventMetadata.ts` — 事件的显示名称、说明和固定展示顺序。
- Create: `console/src/pages/Control/HookManagement/scenarioTemplates.ts` — 完整场景模板，以及生成独立事件草稿的纯函数。
- Create: `console/src/pages/Control/HookManagement/scenarioTemplates.test.ts` — 模板事件和默认处理器的单元测试。
- Create: `console/src/pages/Control/HookManagement/components/EventOverview.tsx` — 事件摘要列表、空状态、全局开关和进入编辑动作。
- Create: `console/src/pages/Control/HookManagement/components/EventEditorDrawer.tsx` — 单一事件的编辑抽屉、分组与处理器管理、手动测试入口。
- Create: `console/src/pages/Control/HookManagement/components/HandlerList.tsx` — 同组处理器卡片、键盘排序和展开编辑。
- Modify: `console/src/pages/Control/HookManagement/draft.ts` — 增加不可变的事件替换、处理器移动和事件复制 helper。
- Modify: `console/src/pages/Control/HookManagement/draft.test.ts` — 覆盖新增 draft helper。
- Modify: `console/src/pages/Control/HookManagement/index.tsx` — 组合总览与抽屉，保留保存、冲突、脚本库与真实测试确认逻辑。
- Modify: `console/src/pages/Control/HookManagement/index.module.less` — 用总览、抽屉、卡片和窄屏样式取代树状工作区样式。
- Modify: `console/src/pages/Control/HookManagement/index.test.tsx` — 覆盖新的关键用户流程，保留脚本库与保存冲突回归测试。

## Task 1: 建立事件展示和完整场景模板

**Files:**
- Create: `console/src/pages/Control/HookManagement/eventMetadata.ts`
- Create: `console/src/pages/Control/HookManagement/scenarioTemplates.ts`
- Create: `console/src/pages/Control/HookManagement/scenarioTemplates.test.ts`

- [ ] **Step 1: 写出模板的失败测试。**

```ts
import { describe, expect, it } from "vitest";
import { createScenarioEvent, scenarioTemplates } from "./scenarioTemplates";

describe("Hook scenario templates", () => {
  it("creates an independent complete tool-audit event", () => {
    const event = createScenarioEvent("tool-audit");

    expect(event.event).toBe("PostToolUse");
    expect(event.groups).toHaveLength(1);
    expect(event.groups[0]).toMatchObject({ matcher: { tools: [] } });
    expect(event.groups[0]?.hooks[0]).toMatchObject({
      type: "prompt",
      failPolicy: "allow",
    });
  });

  it("does not share nested template state between creations", () => {
    const first = createScenarioEvent("tool-audit");
    const second = createScenarioEvent("tool-audit");
    first.groups[0]?.hooks.push({ id: "extra", type: "prompt", prompt: "x" });

    expect(second.groups[0]?.hooks).toHaveLength(1);
  });

  it("lists the user-facing complete scenario choices", () => {
    expect(scenarioTemplates.map((template) => template.id)).toEqual([
      "session-start-check",
      "prompt-preprocess",
      "tool-audit",
      "tool-block",
      "failure-alert",
    ]);
  });
});
```

- [ ] **Step 2: 验证测试因模块不存在而失败。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement/scenarioTemplates.test.ts`

Expected: FAIL，提示无法解析 `./scenarioTemplates`。

- [ ] **Step 3: 实现固定事件元数据和模板工厂。**

`eventMetadata.ts` 定义 `eventMetadata`，键为现有七个 `HookEventName`，每项有 `label`、`description`、`order`；不要增加后端没有的事件名。`scenarioTemplates.ts` 导出以下稳定类型和函数：

```ts
export type ScenarioTemplateId =
  | "session-start-check"
  | "prompt-preprocess"
  | "tool-audit"
  | "tool-block"
  | "failure-alert";

export type ScenarioEvent = {
  event: HookEventName;
  groups: HookMatcherGroupDraft[];
};

export function createScenarioEvent(id: ScenarioTemplateId): ScenarioEvent {
  const template = scenarioTemplates.find((item) => item.id === id);
  if (!template) throw new Error(`Unknown Hook scenario template: ${id}`);
  return structuredClone({ event: template.event, groups: template.groups });
}
```

模板均创建一个 `matcher: { tools: [] }` 的分组和一个可保存的 `prompt` 处理器；`tool-block` 使用 `failPolicy: "block"`，其余使用 `"allow"`。Prompt 内容必须是可直接执行的中文任务说明，不能用空字符串或虚构命令/URL。模板工厂在每次创建时生成 ID：

```ts
function createTemplatePrompt(
  idPrefix: string,
  prompt: string,
  failPolicy: "allow" | "block",
): HookHandlerDraft {
  return {
    id: `${idPrefix}-${crypto.randomUUID().slice(0, 8)}`,
    type: "prompt",
    prompt,
    if: "",
    timeout: 10,
    statusMessage: "",
    once: false,
    includeConversationSnapshot: false,
    conversationSnapshotLimit: 50,
    failPolicy,
  };
}
```

- [ ] **Step 4: 验证模板单测通过。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement/scenarioTemplates.test.ts`

Expected: PASS，3 个断言通过。

- [ ] **Step 5: 提交模板基础。**

```bash
git add console/src/pages/Control/HookManagement/eventMetadata.ts \
  console/src/pages/Control/HookManagement/scenarioTemplates.ts \
  console/src/pages/Control/HookManagement/scenarioTemplates.test.ts
git commit -m "feat(hooks): add event scenario templates"
```

## Task 2: 给 draft 增加事件替换和处理器排序能力

**Files:**
- Modify: `console/src/pages/Control/HookManagement/draft.ts`
- Modify: `console/src/pages/Control/HookManagement/draft.test.ts`

- [ ] **Step 1: 写出处理器移动和模板事件替换的失败测试。**

```ts
it("moves a Handler without crossing its Matcher Group boundary", () => {
  const next = moveHandler(config, "PreToolUse", "tool-guards", 0, 1);

  expect(next.events.PreToolUse[0]?.hooks.map((hook) => hook.id)).toEqual([
    "second-handler",
    "guard-shell",
  ]);
  expect(config.events.PreToolUse[0]?.hooks[0]?.id).toBe("guard-shell");
});

it("replaces one event with a scenario event without mutating another event", () => {
  const scenario = createScenarioEvent("tool-audit");
  const next = replaceEvent(config, "PostToolUse", scenario.groups);

  expect(next.events.PostToolUse).toEqual(scenario.groups);
  expect(next.events.PreToolUse).toEqual(config.events.PreToolUse);
});
```

Extend the `PreToolUse` fixture before running the test with this exact second handler:

```ts
{
  id: "second-handler",
  type: "command",
  argv: ["echo", "second"],
}
```

- [ ] **Step 2: 验证测试失败。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement/draft.test.ts`

Expected: FAIL，提示 `moveHandler` 和 `replaceEvent` 尚未导出。

- [ ] **Step 3: 实现最小、不可变的 helper。**

在 `draft.ts` 中实现并导出：

```ts
export function moveHandler(
  config: HookConfigDraft,
  event: HookEventName,
  groupId: string,
  fromIndex: number,
  toIndex: number,
): HookConfigDraft;

export function replaceEvent(
  config: HookConfigDraft,
  event: HookEventName,
  groups: HookMatcherGroupDraft[],
): HookConfigDraft;
```

两者使用 `produce`。`moveHandler` 在索引越界、索引相同或找不到分组时原样返回 draft；只能移动给定分组内部的 `hooks`。`replaceEvent` 复制传入 groups，并写入 `events[event]`，以便模板不能和当前 draft 共享数组。

- [ ] **Step 4: 验证 draft 测试通过。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement/draft.test.ts`

Expected: PASS，原有和新增测试全部通过。

- [ ] **Step 5: 提交 draft 行为。**

```bash
git add console/src/pages/Control/HookManagement/draft.ts \
  console/src/pages/Control/HookManagement/draft.test.ts
git commit -m "feat(hooks): support event replacement and handler ordering"
```

## Task 3: 以失败测试定义事件总览和创建入口

**Files:**
- Create: `console/src/pages/Control/HookManagement/components/EventOverview.tsx`
- Modify: `console/src/pages/Control/HookManagement/index.test.tsx`

- [ ] **Step 1: 写出总览和模板入口的失败组件测试。**

```tsx
it("shows configured and empty events without rendering the configuration tree", async () => {
  render(<HookManagementPage />);

  expect(await screen.findByRole("heading", { name: "Hook 管理" })).toBeInTheDocument();
  expect(screen.getByText("PreToolUse")).toBeInTheDocument();
  expect(screen.getByText(/1 个分组 · 1 个处理器/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "开始配置 SessionStart" })).toBeInTheDocument();
  expect(screen.queryByText("事件与处理链")).not.toBeInTheDocument();
});

it("creates a scenario event from the new-event flow", async () => {
  render(<HookManagementPage />);
  fireEvent.click(await screen.findByRole("button", { name: "新建事件" }));
  fireEvent.click(screen.getByRole("button", { name: "从场景模板开始" }));
  fireEvent.click(screen.getByRole("button", { name: /工具调用审计/ }));

  expect(screen.getByRole("dialog", { name: /PostToolUse/ })).toBeInTheDocument();
  expect(screen.getByText(/工具调用审计/)).toBeInTheDocument();
});
```

- [ ] **Step 2: 运行组件测试并确认当前树形页面不满足新断言。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement/index.test.tsx`

Expected: FAIL，找不到“新建事件”，且仍存在“事件与处理链”。

- [ ] **Step 3: 实现 `EventOverview`。**

组件 props 必须为：

```ts
type EventOverviewProps = {
  config: HookConfigDraft;
  dirty: boolean;
  onEnabledChange: (enabled: boolean) => void;
  onEdit: (event: HookEventName) => void;
  onCreate: () => void;
};
```

按 `eventMetadata` 的 `order` 渲染全部七个事件。摘要使用当前事件的分组数和所有分组 `hooks.length` 的和，不能依赖处理器 ID。配置过的事件显示“编辑”；未配置的事件显示带事件名的“开始配置”按钮。全局开关位于总览头部；当 `dirty` 为 true 时显示“未保存更改”。

- [ ] **Step 4: 在 `index.tsx` 接入总览但暂不移除脚本库。**

删除 `selected: HookTreeSelection` 和旧侧树的渲染路径。新增 `editingEvent: HookEventName | null`、`createOpen`、`createMode` 状态。点击空事件先把空数组写入 `draft.events[event]` 再打开编辑抽屉；模板选择调用 `replaceEvent` 后打开对应事件。空事件按钮文本固定为 `开始配置 ${event}`。继续保留 `Tabs` 的“脚本库”和所有上传逻辑。

- [ ] **Step 5: 验证总览测试通过。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement/index.test.tsx`

Expected: PASS，新增总览测试与原有脚本库、冲突测试均通过。

- [ ] **Step 6: 提交总览入口。**

```bash
git add console/src/pages/Control/HookManagement/components/EventOverview.tsx \
  console/src/pages/Control/HookManagement/index.tsx \
  console/src/pages/Control/HookManagement/index.test.tsx
git commit -m "feat(hooks): add event overview and creation flow"
```

## Task 4: 构建事件编辑抽屉和处理器卡片

**Files:**
- Create: `console/src/pages/Control/HookManagement/components/EventEditorDrawer.tsx`
- Create: `console/src/pages/Control/HookManagement/components/HandlerList.tsx`
- Modify: `console/src/pages/Control/HookManagement/index.tsx`
- Modify: `console/src/pages/Control/HookManagement/index.test.tsx`

- [ ] **Step 1: 写出抽屉编辑、排序和高级匹配条件的失败测试。**

```tsx
it("edits one event in a drawer and keeps its internal group ID advanced", async () => {
  render(<HookManagementPage />);
  fireEvent.click(await screen.findByRole("button", { name: /PreToolUse.*编辑/ }));

  expect(screen.getByRole("dialog", { name: "编辑 PreToolUse" })).toBeInTheDocument();
  expect(screen.getByText("适用范围")).toBeInTheDocument();
  expect(screen.queryByLabelText("Matcher Group ID")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "高级匹配设置" }));
  expect(screen.getByLabelText("Matcher Group ID")).toBeVisible();
});

it("moves a Handler down while preserving its event and group", async () => {
  render(<HookManagementPage />);
  fireEvent.click(await screen.findByRole("button", { name: /PreToolUse.*编辑/ }));
  fireEvent.click(screen.getByRole("button", { name: /guard-shell.*下移/ }));

  fireEvent.click(screen.getByRole("button", { name: "保存并激活" }));
  await waitFor(() =>
    expect(mocks.saveConfiguration).toHaveBeenCalledWith(
      expect.objectContaining({
        events: expect.objectContaining({
          PreToolUse: [expect.objectContaining({ hooks: [
            expect.objectContaining({ id: "second-handler" }),
            expect.objectContaining({ id: "guard-shell" }),
          ] })],
        }),
      }),
      "rev-1",
    ),
  );
});
```

- [ ] **Step 2: 验证测试失败。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement/index.test.tsx`

Expected: FAIL，当前页面没有事件编辑抽屉和处理器移动按钮。

- [ ] **Step 3: 实现 `HandlerList`。**

每张卡片必须显示 handler ID、`command/http/prompt` 类型、一个安全摘要（命令显示首个 argv，HTTP 显示 URL，Prompt 显示前 80 字符）和失败策略。提供可访问的“上移”“下移”按钮，调用 `onMove(index, index ± 1)`；可选地使用现有 `@dnd-kit/sortable` 增强拖动，但按钮必须是完整的键盘替代方案。展开卡片后复用当前 Handler 编辑字段和既有 JSON 校验，保持 `command`、`http`、`prompt` 字段语义不变。

- [ ] **Step 4: 实现 `EventEditorDrawer`。**

使用 Ant Design `Drawer`，桌面宽度 `min(760px, 100vw)`，小于 760px 时 `width="100%"`，并设置 `aria-label={`编辑 ${event}`}`。固定抽屉头部显示事件名称、测试、删除事件、关闭和保存操作。正文依次显示：

1. “何时触发”及 `eventMetadata[event].description`；
2. “适用范围”，每个分组以“所有工具”或“仅 X、Y 工具”摘要显示；
3. “依序执行的处理器”，通过 `HandlerList` 编辑。

组的 ID 与原始 `matcher.tools` 只在“高级匹配设置” `Collapse` 中出现。删除事件要在调用 `removeEvent` 后关闭抽屉。新增分组、处理器仍使用现有 `addGroup`、`addHandler`，并保持 prompt handler 只允许现有 `promptEvents` 中的事件。

- [ ] **Step 5: 把现有真实测试确认 Modal 接到抽屉。**

`index.tsx` 继续持有 `testOpen`、`confirmed`、`testContext`、`testResult`、`testError` 和待测 handler。将 `runTest` 的输入改为显式参数，避免依赖已删除的 `selected`：

```ts
const runTest = async (
  event: HookEventName,
  handler: HookHandlerDraft,
) => {
  let context: Record<string, unknown>;
  try {
    context = JSON.parse(testContext) as Record<string, unknown>;
  } catch {
    setTestError("Hook Context 必须是有效 JSON");
    return;
  }
  const requiredContextFields = [
    "session_id", "transcript_path", "cwd", "tenant_id",
    "effective_tenant_id", "user_id", "agent_id", "channel",
  ];
  if (
    requiredContextFields.some((field) => typeof context[field] !== "string") ||
    context.hook_event_name !== event
  ) {
    setTestError("Hook Context 必须保留当前事件及所有必填 Envelope 字段");
    return;
  }
  setTestError(null);
  setTesting(true);
  try {
    const result = await hookManagementApi.manualTest(handler, context);
    setTestResult(result.redacted_summary);
  } catch (cause) {
    const errorMessage = cause instanceof Error ? cause.message : "人工测试失败";
    if ((cause as { status?: number }).status === 422) setTestError(errorMessage);
    else message.error(errorMessage);
  } finally {
    setTesting(false);
  }
};
```

抽屉的处理器卡片触发测试时，以该事件和该 handler 打开现有确认 Modal；确认文案和 `confirmRealExecution: true` API 请求不得改变。

- [ ] **Step 6: 验证抽屉和排序测试通过。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement/index.test.tsx`

Expected: PASS，新增抽屉/排序测试与现有人工测试、脚本上传、保存冲突测试全部通过。

- [ ] **Step 7: 提交抽屉编辑能力。**

```bash
git add console/src/pages/Control/HookManagement/components/EventEditorDrawer.tsx \
  console/src/pages/Control/HookManagement/components/HandlerList.tsx \
  console/src/pages/Control/HookManagement/index.tsx \
  console/src/pages/Control/HookManagement/index.test.tsx
git commit -m "feat(hooks): edit event flows in a drawer"
```

## Task 5: 完成视觉样式与回归验证

**Files:**
- Modify: `console/src/pages/Control/HookManagement/index.module.less`
- Modify: `console/src/pages/Control/HookManagement/index.test.tsx`

- [ ] **Step 1: 写出窄屏抽屉和未保存状态的失败测试。**

```tsx
it("marks an edited event as unsaved until configuration is saved", async () => {
  render(<HookManagementPage />);
  fireEvent.click(await screen.findByRole("button", { name: /PreToolUse.*编辑/ }));
  fireEvent.change(screen.getByLabelText("Handler ID"), {
    target: { value: "guard-shell-renamed" },
  });

  expect(screen.getByText("未保存更改")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "保存并激活" }));
  await waitFor(() => expect(mocks.saveConfiguration).toHaveBeenCalled());
});
```

- [ ] **Step 2: 验证测试失败。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement/index.test.tsx`

Expected: FAIL，当前实现尚未追踪与保存基线的差异。

- [ ] **Step 3: 实现视觉和 dirty-state 收尾。**

将旧 `.workspace`、`.tree`、`.group`、`.handler` 和 `.detail` 样式替换为事件列表、事件摘要、卡片、抽屉区块和处理器卡片样式。使用现有 `--console-management-*` 变量，避免引入页面专属颜色。`index.tsx` 在加载/成功保存后保存序列化基线，在 draft 改变后比较以显示 `dirty`；不要把复杂对象比较放入每个子组件。

窄屏媒体查询必须让总览单列排列，抽屉由组件宽度规则全屏显示，且脚本库原样可用。

- [ ] **Step 4: 运行 Hook 管理页完整测试。**

Run: `cd console && pnpm test:run src/pages/Control/HookManagement`

Expected: PASS，所有 draft、模板、页面和 API 模块相关测试通过。

- [ ] **Step 5: 运行类型检查和生产构建。**

Run: `cd console && pnpm build`

Expected: PASS，`tsc -b` 和 `vite build` 均以退出码 0 完成。

- [ ] **Step 6: 使用浏览器做人工回归。**

Run: `cd console && pnpm dev --host 127.0.0.1 --port 4173`

验证：事件总览不出现树；空白和模板创建都能打开抽屉；处理器排序后保存 payload 顺序正确；脚本库仍可上传；窄屏抽屉全屏；真实测试仍要求明确确认。

- [ ] **Step 7: 执行 GitNexus 和最终提交检查。**

在编辑 `HookManagementPage`、`EventOverview`、`EventEditorDrawer`、`HandlerList` 或 draft helper 前，分别运行 GitNexus `impact({ target, direction: "upstream" })` 并记录直接调用方、受影响流程和风险等级；若为 HIGH/CRITICAL，先向用户报告。提交前运行：

```text
detect_changes({ scope: "all", repo: "CoPaw" })
```

确认结果只覆盖 Hook 管理页及其测试、且无意外执行流后提交：

```bash
git add console/src/pages/Control/HookManagement
git commit -m "feat(hooks): redesign hook management workflow"
```

## Plan self-review

- **Spec coverage:** 事件总览（Task 3）、空白/完整场景模板（Task 1 和 Task 3）、抽屉编辑和可读分组（Task 4）、排序（Task 2 和 Task 4）、未保存与冲突保存（Task 3 和 Task 5）、当前处理器真实测试（Task 4）、窄屏和回归测试（Task 5）均有明确任务。
- **Completeness scan:** 每个实现步骤都列出了具体文件、测试及验证命令；不存在待补内容或泛化的测试说明。
- **Type consistency:** 模板使用 `HookEventName`、`HookMatcherGroupDraft`、`HookHandlerDraft`；`replaceEvent` 和 `moveHandler` 是唯一更新 draft 层级的新增 pure helper；抽屉测试 API 使用显式 `(event, handler)` 参数，避免依赖已移除的树选择状态。
