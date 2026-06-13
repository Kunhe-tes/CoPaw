## Why

The chat page currently loads every persisted chat mapping in one request, so workspaces with hundreds or thousands of historical sessions pay increasing backend status-lookup, response-size, frontend processing, and rendering costs on initial load and refresh. The history list should load a bounded recent page first and fetch older sessions on demand without changing existing clients or disrupting chat selection, message display, streaming, stop, reconnect, rename, or delete behavior.

## What Changes

- Add optional pagination parameters to the existing chat-list endpoint while preserving the current unpaginated array response when those parameters are omitted.
- Define deterministic newest-first ordering and pagination metadata for paginated chat-list requests.
- Update the Console chat session adapter to load the first history page and append older pages on demand without duplicating or losing locally pending/resolved sessions.
- Replace the sidebar history virtual-list implementation with a paginated normal list and an explicit/infinite load-more interaction suitable for bounded page sizes.
- Preserve existing chat detail loading and all record operations, including session identity resolution, message rendering, streaming, reconnect, stop, rename, and deletion.
- Add backend and frontend regression coverage for compatibility, pagination boundaries, ordering, list merging, and existing chat behavior.

## Capabilities

### New Capabilities
- `chat-history-pagination`: Optional, backward-compatible pagination for chat-list reads, including ordering, metadata, validation, and page traversal semantics.

### Modified Capabilities
- `sidebar-task-list`: Change the history section from an all-record virtualized list to paginated incremental loading while preserving existing item presentation and navigation behavior.

## Impact

- Backend chat list models, router, manager/repository query path, and tests under `src/swe/app/runner` and `tests`.
- Console chat API types, session adapter, shared session state synchronization, sidebar history rendering/styles, and related Vitest coverage.
- Existing `GET /chats` and agent-scoped equivalents remain compatible for callers that do not send pagination parameters; chat detail and mutation endpoint contracts remain unchanged.
- The current JSON repository may still scan its file to compute a page, but pagination bounds status lookups, serialized payload size, network transfer, frontend transformation, and DOM work. A database/index migration is outside this change.
