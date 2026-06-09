## ADDED Requirements

### Requirement: Task list section in sidebar
When the current chat URL includes `origin=Y` and `window.__env__.enableOriginYTaskTabs` is enabled, the expanded chat sidebar SHALL display a compact "我的任务" entry block instead of an inline expandable task list. The entry block SHALL show the title "我的任务", the task count, and a concise summary of important task states such as unread, running, or paused counts. Clicking the entry block SHALL toggle the chat header task tab strip. When either condition is not met, the expanded chat sidebar SHALL preserve the original inline expandable task list.

#### Scenario: Task entry display
- **WHEN** the current chat URL includes `origin=Y`
- **AND** `window.__env__.enableOriginYTaskTabs` is enabled
- **AND** the expanded chat sidebar is visible
- **THEN** the sidebar displays a compact "我的任务" entry block with the visible task count

#### Scenario: Standard task list when conditions are not met
- **WHEN** the current chat URL does not include `origin=Y`
- **OR** `window.__env__.enableOriginYTaskTabs` is not enabled
- **AND** the expanded chat sidebar is visible
- **THEN** the sidebar displays the original inline task list section and does not replace it with the compact task entry block

#### Scenario: Open header task tabs
- **WHEN** the current chat URL includes `origin=Y`
- **AND** `window.__env__.enableOriginYTaskTabs` is enabled
- **AND** the user clicks the "我的任务" entry block
- **THEN** the chat header task tab strip is shown or hidden without navigating away from the current chat

#### Scenario: Empty task list
- **WHEN** no tasks are configured
- **THEN** the "我的任务" entry block is displayed with a zero count and an empty or neutral summary state

### Requirement: Task item display
Detailed per-task display SHALL move from the expanded sidebar list into the chat header task tab strip. The expanded sidebar task entry SHALL retain task count and aggregate state information, while each header task tab SHALL preserve per-task title, unread badge, selected state, paused/running state, and available task actions.

#### Scenario: Task metadata moved to tabs
- **WHEN** tasks exist and the header task tab strip is visible
- **THEN** each visible task is represented by a task tab that displays its title and state indicators

#### Scenario: Sidebar aggregate unread display
- **WHEN** one or more visible tasks have unread updates
- **THEN** the compact sidebar task entry displays an aggregate unread indication without rendering the full task list inline

#### Scenario: Sidebar aggregate paused or running display
- **WHEN** one or more visible tasks are paused or running
- **THEN** the compact sidebar task entry summarizes those states without rendering separate task rows

### Requirement: Click task to trigger execution
Clicking an individual task from the task tab strip SHALL preserve the existing task click behavior for the corresponding task, including resolving and opening the task chat/session target. Running a task immediately SHALL remain available through the task action menu, not through the compact sidebar entry click.

#### Scenario: Click task tab
- **WHEN** the user clicks an individual task tab
- **THEN** the corresponding task target is opened using the existing task navigation behavior

#### Scenario: Run task action
- **WHEN** the user chooses the run action from a task tab action menu
- **THEN** the corresponding cronjob run action is invoked through the existing task action handler

#### Scenario: Sidebar entry click does not run a task
- **WHEN** the user clicks the compact "我的任务" sidebar entry block
- **THEN** the task tab strip is toggled and no individual task execution is triggered

### Requirement: History section in sidebar
The sidebar SHALL display a "历史记录" section with a collapsible list below the task section. Each history item SHALL display a title (color #4F5060) and a timestamp (color #808191) in "YYYY-MM-DD HH:mm" format.

#### Scenario: History section display
- **WHEN** the sidebar is visible and history items exist
- **THEN** the "历史记录(N)" section shows history items with title and formatted timestamp

#### Scenario: History item click
- **WHEN** the user clicks a history item
- **THEN** the corresponding chat session is loaded (existing session navigation behavior)
