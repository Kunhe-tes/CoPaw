# Context Reference Mention Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the five `@` mention regressions while preserving discovery, grouping, keyboard navigation, and structured submissions.

**Architecture:** Keep trigger lifecycle inside `useSkillMentions`: only a valid trailing `@` range can open or query the menu, and selection clears that range before later editor input arrives. Keep menu presentation in `SkillMentionMenu`, which renders a geometry-stable loading state and a dedicated empty-state component. `SkillTokenEditor` continues to pass editor text/caret information unchanged.

**Tech Stack:** React 18, TypeScript, Ant Design, Vitest, Testing Library.

---

### Task 1: Lock the mention trigger lifecycle with regression tests

**Files:**
- Modify: `console/src/components/agentscope-chat/SkillMentions/index.test.tsx`
- Modify: `console/src/components/agentscope-chat/SkillMentions/SkillTokenEditor.test.tsx`

- [ ] **Step 1: Write the failing tests**

Add a hook-harness test that selects `docs / search`, then changes the value to
`"请用 @docs/search 后续文本"`; it must assert that `onOpen` is not called a
second time and the listbox is absent. Add an editor test that renders a token
and asserts its type marker has an accessible name such as `"MCP 工具"` rather
than the current 5px circular marker that visually reads as `.@docs/search`.

```tsx
fireEvent.click(screen.getByRole("option", { name: /docs \/ search/ }));
fireEvent.change(input, { target: { value: "请用 @docs/search 后续文本" } });
expect(onOpen).toHaveBeenCalledTimes(1);
expect(screen.queryByRole("listbox")).toBeNull();
expect(screen.getByLabelText("MCP 工具")).toBeInTheDocument();
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pnpm test:run src/components/agentscope-chat/SkillMentions/index.test.tsx src/components/agentscope-chat/SkillMentions/SkillTokenEditor.test.tsx`

Expected: FAIL because selection leaves the query trigger active or produces
the unexpected punctuation.

- [ ] **Step 3: Commit the failing-test checkpoint only if independently useful**

Do not commit a knowingly red worktree. Continue directly to the minimal hook
repair so the production branch remains green.

### Task 2: Clear trigger state after selection and use recognisable token icons

**Files:**
- Modify: `console/src/components/agentscope-chat/SkillMentions/useSkillMentions.ts:45-150`
- Modify: `console/src/components/agentscope-chat/SkillMentions/SkillTokenEditor.tsx:145-190`

- [ ] **Step 1: Add a trigger reset helper**

Add a local callback that clears `mentionRangeRef`, resets `query` to `""`, and
resets `activeIndex` to `0`. Call it when selection succeeds before closing the
menu. Keep `getMentionRange` as the only place that identifies a new trigger.

```ts
const clearMentionTrigger = useCallback(() => {
  mentionRangeRef.current = null;
  setQuery("");
  setActiveIndex(0);
}, []);
```

- [ ] **Step 2: Replace the dot marker with a type icon and retain exact range replacement**

In `replaceEditorContents`, replace the 5px coloured circle with a compact,
non-text glyph (bolt for skills, command for MCP, file glyph for files) and
give it an `aria-label` matching the type. Construct the replacement as the
prefix before `range.start`, one token, one space only when the following text
is not whitespace, and the original suffix. Do not derive a range from DOM
token punctuation or append a punctuation character.

```ts
const prefix = value.slice(0, range.start);
const suffix = value.slice(range.end);
const separator = /^\s/.test(suffix) ? "" : " ";
onValueChange(`${prefix}${contextReferenceText(item)}${separator}${suffix}`);
```

- [ ] **Step 3: Run the focused tests and verify they pass**

Run: `pnpm test:run src/components/agentscope-chat/SkillMentions/index.test.tsx src/components/agentscope-chat/SkillMentions/SkillTokenEditor.test.tsx`

Expected: PASS; the new tests prove that post-selection input is ordinary text
until another `@` is typed.

- [ ] **Step 4: Commit the hook repair**

```bash
git add console/src/components/agentscope-chat/SkillMentions/useSkillMentions.ts \
  console/src/components/agentscope-chat/SkillMentions/SkillTokenEditor.tsx \
  console/src/components/agentscope-chat/SkillMentions/index.test.tsx \
  console/src/components/agentscope-chat/SkillMentions/SkillTokenEditor.test.tsx
git commit -m "fix(chat): reset context mention after selection"
```

