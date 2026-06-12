## ADDED Requirements

### Requirement: Chat list pagination SHALL be optional and backward compatible
The existing chat-list endpoint SHALL accept `page` and `page_size` as optional paired query parameters. A request that omits both parameters SHALL preserve the existing top-level array response and existing unpaginated ordering. A request that supplies both parameters SHALL return a paginated response containing `items`, `total`, `page`, `page_size`, and `has_more`.

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

### Requirement: Paginated chats SHALL use stable newest-first ordering
Paginated chat-list requests SHALL apply existing filters first, then order matching chats by `updated_at` descending and `id` descending before slicing the requested page. Runtime status lookup SHALL be performed only for chats included in the requested page.

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

### Requirement: Pagination SHALL NOT change chat detail and mutation behavior
Adding chat-list pagination SHALL NOT change the contracts or behavior of chat detail, create, update, delete, stop, reconnect, or streaming operations.

#### Scenario: Load messages for a chat outside the loaded page
- **WHEN** a valid chat ID is not present in the currently requested list page and its detail endpoint is requested
- **THEN** the endpoint returns that chat's existing message history and status using the unchanged detail contract

#### Scenario: Existing chat operations after paginated listing
- **WHEN** a client has obtained chats through a paginated list and then renames, deletes, stops, reconnects, or continues one of those chats
- **THEN** the corresponding existing operation retains its previous behavior and identity semantics
