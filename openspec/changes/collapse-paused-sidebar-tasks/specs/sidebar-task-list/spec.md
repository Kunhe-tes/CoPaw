## MODIFIED Requirements

### Requirement: Task list section in sidebar
The sidebar SHALL display a "我的任务" section with a collapsible task list. The section header SHALL show the title "我的任务(N)" where N is the total task count, along with a collapse/expand toggle icon. Task items SHALL be fetched from the cronjob API. Active and running tasks SHALL be displayed directly, while manually and automatically paused tasks SHALL be placed in a separate "已暂停任务(M)" disclosure group after the directly visible tasks, where M is the paused task count. The paused-task group SHALL be collapsed by default unless it contains the currently selected task, and SHALL be independently expandable from the main task section. The same grouping behavior SHALL be available in both the expanded chat sidebar and the collapsed-sidebar task panel. The collapsed paused-task disclosure SHALL NOT display unread badges, unread dots, or aggregate unread text.

#### Scenario: Runnable tasks are prioritized
- **WHEN** the sidebar is visible and active or running tasks exist
- **THEN** those tasks are displayed directly in their existing relative order
- **AND** they appear before the paused-task disclosure group

#### Scenario: Paused tasks are collapsed by default
- **WHEN** one or more manually or automatically paused tasks exist
- **THEN** the sidebar displays a collapsed "已暂停任务(M)" disclosure after the directly visible tasks
- **AND** paused task cards are not displayed until the disclosure is expanded

#### Scenario: Expand paused tasks
- **WHEN** the user activates the paused-task disclosure
- **THEN** the disclosure reports its expanded state
- **AND** all paused task cards are displayed in their existing relative order

#### Scenario: Collapse paused tasks
- **WHEN** the paused-task disclosure is expanded and the user activates it again
- **THEN** the paused task cards are hidden
- **AND** the paused task count remains visible

#### Scenario: Total and paused counts remain understandable
- **WHEN** the task list contains both runnable and paused tasks
- **THEN** "我的任务(N)" displays the total number of tasks
- **AND** "已暂停任务(M)" displays the number of paused tasks

#### Scenario: Collapsed disclosure omits unread aggregation
- **WHEN** the paused-task disclosure is collapsed and one or more paused tasks have unread updates
- **THEN** the disclosure displays only the paused-task label, paused-task count, and disclosure icon
- **AND** it does not display an unread badge, unread dot, or aggregate unread text

#### Scenario: Selected paused task remains visible
- **WHEN** the currently selected task belongs to the paused-task group
- **THEN** the paused-task disclosure automatically expands in the active task-list surface
- **AND** the selected paused task is visible with its selected state

#### Scenario: Unselected task becomes paused
- **WHEN** an unselected task moves into the paused-task group during a task refresh
- **THEN** the paused count updates
- **AND** a user-collapsed paused-task disclosure remains collapsed

#### Scenario: No paused tasks
- **WHEN** no tasks are manually or automatically paused
- **THEN** the paused-task disclosure is not displayed

#### Scenario: Empty task list
- **WHEN** no tasks are configured
- **THEN** the "我的任务(0)" section is displayed with no paused-task disclosure and no task cards or with an empty state message

#### Scenario: Keyboard-operated disclosure
- **WHEN** keyboard focus reaches the paused-task disclosure
- **THEN** Enter or Space toggles the paused-task region
- **AND** visible focus and the current expanded state are exposed to assistive technology

### Requirement: Task item display
Each directly visible or expanded task item SHALL preserve its title, unread badge, selected state, paused/running state, latest completion metadata, next-run text, and available task actions in the sidebar list. Paused items SHALL preserve the distinction between manual and automatic pause states after the paused-task disclosure is expanded. Collapsing paused tasks SHALL only change their visibility and SHALL NOT clear unread state, selection, metadata, or available actions.

#### Scenario: Task with unread badge
- **WHEN** a directly visible task or an expanded paused task has unread updates
- **THEN** a red badge with the unread count is displayed with the task item

#### Scenario: Task state display
- **WHEN** a task is running, manually paused, or automatically paused and its card is visible
- **THEN** the corresponding state is displayed on that task item

#### Scenario: Task schedule metadata
- **WHEN** a visible task has next-run or latest completion metadata
- **THEN** that metadata remains available from the task item

#### Scenario: Paused task actions remain available
- **WHEN** the user expands the paused-task disclosure
- **THEN** each paused task retains its existing open, resume, delete, and other permitted task actions

#### Scenario: Task state changes while the list is open
- **WHEN** a task changes between runnable and paused state after the list has rendered
- **THEN** it moves to the corresponding group without changing the relative order of the other tasks
- **AND** the paused count and disclosure visibility update to match the latest data
