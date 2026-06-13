## MODIFIED Requirements

### Requirement: History section in sidebar
The sidebar SHALL display a "历史记录" section with a collapsible normally rendered list below the task section. The Console SHALL initially request a bounded first page of chat history, SHALL append older pages when the user scrolls near the end of the loaded history, and SHALL NOT require the previous virtual-list implementation. Each history item SHALL display a title (color #4F5060) and a timestamp (color #808191) in "YYYY-MM-DD HH:mm" format. Paginated list loading SHALL preserve existing chat navigation, message display, session identity, and chat operation behavior.

#### Scenario: History section displays the first page
- **WHEN** the sidebar becomes visible and historical chats exist
- **THEN** the Console requests and displays the first bounded page in newest-first order
- **AND** each visible item shows its title and formatted timestamp

#### Scenario: User scrolls to older history
- **WHEN** the current page reports that older chats remain and the user scrolls near the bottom of the loaded history
- **THEN** the Console requests the next page exactly once while that request is in flight
- **AND** appends unseen older chat rows after the already loaded rows
- **AND** preserves the user's current chat and existing scroll context

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
