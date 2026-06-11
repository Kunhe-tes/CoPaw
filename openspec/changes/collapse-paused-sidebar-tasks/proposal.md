## Why

Paused scheduled tasks currently occupy the same visual level as tasks that can run normally, so the sidebar is dominated by items that require no immediate attention and active tasks are harder to scan. The task list should prioritize runnable work while keeping paused tasks discoverable and recoverable.

## What Changes

- Split the sidebar task collection into runnable tasks and paused tasks using the existing task state metadata.
- Keep runnable and currently running tasks directly visible in their existing order.
- Move manually and automatically paused tasks into a dedicated "已暂停任务(N)" disclosure group at the bottom of the task list, collapsed by default.
- Allow users to expand the paused group to inspect paused tasks and use the existing open, resume, and delete actions.
- Preserve the total count in "我的任务(N)" while showing the paused count separately on the disclosure row.
- Keep the collapsed paused-task disclosure intentionally minimal: it shows only the paused-task label and count, without unread badges or aggregate unread text.
- Automatically expand the paused-task group when the task currently being viewed belongs to that group, so the selected task remains visible in the sidebar.
- Apply the same grouping behavior to both the expanded chat sidebar and the collapsed-sidebar task popover.
- Add accessible disclosure semantics, keyboard operation, visible focus styling, and reduced-motion behavior.
- Keep cronjob APIs, pause/resume semantics, unread tracking, task navigation, and task ordering unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `sidebar-task-list`: Change task presentation so paused tasks are hidden in a collapsed secondary group by default while runnable tasks remain immediately visible and all paused-task operations remain available after expansion.

## Impact

- Affected Console components: `ChatTaskList`, the collapsed-sidebar `ExpandablePanel` task content, and their styles and tests.
- Existing helpers in `console/src/pages/Chat/taskJobs.ts` remain the source of task state classification.
- No backend, API schema, persistence, routing, or dependency changes are required.