### Task 3: Stabilise the menu layout and empty state

**Files:**
- Modify: `console/src/components/agentscope-chat/SkillMentions/index.tsx:55-220`
- Modify: `console/src/components/agentscope-chat/SkillMentions/index.test.tsx`

- [ ] **Step 1: Write failing menu tests**

Assert every option has a full-width left-aligned content wrapper, title and
description styles include `whiteSpace: "nowrap"`, `overflow: "hidden"`, and
`textOverflow: "ellipsis"`. Render `loading` with populated items and assert
the listbox and an option remain mounted. Render an empty query result and
assert the new `"未找到匹配的上下文引用"` status and search icon label exist.

```tsx
expect(screen.getByRole("option", { name: /docs \/ search/ })).toHaveStyle({
  justifyContent: "flex-start",
});
expect(screen.getByRole("status", { name: "未找到匹配的上下文引用" }))
  .toBeInTheDocument();
```

- [ ] **Step 2: Run the menu test and verify it fails**

Run: `pnpm test:run src/components/agentscope-chat/SkillMentions/index.test.tsx`

Expected: FAIL because loading replaces all rows and the empty treatment has no
dedicated labelled visual structure.

- [ ] **Step 3: Implement the compact presentation**

Set each Ant Design button to `justifyContent: "flex-start"`; make the text
column `flex: "1 1 auto"` so it begins at the same icon-adjacent baseline and
may truncate. Keep grouped rows mounted during loading, apply a subdued loading
overlay/status, and replace the raw empty span with a centered `Flex` containing
`SearchOutlined`, title, and short helper text. Keep no tooltip and horizontal
overflow hidden.

- [ ] **Step 4: Run the menu test and verify it passes**

Run: `pnpm test:run src/components/agentscope-chat/SkillMentions/index.test.tsx`

Expected: PASS; the listbox remains stable while loading and the empty state is
semantically labelled and visibly structured.

- [ ] **Step 5: Commit the visual repair**

```bash
git add console/src/components/agentscope-chat/SkillMentions/index.tsx \
  console/src/components/agentscope-chat/SkillMentions/index.test.tsx
git commit -m "fix(chat): stabilise context mention menu"
```

### Task 4: Verify and review the repair

**Files:**
- Verify: `console/src/components/agentscope-chat/SkillMentions/index.test.tsx`
- Verify: `console/src/components/agentscope-chat/SkillMentions/SkillTokenEditor.test.tsx`
- Verify: `console/src/pages/Chat/welcomeSkillMentions.test.ts`

- [ ] **Step 1: Run the complete focused front-end suite**

Run: `pnpm test:run src/components/agentscope-chat/SkillMentions/index.test.tsx src/components/agentscope-chat/SkillMentions/SkillTokenEditor.test.tsx src/pages/Chat/welcomeSkillMentions.test.ts src/components/agentscope-chat/Sender/index.test.tsx src/components/agentscope-chat/WelcomeCenterLayout/index.test.tsx`

Expected: PASS with no failed test files.

- [ ] **Step 2: Run formatting and backend regression checks**

Run: `pnpm exec prettier --check src/components/agentscope-chat/SkillMentions/index.tsx src/components/agentscope-chat/SkillMentions/useSkillMentions.ts src/components/agentscope-chat/SkillMentions/index.test.tsx src/components/agentscope-chat/SkillMentions/SkillTokenEditor.test.tsx && ../../../venv/bin/python -m pytest ../tests/unit/app/test_context_references.py ../tests/unit/app/test_runner_context_references.py -q`

Expected: Prettier succeeds and Python reports all selected tests passed.

- [ ] **Step 3: Inspect changed execution scope before committing**

Run GitNexus `detect_changes` for this worktree. Review the changed file list
and risk assessment; stop for a HIGH or CRITICAL result.

- [ ] **Step 4: Commit verification-only adjustments if any**

```bash
git add console/src/components/agentscope-chat/SkillMentions/useSkillMentions.ts \
  console/src/components/agentscope-chat/SkillMentions/SkillTokenEditor.tsx \
  console/src/components/agentscope-chat/SkillMentions/index.tsx \
  console/src/components/agentscope-chat/SkillMentions/index.test.tsx \
  console/src/components/agentscope-chat/SkillMentions/SkillTokenEditor.test.tsx
git commit -m "test(chat): cover context mention regressions"
```
