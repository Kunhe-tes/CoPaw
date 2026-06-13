## Context

The chat page currently renders "我的任务" as an inline list inside the expanded chat sidebar via `ChatTaskList`. The list already has mature task behavior: it uses `taskJobs.ts` helpers for visible tasks, selected task detection, task state, unread count, next-run text, and open-target resolution; it also reuses `TaskActionMenu` for stop, run, resume, and delete actions.

The chat header is provided through `AgentScopeRuntimeWebUI`'s `theme.rightHeader`. It already contains `ChatHeaderTitle`, generated files, and model selection. The header height is fixed at 54px and message-list spacing assumes that height, so task tabs must fit within the existing header without increasing layout height.

## Goals / Non-Goals

**Goals:**
- Replace the expanded sidebar task list with a compact "我的任务" entry block.
- Show task tabs in the chat header when the task entry is opened.
- Preserve all existing task state display and task operations.
- Preserve task click/navigation behavior and current task selection.
- Keep the existing collapsed toolbar task panel and history list usable.
- Keep the change UI-only; no backend/API behavior changes.

**Non-Goals:**
- Changing cronjob APIs or task response schemas.
- Changing task execution, pause, resume, delete, or read-marking semantics.
- Changing history record behavior.
- Reworking the global app sidebar.
- Adding mobile-specific navigation patterns beyond graceful overflow within the current layout.

## Decisions

### 1. Header Tabs Controlled by Chat Page State

**Decision:** Manage task tab visibility in `Chat/index.tsx`, near the existing `tasks`, `currentTask`, and task action handlers.

**Rationale:** The chat page already owns task fetching, polling, selected task derivation, and all task handlers. Keeping visibility state there lets the new header component receive the same data and callbacks without introducing a separate store.

**Alternative considered:** Store tab visibility inside `ChatSidebar`. Rejected because the tabs render in the chat header, not inside the sidebar, and cross-component imperative coordination would be more fragile.

### 2. Compact Sidebar Entry Instead of Inline List

**Decision:** Replace expanded-sidebar `ChatTaskList` usage with a compact entry block that shows title, total count, and a concise state summary. Clicking the entry toggles the header task tabs.

**Rationale:** This keeps the left sidebar lightweight while preserving a discoverable task affordance. It also avoids duplicating a full task list in both sidebar and header.

**Alternative considered:** Keep the full sidebar task list and add header tabs. Rejected because it duplicates navigation surfaces and does not solve the sidebar crowding problem.

### 3. Reuse Existing Task Semantics

**Decision:** Reuse `getTaskSidebarMeta`, `getTaskNextRunText`, `getTaskOpenTarget`, `shouldMarkTaskReadOnOpen`, and `TaskActionMenu`.

**Rationale:** The request is explicitly UI/style-only. Reusing these helpers ensures running, paused, unread, selected, and action availability behavior remains aligned with the existing sidebar list.

**Alternative considered:** Build a separate tab-specific task state model. Rejected because it would increase the chance of task-state drift.

### 4. Single-Line Horizontal Tab Strip

**Decision:** Render task tabs as a single-line horizontal strip constrained between the chat title and right-side header controls. Overflow scrolls horizontally and does not wrap or increase header height.

**Rationale:** The chat layout reserves 54px for the header. A single-line strip prevents message content overlap and keeps model selection reachable.

**Alternative considered:** Multi-row tabs or a dropdown-only task selector. Multi-row tabs would break header height assumptions; dropdown-only navigation would hide the "one tab per task" requirement.

### 5. Actions Live Inside Each Tab

**Decision:** Place the existing overflow action menu in each task tab, while stopping propagation so action clicks do not open the task.

**Rationale:** This keeps operations attached to the task they affect and matches the existing sidebar behavior where menu clicks do not trigger task navigation.

**Alternative considered:** Put actions in a separate details popover. Rejected for the initial change because it adds another interaction layer without improving the core tab workflow.

## Risks / Trade-offs

- **[Header crowding]** -> Constrain the tab strip with `min-width: 0`, horizontal overflow, and max tab widths; keep generated files and model selector fixed on the right.
- **[Many tasks]** -> Use horizontal scrolling and keyboard-focusable tabs; optionally add subtle edge fades if needed during implementation.
- **[Action click opens task accidentally]** -> Preserve event `stopPropagation` behavior from `TaskActionMenu` and cover it with tests.
- **[Collapsed toolbar divergence]** -> Leave the existing collapsed toolbar task panel behavior intact during this change; only the expanded sidebar presentation changes.
- **[Visual state loss]** -> Map all existing sidebar task states into tab variants: selected, running, manual paused, auto paused, unread.
- **[Accessibility regression]** -> Use button semantics for the sidebar entry and tabs, visible focus states, `aria-selected` for active tabs, and predictable tab order.
