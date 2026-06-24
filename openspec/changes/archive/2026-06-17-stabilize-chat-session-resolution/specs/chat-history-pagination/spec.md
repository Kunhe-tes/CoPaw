## MODIFIED Requirements

### Requirement: Pagination SHALL NOT change chat detail and mutation behavior
Adding chat-list pagination SHALL NOT change the contracts or behavior of chat detail, create, update, delete, stop, reconnect, or streaming operations. Console URL/session initialization SHALL allow a valid `/chat/:id` route to activate through the existing chat detail loading path even when the matching chat is not present in the currently loaded history page, and SHALL NOT replace an active local pending session while a newly created chat is resolving from its local timestamp id to a backend chat id.

#### Scenario: Load messages for a chat outside the loaded page
- **WHEN** a valid chat ID is not present in the currently requested list page and its detail endpoint is requested
- **THEN** the endpoint returns that chat's existing message history, status, and chat metadata without requiring an unpaginated list request

#### Scenario: Activate a route for a chat outside the loaded page
- **WHEN** the Console route is `/chat/:id`
- **AND** the matching chat is not present in the currently loaded history page
- **AND** the currently active session is not a local pending timestamp session
- **THEN** the Console sets the runtime current session id to the route id
- **AND** the existing session loader loads the chat detail by id
- **AND** the history list is not mutated with an ad hoc fetched session object during URL initialization

#### Scenario: Preserve pending local session during backend id resolution
- **WHEN** a newly created local chat is active with a local timestamp session id
- **AND** the route changes to a backend chat id as the first response is persisted
- **THEN** URL/session initialization does not replace the active local pending session
- **AND** the in-progress conversation remains available for follow-up messages

#### Scenario: Existing chat operations after paginated listing
- **WHEN** a client has obtained chats through a paginated list and then renames, deletes, stops, reconnects, or continues one of those chats
- **THEN** the corresponding existing operation retains its previous behavior and identity semantics
