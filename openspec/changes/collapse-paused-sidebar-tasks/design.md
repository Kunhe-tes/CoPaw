## Context

The chat task surfaces currently render all cron tasks as peers in `ChatTaskList` and in the collapsed-sidebar `ExpandablePanel`. `getTaskSidebarMeta()` already normalizes every task into `active`, `running`, `auto-paused`, or `manual-paused`, so the UI can group tasks without changing API data or duplicating pause rules.

Paused cards currently use a warm tinted background and remain fully expanded. When several tasks are paused, those cards consume most of the sidebar and visually compete with tasks that will run normally. The design needs progressive disclosure while preserving paused-task visibility and recovery actions.

The Console uses React, Ant Design, `antd-style`, existing design tokens, and local SVG icons. Both task surfaces must stay behaviorally aligned.

## Goals / Non-Goals

**Goals:**
- Make active and running tasks the primary, immediately visible task list.
- Put all manually and automatically paused tasks in a collapsed secondary group by default.
- Preserve task order within both groups and preserve all existing task metadata and actions.
- Use a compact, accessible disclosure control that works in the expanded sidebar and collapsed-sidebar popover.
- Keep the visual treatment consistent with the existing neutral blue/gray Console design.

**Non-Goals:**
- Changing cronjob APIs or the definition of paused states.
- Automatically resuming, deleting, or otherwise mutating paused tasks.
- Persisting disclosure state across reloads or between the two sidebar modes.
- Changing task execution, unread, navigation, or selection semantics.
- Redesigning the task detail page or the global navigation sidebar.

## Decisions

### 1. Partition by normalized sidebar state

**Decision:** Each task surface derives `runnableTasks` and `pausedTasks` from `getTaskSidebarMeta(task)`. `active` and `running` belong to the runnable group; `manual-paused` and `auto-paused` belong to the paused group.

**Rationale:** The helper already encodes API edge cases such as `pause_reason`, so both UIs stay consistent with action availability and status copy.

**Alternative considered:** Filter directly on `task.is_paused`. Rejected because it can diverge from the existing `pause_reason` fallback and auto-pause classification.

### 2. Preserve total count and original relative order

**Decision:** "我的任务(N)" continues to show the total task count. The disclosure row separately shows "已暂停任务 M". Filtering preserves the incoming array order inside each group.

**Rationale:** The total count tells users that tasks still exist even while some rows are hidden. Stable relative order avoids an unrelated sorting change.

**Alternative considered:** Change the header count to runnable tasks only. Rejected because it makes collapsed paused tasks appear to have disappeared.

### 3. Use a bottom disclosure row, collapsed by default

**Decision:** Render the paused disclosure after runnable cards only when at least one paused task exists. Each task surface owns local disclosure state initialized as collapsed, except when the currently selected task is paused; in that case the group initializes or transitions to expanded so the selected task remains visible.

Collapsed state:

```text
我的任务(4)                         v
  早报
  下次运行：06-12 09:00

  ark
  下次运行：06-13 09:00

  >  已暂停任务 2
```

Expanded state:

```text
  v  已暂停任务 2
     仅在需要时查看或恢复
  ┌ 每日业绩简报                  ... ┐
  │ 已自动暂停 · 连续 3 次未读        │
  │ 06-06 09:01  已完成               │
  └───────────────────────────────────┘
  ┌ ark                           ... ┐
  │ 已手动暂停                        │
  └───────────────────────────────────┘
```

**Rationale:** A bottom group follows the user's scan path: actionable tasks first, archived-like state second. Default collapse reduces clutter without removing access.

**Alternative considered:** Add a top-level "只看运行中" filter. Rejected because a filter requires more state, makes paused tasks less discoverable, and is heavier than the requested disclosure behavior.

### 4. Neutral group styling with restrained paused styling

**Decision:** The collapsed disclosure is a 36px neutral row with muted text, a paused-task count, and a chevron. It deliberately does not display an unread badge, unread dot, or aggregate unread text. Hover uses the existing subtle blue surface; focus uses the existing visible blue focus ring. Expanded paused cards retain their individual unread badges and status text with a very light warm tint, but the group wrapper has no large orange panel or border.

