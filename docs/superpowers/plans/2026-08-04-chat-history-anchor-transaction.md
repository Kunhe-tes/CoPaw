# Chat History Anchor Transaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the reader's exact visible message position when cursor-paginated archived history is inserted above a reverse-ordered chat timeline.

**Architecture:** One archive-page insertion becomes an anchor transaction: capture a visible bubble immediately before state changes, insert the page, restore its container-local offset before paint, then verify once on the next frame. The transaction records the active session and history generation so stale work cannot adjust another timeline.

**Tech Stack:** React 18, TypeScript, Vitest, Testing Library, Bubble.List.

---

### Task 1: Anchor transaction

**Files:**

- Modify: `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/MessageList/index.tsx`
- Modify: `console/src/components/agentscope-chat/Bubble/hooks/scrollAnchor.ts`
- Test: `console/src/components/agentscope-chat/Bubble/hooks/scrollAnchor.test.ts`

- [ ] Write a failing test for `oldScrollTop: -240`, `previousOffset: 96`, and `nextOffset: 124`, expecting `-212`.
- [ ] Run `pnpm test:run src/components/agentscope-chat/Bubble/hooks/scrollAnchor.test.ts` and observe the intended red state.
- [ ] Capture session/generation/anchor before `setMessages`; resolve only from the list container in a layout effect; verify and correct once in `requestAnimationFrame`.
- [ ] Re-run the focused anchor and MessageList tests.

### Task 2: Real DOM regression seam

**Files:**

- Modify: `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/MessageList/index.contentOnly.test.tsx`
- Modify: `console/src/components/agentscope-chat/Bubble/BubbleList.tsx`
- Modify: `console/src/components/agentscope-chat/Bubble/style/list.ts`

- [ ] Write a failing test that resolves an archive page and requires the tracked visible bubble to remain within one pixel of its prior offset.
- [ ] Expose only the existing scroll container and bubble IDs needed by the test; do not add product debug UI.
- [ ] Disable browser-native scroll anchoring only for the reverse conversation list, so application anchor restoration is the single authority.
- [ ] Run all chat pagination regression tests.

### Task 3: Verification and commit

**Files:** the scoped files above plus this plan.

- [ ] Run focused tests, ESLint on changed sources, `pnpm build:test`, and `git diff --check`.
- [ ] Re-run the seeded conversation in a real browser and compare anchor coordinates for two cursor pages.
- [ ] Run GitNexus `detect_changes` before staging and after staging; stage only scoped files.
- [ ] Commit with `fix(chat): anchor paged history viewport`.
