# Chat History Pull-to-Load Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace automatic top-of-timeline history loading with a threshold-triggered pull gesture that gives progress feedback and preserves the visible conversation after archived messages are prepended.

**Architecture:** Keep cursor pagination, archive conversion, generation guards, and deduplication in `MessageList`. Add a small gesture hook that only owns Pointer/Touch drag state, resistance, threshold release, and in-progress locking. Preserve a logical top-origin scroll anchor across the prepend; map it back to native `scrollTop` so the existing reverse-direction bubble list remains stable.

**Tech Stack:** React 18, TypeScript, Vitest, Testing Library, Ant Design, existing AgentScope Bubble List.

---

### Task 1: Specify and test the top-overscroll state machine

**Files:**
- Create: `console/src/components/agentscope-chat/hooks/useTopOverscroll.ts`
- Create: `console/src/components/agentscope-chat/hooks/useTopOverscroll.test.tsx`

- [ ] **Step 1: Write failing tests for resistance and release behavior.**

```tsx
it("arms only after the resisted pull reaches 72px", () => {
  expect(toVisualPullOffset(100)).toBe(45);
  expect(toVisualPullOffset(160)).toBe(72);
});

it("calls onTriggered once after an armed pointer release", async () => {
  render(<Harness onTriggered={onTriggered} />);
  dragFromTop({ startY: 100, endY: 260 });
  await waitFor(() => expect(onTriggered).toHaveBeenCalledTimes(1));
});
```

- [ ] **Step 2: Run the tests to verify the missing hook fails.**

Run: `pnpm test:run src/components/agentscope-chat/hooks/useTopOverscroll.test.tsx`

Expected: failure because `useTopOverscroll` and `toVisualPullOffset` do not exist.

- [ ] **Step 3: Implement the minimal, reusable gesture hook.**

Expose a `containerRef`, `onTriggered`, `disabled`, and `onStateChange` contract. Capture only primary pointers that begin while the container is at its visual top. Use these fixed interaction constants:

```ts
export const TOP_PULL_THRESHOLD = 72;
export const TOP_PULL_MAX_OFFSET = 120;
export const TOP_PULL_RESISTANCE = 0.45;

export const toVisualPullOffset = (rawPull: number) =>
  Math.min(TOP_PULL_MAX_OFFSET, Math.max(0, rawPull) * TOP_PULL_RESISTANCE);
```

Handle pointer move, up, cancel, and lost capture. The hook emits `idle`, `pulling`, `ready`, and `loading`; it never owns API pagination or user-facing Chinese labels.

- [ ] **Step 4: Run the focused hook tests.**

Run: `pnpm test:run src/components/agentscope-chat/hooks/useTopOverscroll.test.tsx`

Expected: PASS.

### Task 2: Integrate pull feedback and stable history prepending

**Files:**
- Modify: `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/MessageList/index.tsx`
- Modify: `console/src/components/agentscope-chat/Bubble/BubbleList.tsx`
- Modify: `console/src/components/agentscope-chat/Bubble/style/list.ts`
- Create: `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/MessageList/index.test.tsx`

- [ ] **Step 1: Write failing MessageList integration tests.**

```tsx
it("does not request history before the pull threshold", async () => {
  render(<MessageListHarness />);
  dragMessageList({ startY: 100, endY: 220 });
  expect(chatApi.getChatHistory).not.toHaveBeenCalled();
});

it("prepends the cursor page without moving the visible anchor", async () => {
  setScrollMetrics({ top: -180, height: 1_000, clientHeight: 400 });
  mockHistoryPage({ messages: olderMessages, has_more: true, next_cursor: "c-2" });
  render(<MessageListHarness />);
  dragMessageList({ startY: 100, endY: 280 });
  await waitFor(() => expect(screen.getByText("older message")).toBeVisible());
  expect(readLogicalTopOffset()).toBe(420);
});
```

- [ ] **Step 2: Run the test to verify it fails.**

Run: `pnpm test:run src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/MessageList/index.test.tsx`

Expected: failure because the current `onReachStart` path requests immediately and exposes no pull state.

- [ ] **Step 3: Implement presentation, request locking, and anchoring.**

Replace `onReachStart` with `useTopOverscroll`. Render an absolute, non-layout-shifting indicator above the timeline:

| Gesture state | Text |
| --- | --- |
| `pulling` | `加载更早历史` |
| `ready` | `松开加载更早历史` |
| `loading` | `正在加载更早历史` |

Give the indicator `role="status"` and `aria-live="polite"`; progress is represented by its visible offset and a numeric-valued progress element. While `loading`, retain the existing `historyLoadingRef` lock and session-generation guard.

Before `setMessages`, capture `H0`, native `scrollTop`, client height, and list direction. After commit, restore a logical top-origin anchor:

```ts
const oldLogicalTop = isReverse
  ? oldScrollTop + oldScrollHeight - clientHeight
  : oldScrollTop;
const nextLogicalTop = oldLogicalTop + (newScrollHeight - oldScrollHeight);
const nextScrollTop = isReverse
  ? nextLogicalTop - newScrollHeight + clientHeight
  : nextLogicalTop;
```

For the current reverse list this algebra intentionally yields the prior native `scrollTop`; it preserves the old visible content while history is added at the visual top. Add a one-update `preserveScrollPosition` Bubble List prop so its auto-scroll-to-bottom effect does not overwrite the recovered anchor.

- [ ] **Step 4: Run the integration tests.**

Run: `pnpm test:run src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/MessageList/index.test.tsx src/pages/Chat/sessionApi/index.test.ts`

Expected: PASS.

### Task 3: Update compaction copy and run regressions

**Files:**
- Modify: `console/src/pages/Chat/components/ConversationCompactionBoundary.tsx`
- Modify: `console/src/pages/Chat/components/ConversationCompactionBoundary.test.tsx`

- [ ] **Step 1: Write the failing copy assertion.**

```tsx
expect(screen.getByText("会话已压缩 · 上滚查看历史内容")).toBeVisible();
expect(screen.queryByText(/条消息已归档/)).not.toBeInTheDocument();
```

- [ ] **Step 2: Run the focused test to verify failure.**

Run: `pnpm test:run src/pages/Chat/components/ConversationCompactionBoundary.test.tsx`

Expected: failure because the current divider includes `archived_message_count`.

- [ ] **Step 3: Make the divider copy-only.**

Keep the neutral two-rule presentation and separator semantics. Remove the now-unused archive-count data dependency from the card component while retaining compatibility with card renderer props.

- [ ] **Step 4: Run full relevant verification and commit.**

Run:

```bash
pnpm test:run src/components/agentscope-chat/hooks/useTopOverscroll.test.tsx src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/MessageList/index.test.tsx src/pages/Chat/components/ConversationCompactionBoundary.test.tsx src/pages/Chat/sessionApi/index.test.ts
pnpm build:test
```

Before committing, run GitNexus `detect_changes({ scope: "staged" })`. Stage only the plan and the files above; preserve unrelated worktree changes.
