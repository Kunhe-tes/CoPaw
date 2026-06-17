## MODIFIED Requirements

### Requirement: Pagination SHALL NOT change chat detail and mutation behavior
Adding chat-list pagination SHALL NOT change the contracts or behavior of chat detail, create, update, delete, stop, reconnect, or streaming operations. The Console MUST NOT treat absence from the currently loaded chat-list page as proof that a requested chat cannot be opened.

#### Scenario: Load messages for a chat outside the loaded page
- **WHEN** a valid chat ID is not present in the currently requested list page and its detail endpoint is requested
- **THEN** the endpoint returns that chat's existing message history, status, and chat metadata without requiring an unpaginated list request

#### Scenario: Existing chat operations after paginated listing
- **WHEN** a client has obtained chats through a paginated list and then renames, deletes, stops, reconnects, or continues one of those chats
- **THEN** the corresponding existing operation retains its previous behavior and identity semantics

#### Scenario: Direct chat URL recovers detail outside loaded pages
- **WHEN** the Console opens `/chat/{chat_id}` and `{chat_id}` is absent from the currently loaded chat-list page
- **THEN** the Console MUST request that chat through the chat detail API
- **AND** the recovered chat metadata and messages MUST render as the selected conversation
- **AND** the Console MUST NOT require loading additional chat-list pages before opening it

#### Scenario: Task chat target recovers detail outside loaded pages
- **WHEN** a task opens a valid `task.chat_id` that is absent from the currently loaded chat-list page
- **THEN** the Console MUST navigate to `/chat/{task.chat_id}`
- **AND** the Console MUST request that chat through the chat detail API
- **AND** the recovered task conversation MUST render without depending on a loaded-list match

#### Scenario: Recovered detail merges without disturbing pagination state
- **WHEN** the Console recovers a valid chat through the detail API because it is absent from the loaded chat-list page
- **THEN** the Console MUST merge the recovered chat into local session state for selection, title, and identity matching
- **AND** it MUST NOT refresh page 1, reset pagination cursors, or duplicate the chat when a later page contains the same identity

#### Scenario: Pending session URL resolution does not reload the active conversation
- **WHEN** a newly created local pending session receives its backend `chat_id` and the Console replaces the URL with `/chat/{chat_id}`
- **THEN** the Console MUST preserve the active runtime session and visible messages for that conversation
- **AND** it MUST NOT clear the message list or show a full session reload solely because the URL now contains the backend `chat_id`
