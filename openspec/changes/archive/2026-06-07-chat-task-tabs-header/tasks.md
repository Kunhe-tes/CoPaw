## 1. Shared Task UI Primitives

- [x] 1.1 Identify reusable rendering logic from `ChatTaskList` and `ExpandablePanel` for task title, unread badge, state class names, next-run text, and completed status text.
- [x] 1.2 Extract or duplicate only the minimal shared task display helpers needed by the new header tabs without changing task API behavior.
- [x] 1.3 Confirm `TaskActionMenu` can be reused from tab controls with event propagation stopped.

## 2. Sidebar Task Entry

- [x] 2.1 Replace the expanded sidebar inline `ChatTaskList` usage with a compact clickable "我的任务" entry block.
- [x] 2.2 Add aggregate sidebar entry metadata for total task count, unread count, running count, and paused count.
- [x] 2.3 Wire sidebar entry click to toggle header task tabs visibility without triggering task navigation or execution.
- [x] 2.4 Keep history records, guide footer, sidebar collapse toggle, and collapsed toolbar behavior unchanged.

## 3. Header Task Tabs

- [x] 3.1 Create a `ChatTaskTabs` component that renders one tab per visible task in a single-line horizontal strip.
- [x] 3.2 Render selected, unread, running, manual-paused, and auto-paused visual states using existing task metadata helpers.
- [x] 3.3 Preserve task tab click navigation by calling the existing `onTaskClick` handler.
- [x] 3.4 Add per-tab `TaskActionMenu` support for stop, run, resume, and delete without triggering tab navigation.
- [x] 3.5 Show compact secondary metadata such as completed status or next-run text through inline, tooltip, or hover detail UI.
- [x] 3.6 Handle empty task state when tabs are open and no visible tasks exist.

## 4. Chat Header Integration

- [x] 4.1 Add task tab visibility state in `Chat/index.tsx` near existing task state and handlers.
- [x] 4.2 Insert `ChatTaskTabs` into `theme.rightHeader` between `ChatHeaderTitle` and existing right-side controls.
- [x] 4.3 Ensure generated files and model selector remain reachable and visually stable when tabs overflow.
- [x] 4.4 Ensure the header height remains stable and does not cause chat message overlap.

## 5. Styling and Accessibility

- [x] 5.1 Add styles for the compact sidebar task entry using the existing chat design tokens and restrained flat UI treatment.
- [x] 5.2 Add styles for task tabs, selected state, paused/running state, unread badges, hover states, focus states, and horizontal overflow.
- [x] 5.3 Add accessible labels and button semantics for the sidebar task entry, task tabs, and tab action triggers.
- [x] 5.4 Verify keyboard tab order follows the visual order of sidebar entry, task tabs, task actions, generated files, and model selector.

## 6. Tests and Verification

- [x] 6.1 Add or update tests for compact sidebar task entry count and click-to-toggle behavior.
- [x] 6.2 Add tests for task tab selected, unread, paused, running, and empty states.
- [x] 6.3 Add tests proving task action menu clicks do not trigger task tab navigation.
- [x] 6.4 Run the relevant chat component tests.
- [x] 6.5 Run a browser check for expanded sidebar, open task tabs, overflow behavior, and collapsed sidebar regression.
