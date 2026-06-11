## 1. Shared Task Grouping

- [x] 1.1 Add a pure helper that partitions tasks into runnable and paused groups using `getTaskSidebarMeta` while preserving input order.
- [x] 1.2 Add unit tests covering active, running, manual-paused, auto-paused, mixed, and empty task collections.

## 2. Expanded Sidebar Task List

- [x] 2.1 Update `ChatTaskList` to render runnable tasks directly and a paused-task disclosure only when paused tasks exist.
- [x] 2.2 Implement collapsed-by-default disclosure state that automatically expands while `selectedTaskId` belongs to a paused task, together with accessible `button`, `aria-expanded`, and `aria-controls` semantics.
- [x] 2.3 Add neutral disclosure, expanded paused-card, focus-visible, dark-mode, and reduced-motion styles; keep the collapsed disclosure free of unread badges or aggregate unread text.
- [x] 2.4 Extend `ChatTaskList` tests for default collapse, count labels, omitted unread aggregation, selected-paused auto-expansion, expand/collapse, paused actions, live group changes, and no-paused/empty states.

## 3. Collapsed Sidebar Task Panel

- [x] 3.1 Pass `selectedTaskId` from `ChatSidebar` into the task `ExpandablePanel` and apply the same runnable-first, selected-paused auto-expansion, and paused-disclosure rendering.
- [x] 3.2 Add matching disclosure and expanded paused-card styles within the expandable panel namespace.
- [x] 3.3 Extend `ExpandablePanel` tests for default collapse, omitted unread aggregation, selected-paused auto-expansion, keyboard operation, counts, paused actions, and dynamic state changes.

## 4. Verification

- [x] 4.1 Run focused Vitest suites for task helpers, `ChatTaskList`, and `ExpandablePanel`.
- [x] 4.2 Run Console TypeScript checking, linting for touched files, and a production build.
- [x] 4.3 Verify in the browser at expanded and collapsed sidebar widths, including hover, focus, dark mode, long task names, many paused tasks, and reduced-motion behavior.
