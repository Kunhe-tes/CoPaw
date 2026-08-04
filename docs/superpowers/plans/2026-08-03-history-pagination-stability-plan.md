# Chat History Pagination Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the history timeline stable while allowing a completed archive snapshot to be refreshed when new compactions arrive.

**Architecture:** `MessageList` will distinguish a cursor being exhausted from an immutable conversation start. It will render terminal feedback only after a request finds no new records, and invalidates that snapshot on compaction. A message-element anchor, rather than a total-height delta, will restore the reader's visible message after older cards are inserted into the reverse-ordered timeline.

**Tech Stack:** React, TypeScript, Vitest, Testing Library.

---

### Task 1: Define snapshot-terminal feedback

**Files:**
- Modify: `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/MessageList/index.tsx`
- Test: `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/MessageList/index.contentOnly.test.tsx`

- [x] Write a failing test where a final page contributes an archived message and assert that the status returns to idle instead of displaying `已到达会话开始处`.
- [x] Write a failing test where a final page contributes no unseen messages and assert that the terminal status is displayed.
- [x] Treat the existing exhausted state as a snapshot terminal state: enter it only for an empty terminal result; existing compaction events reset it and a successful page with records returns to idle.
- [x] Run `pnpm test:run src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/MessageList/index.contentOnly.test.tsx` and confirm the tests pass.

### Task 2: Preserve a visible message anchor

**Files:**
- Modify: `console/src/components/agentscope-chat/Bubble/hooks/scrollAnchor.ts`
- Test: `console/src/components/agentscope-chat/Bubble/hooks/scrollAnchor.test.ts`
- Modify: `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/MessageList/index.tsx`

- [x] Write a failing helper test for converting a before/after element offset into a reverse-list scroll correction.
- [x] Add a pure helper for restoring an element-relative scroll anchor.
- [x] Capture the first visible bubble before history cards are inserted and restore it in a layout effect after cards are inserted; when no bubble is visible, do not apply a fragile height-based correction.
- [x] Run the anchor and message-list tests and confirm that the visible anchor offset is unchanged.

### Task 3: Validate and commit the focused change

**Files:**
- Modify: files from Tasks 1–2 only

- [x] Run all chat-history, bubble-list, divider, and session API tests.
- [x] Run `pnpm build:test` and `git diff --check`.
- [x] Run GitNexus `detect_changes(scope="unstaged")`, stage only history-pagination files and this plan, then commit with `fix(chat): stabilize history pagination`.