Suggested visual tokens:
- Disclosure text: existing secondary text token; count uses muted text.
- Disclosure content: "已暂停任务 M" only; unread information remains on individual task cards after expansion.
- Disclosure hover: `rgba(55, 105, 252, 0.04)`.
- Paused group separator: optional 1px neutral border with 8px top margin.
- Auto-paused status: existing `#A15C07`; manual pause: muted text token.
- Chevron transition: 160-200ms ease; disabled under `prefers-reduced-motion: reduce`.

**Rationale:** Paused state remains recognizable after expansion but no longer dominates the default sidebar.

**Alternative considered:** Keep an amber background on the disclosure row. Rejected because it continues to signal warning-level urgency for hidden, non-running work.

### 5. Reuse one rendering contract across both task surfaces

**Decision:** Extract shared partition logic into a small pure helper, and either extract a shared paused disclosure component or mirror the same markup/state contract in `ChatTaskList` and `ExpandablePanel` if their card class systems make extraction noisier. Existing card rendering and `TaskActionMenu` remain intact.

**Rationale:** The wide and narrow sidebar presentations use different style namespaces but must classify and expose paused tasks identically. A pure helper is easy to test without forcing a broad component refactor.

**Alternative considered:** Change only `ChatTaskList`. Rejected because collapsed sidebar users would still see the cluttered presentation.

### 6. Accessible disclosure behavior

**Decision:** Implement the disclosure as a native `button` with `aria-expanded` and `aria-controls`. Enter and Space work natively, focus is visible, and the controlled region has a stable ID. The main "我的任务" section collapse remains independent.

**Rationale:** The interaction is a standard disclosure, and native semantics avoid custom keyboard handling gaps in the current clickable `div` pattern.

**Alternative considered:** Use a clickable `div` matching existing headers. Rejected because the new control can improve accessibility without altering task card semantics.

### 7. Handle live task state changes predictably

**Decision:** Recompute groups on every task update. If the last paused task resumes, remove the disclosure row. If an unselected task becomes paused while the group is collapsed, place it into the hidden group and update the count without auto-expanding. If `selectedTaskId` identifies a paused task, automatically expand the paused group and keep it expanded while that task remains selected. This rule applies to both `ChatTaskList` and the collapsed-sidebar `ExpandablePanel`, which must receive the selected task ID from `ChatSidebar`.

**Rationale:** Ordinary polling updates should not create layout jumps, but hiding the task currently being viewed removes essential location feedback. Selection-triggered expansion is therefore the only automatic expansion case.

**Alternative considered:** Auto-expand whenever any task enters paused state. Rejected because background updates could repeatedly disrupt the list; automatic expansion is limited to the selected paused task.

## Risks / Trade-offs

- **[Paused tasks become too easy to overlook]** -> Keep the paused count visible in the disclosure row and preserve the total count in the section header; unread aggregation is intentionally omitted by product decision.
- **[Wide and collapsed sidebar implementations drift]** -> Share state classification and add equivalent interaction tests for both components.
- **[Nested collapse controls become confusing]** -> Keep the main section toggle visually in the header and the paused disclosure indented with distinct copy and spacing.
- **[Task updates cause surprising movement]** -> Preserve source order within each group and auto-expand only when required to reveal the selected paused task.
- **[Long expanded paused groups still consume space]** -> Allow normal container scrolling; avoid introducing a second nested scrollbar in this change.
- **[Motion or keyboard accessibility regressions]** -> Use a native button, visible `:focus-visible`, ARIA disclosure attributes, and reduced-motion CSS.

## Migration Plan

1. Add and test the shared task partition helper.
2. Update `ChatTaskList` with the paused disclosure and styles.
3. Update `ExpandablePanel` task content with the same behavior and styles.
4. Run focused component tests, type checking, and the Console build.
5. Roll back by reverting the UI grouping; no data migration or backend rollback is needed.

## Open Questions

None. Disclosure state is intentionally local and non-persistent for the first implementation.
