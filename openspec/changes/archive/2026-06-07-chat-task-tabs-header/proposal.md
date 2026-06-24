## Why

The current "我的任务" area consumes vertical space in the chat sidebar and competes with history records, while the task context is most useful near the active chat header. This change moves task navigation into header-level tabs so users can switch between tasks without losing the existing task status, unread, and action controls.

## What Changes

- Replace the expanded sidebar's full task list with a compact clickable "我的任务" entry block that summarizes task count and important states.
- Add a horizontally scrollable task tab strip in the chat header area after the user opens the task entry block.
- Render one tab per task, with selected, running, paused, unread, and empty states represented in the tab UI.
- Preserve existing task click behavior: selecting a task tab opens the same target chat/session as the previous sidebar task item behavior.
- Preserve existing task operations: stop, run now, resume, and delete remain available through the existing task action menu.
- Keep history records and the collapsed chat sidebar toolbar behavior usable.
- Do not change cronjob APIs, task polling, task read marking, task execution, or chat session navigation semantics.

## Capabilities

### New Capabilities
- `chat-task-tabs`: Header-level task tab navigation for the chat page, including task state display, unread badge display, overflow handling, and task actions.

### Modified Capabilities
- `sidebar-task-list`: The expanded chat sidebar changes from rendering the full task list inline to rendering a compact task entry block that opens the header task tabs.

## Impact

- `console/src/pages/Chat/index.tsx` - pass task data and handlers into the header-level task tabs and manage task tabs visibility.
- `console/src/pages/Chat/components/ChatSidebar/` - replace expanded-sidebar task list rendering with a compact task entry block while keeping history and collapsed toolbar behavior.
- `console/src/pages/Chat/components/ChatTaskList/` - either refactor into reusable task display primitives or retire expanded-sidebar-only list usage.
- `console/src/pages/Chat/components/TaskActionMenu.tsx` - reuse existing actions from the new task tab UI.
- `console/src/pages/Chat/taskJobs.ts` - reuse existing task state helpers and open-target resolution.
- Tests for task display and actions should move or expand to cover the new task tab component.
