## ADDED Requirements

### Requirement: Header task tabs display
The chat page SHALL display a header-level task tab strip when the user opens the "我的任务" sidebar entry. The tab strip SHALL render one tab for each visible task and SHALL fit inside the existing chat header without increasing header height.

#### Scenario: Open task tabs from sidebar entry
- **WHEN** the user clicks the compact "我的任务" entry in the expanded chat sidebar
- **THEN** the chat header displays the task tab strip with one tab per visible task

#### Scenario: Preserve header height
- **WHEN** the task tab strip is visible
- **THEN** the chat header remains within its existing header height and does not overlap chat messages or right-side header controls

#### Scenario: Empty task tabs
- **WHEN** the user opens the task tab strip and there are no visible tasks
- **THEN** the header task area displays an empty state or remains empty without breaking the chat header layout

### Requirement: Task tab state and metadata
Each task tab SHALL display the task title and SHALL preserve task state indicators from the current task list, including selected, running, auto-paused, manual-paused, and unread states. The tab strip SHALL preserve access to secondary metadata such as latest completed status and next-run text without requiring the sidebar list.

#### Scenario: Selected task tab
- **WHEN** the current chat corresponds to a visible task
- **THEN** that task tab is visually marked as selected

#### Scenario: Unread task tab
- **WHEN** a task has an unread execution count greater than zero
- **THEN** its task tab displays a red unread badge with the unread count capped consistently with the existing task list

#### Scenario: Paused task tab
- **WHEN** a task is manually paused or auto-paused
- **THEN** its task tab displays a paused state indicator that distinguishes paused tasks from active tasks

#### Scenario: Running task tab
- **WHEN** a task is running
- **THEN** its task tab displays a running state indicator and does not expose unavailable task actions

#### Scenario: Secondary task metadata
- **WHEN** a task has next-run text or latest scheduled completion metadata
- **THEN** the task tab UI exposes that metadata through compact inline text, tooltip, or hover detail without expanding the sidebar list

### Requirement: Task tab interaction
Clicking a task tab SHALL open the same chat/session target as clicking the corresponding task item in the previous sidebar list. Clicking a task action menu item SHALL execute that action without also opening the task.

#### Scenario: Click task tab
- **WHEN** the user clicks a task tab
- **THEN** the app opens the task target resolved from the existing task open-target logic

#### Scenario: Click current task tab
- **WHEN** the user clicks the tab for the already active task chat
- **THEN** the app keeps the current chat active without changing task semantics

#### Scenario: Click task action menu
- **WHEN** the user opens a task tab action menu and selects stop, run, resume, or delete
- **THEN** the existing task action handler runs for that task and the tab click navigation is not triggered

### Requirement: Task tab overflow and accessibility
The task tab strip SHALL remain usable when there are more tasks than horizontal header space allows. Task tabs SHALL be reachable through keyboard navigation and SHALL expose clear labels for assistive technologies.

#### Scenario: Overflow tasks
- **WHEN** the visible task tabs exceed the available header width
- **THEN** the task tab strip scrolls horizontally or otherwise exposes all task tabs without wrapping to a second row

#### Scenario: Keyboard access
- **WHEN** the user navigates through the chat header with a keyboard
- **THEN** the sidebar task entry, task tabs, and task action triggers are reachable in visual order with visible focus states

#### Scenario: Assistive labels
- **WHEN** a screen reader inspects a task tab or task action trigger
- **THEN** the control exposes a meaningful label containing the task name or action purpose
