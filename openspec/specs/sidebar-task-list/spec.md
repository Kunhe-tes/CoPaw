# sidebar-task-list Specification

## Purpose
Define the task and paginated chat-history sections shown in the chat sidebar, including their navigation and interaction behavior.

## Requirements

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
The sidebar SHALL display a "历史记录" section with a collapsible normally rendered list below the task section. The Console SHALL initially request a bounded first page of chat history, SHALL append older pages when the user scrolls near the end of the loaded history, SHALL automatically continue when the loaded rows do not fill the scroll container, and SHALL NOT require the previous virtual-list implementation. The section count SHALL reflect the server-reported total while including newer local pending sessions. Each history item SHALL display a title (color #4F5060) and a timestamp (color #808191) in "YYYY-MM-DD HH:mm" format. Paginated list loading SHALL preserve existing chat navigation, message display, session identity, generating state, and chat operation behavior.

#### Scenario: History section displays the first page
- **WHEN** the sidebar becomes visible and historical chats exist
- **THEN** the Console requests and displays the first bounded page in newest-first order
- **AND** each visible item shows its title and formatted timestamp

#### Scenario: User scrolls to older history
- **WHEN** the current page reports that older chats remain and the user scrolls near the bottom of the loaded history
- **THEN** the Console requests the next page exactly once while that request is in flight
- **AND** appends unseen older chat rows after the already loaded rows
- **AND** preserves the user's current chat and existing scroll context

#### Scenario: First page does not fill the history container
- **WHEN** older chats remain but the loaded history is too short to create a scrollbar
- **THEN** the Console automatically requests another page until the container can scroll or no older chats remain

#### Scenario: Session state changes while an older page is loading
- **WHEN** a session is created, switched, or changes generating state while an older history page is in flight
- **THEN** the resolved page is merged with the latest session state instead of replacing those concurrent changes

#### Scenario: All history has been loaded
- **WHEN** the latest paginated response reports that no older chats remain
- **THEN** further bottom scrolling does not request another page

#### Scenario: Loading another page fails
- **WHEN** a request for an older history page fails
- **THEN** already loaded history remains visible and usable
- **AND** the user can retry loading the failed page
- **AND** ordinary scroll events do not repeatedly retry the failed request

#### Scenario: Collapsed history panel reaches the bottom
- **WHEN** the sidebar is collapsed, the history panel is open, and the user scrolls its history content near the bottom
- **THEN** the Console uses the same paginated state to request the next page exactly once
- **AND** it does not issue an unpaginated chat-list request

#### Scenario: History item click
- **WHEN** the user clicks a loaded history item
- **THEN** the corresponding chat session is loaded using the existing session navigation behavior
- **AND** its messages are displayed using the unchanged chat detail flow

#### Scenario: Direct URL targets a chat outside the first page
- **WHEN** the chat page opens with a valid chat ID that is not present in the currently loaded history pages
- **THEN** the Console loads that chat directly instead of creating an empty replacement session
- **AND** subsequent messages preserve the chat's existing logical `session_id`

#### Scenario: Pending chat resolves while history is paginated
- **WHEN** a temporary local chat resolves to a persisted chat ID while one or more history pages are loaded
- **THEN** the sidebar contains one logical row for that conversation
- **AND** chat navigation and follow-up submission use the same identities as before pagination

#### Scenario: Existing chat mutations update the paginated list
- **WHEN** a loaded chat is renamed or deleted
- **THEN** the visible history state reflects that operation without duplicating unrelated rows
- **AND** existing delete navigation and active-chat behavior remain unchanged
