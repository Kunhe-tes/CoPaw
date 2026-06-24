# chat-history-pagination Specification

## Purpose
Define backward-compatible chat-list pagination and stable ordering while preserving all existing chat detail and mutation behavior.

## Requirements

### Requirement: Chat list pagination SHALL be optional and backward compatible
The existing chat-list endpoint SHALL accept `page` and `page_size` as optional paired query parameters. It SHALL additionally accept `cursor` with `page_size` for stable continuation. A request that omits all pagination parameters SHALL preserve the existing top-level array response and existing unpaginated ordering. A paginated response SHALL contain `items`, `total`, `page`, `page_size`, `has_more`, and an optional `next_cursor`.

#### Scenario: Existing caller omits pagination
- **WHEN** a caller requests the chat list without `page` and `page_size`
- **THEN** the endpoint returns the same top-level chat array shape used before pagination support
- **AND** existing `user_id` and `channel` filtering semantics remain unchanged

#### Scenario: Caller requests a page
- **WHEN** a caller requests the chat list with valid `page` and `page_size` values
- **THEN** the endpoint returns only the chats in that page under `items`
- **AND** it returns the matching `total`, requested `page`, requested `page_size`, and correct `has_more` value

#### Scenario: Caller supplies only one pagination parameter
- **WHEN** a caller supplies `page` without `page_size` or `page_size` without `page`
- **THEN** the endpoint rejects the request as invalid

#### Scenario: Caller supplies an invalid pagination value
- **WHEN** a caller supplies a page below 1, a page size below 1, or a page size above the server maximum
- **THEN** the endpoint rejects the request as invalid

#### Scenario: Caller requests stable cursor pagination
- **WHEN** a caller supplies `page_size` and the initial empty cursor or a returned `next_cursor`
- **THEN** the endpoint returns a bounded page and the cursor for the next stable page when more chats remain
- **AND** existing page-number callers remain supported without changing their request or response shape

### Requirement: Paginated chats SHALL use stable newest-first ordering
Paginated chat-list requests SHALL apply existing filters first, then order matching chats by `updated_at` descending and `id` descending before slicing the requested page. Runtime status lookup SHALL be performed only for chats included in the requested page.

Cursor-based requests SHALL use immutable `created_at` descending and `id` descending ordering so answer generation, title updates, and other `updated_at` changes cannot shift unseen chats across continuation boundaries.

#### Scenario: First page contains most recently updated chats
- **WHEN** matching chats have different `updated_at` values and page 1 is requested
- **THEN** the returned items are the most recently updated matching chats in descending order

#### Scenario: Equal update timestamps have deterministic order
- **WHEN** two matching chats have equal `updated_at` values
- **THEN** their relative paginated order is determined by descending chat `id`

#### Scenario: Filters are applied before pagination
- **WHEN** a paginated request includes `user_id` or `channel`
- **THEN** `total` counts only chats matching those filters
- **AND** page boundaries are calculated only from matching chats

#### Scenario: Requested page is beyond the result set
- **WHEN** a valid page starts after the last matching chat
- **THEN** `items` is empty
- **AND** `total`, `page`, and `page_size` remain accurate
- **AND** `has_more` is false

#### Scenario: A loaded chat is updated between cursor pages
- **WHEN** the caller has received a cursor page and a chat's `updated_at` changes before the next cursor request
- **THEN** the next page continues from the immutable creation boundary without omitting an unseen chat

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
