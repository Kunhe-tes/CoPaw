## Context

`GET /chats` currently returns every `ChatSpec` for the active workspace. The JSON repository loads the full `chats.json`, the API resolves runtime status for every returned record, and the Console converts the entire response before a virtualized sidebar renders it. This keeps the DOM bounded but does not bound backend work, payload size, network transfer, or frontend transformation.

The endpoint is also used by older Console code, CLI commands, agent-scoped routes, and other internal callers that expect a top-level array. The frontend session adapter additionally coordinates temporary local session IDs, persisted chat IDs, logical `session_id` values, active streams, task sessions, and direct URL recovery. Pagination must not weaken those identity guarantees.

## Goals / Non-Goals

**Goals:**

- Add optional page-number pagination to the existing chat-list route without changing calls that omit pagination parameters.
- Return newest chats first for paginated requests with stable ordering and sufficient metadata to traverse pages.
- Restrict per-chat runtime status lookup and serialization to the requested page.
- Make the Console initially load a bounded history page and request older pages when the user scrolls to the end of the loaded history.
- Remove the sidebar history virtualizer and render the bounded incrementally loaded list normally.
- Preserve direct chat opening, message history display, session identity, streaming, stop, reconnect, rename, delete, and pending-session resolution behavior.

**Non-Goals:**

- Migrating `chats.json` to SQLite, MySQL, or another indexed store.
- Adding message-level pagination to `GET /chats/{chat_id}`.
- Changing chat creation, update, delete, stop, reconnect, or streaming response contracts.
- Changing task-session retention rules or the semantics of `user_id` and `channel` filters.

## Decisions

### 1. Pagination is opt-in on the existing endpoint

`GET /chats` accepts optional `page` and `page_size` query parameters. They must be supplied together; `page >= 1`, `page_size >= 1`, and `page_size` has a server maximum.

- Without both parameters, the handler preserves the existing top-level array response and existing ordering.
- With both parameters, the handler returns an object containing `items`, `total`, `page`, `page_size`, and `has_more`.

This conditional contract avoids breaking existing callers while giving new callers explicit metadata. A new endpoint was considered, but extending the existing list route better matches the requested API surface and keeps agent-scoped routing consistent.

### 2. Paginated requests use deterministic newest-first ordering

After existing `user_id` and `channel` filters are applied, paginated results are sorted by `updated_at` descending and then `id` descending as a deterministic tie-breaker. Pagination occurs after filtering and sorting. Only page items receive runtime status annotation.

The unpaginated compatibility path is intentionally left unchanged, including its current storage order. This prevents subtle regressions in external callers that may depend on the old array order.

### 3. Repository and manager expose pagination as a structured operation

Pagination logic should live below the router in a manager/repository result abstraction so the API does not duplicate filtering, sorting, total counting, and slicing rules. The initial JSON implementation may load and sort the file in memory, but it returns only the requested page to upper layers. This creates a replaceable boundary for a future indexed repository.

Offset/page pagination is selected over cursors because the UI needs simple sequential page traversal and the backing JSON file has no indexed cursor. Concurrent chat updates may move records between pages; frontend identity-based deduplication prevents duplicate rows, and a first-page refresh re-establishes current ordering.

### 4. Console owns paginated history state separately from message detail state

The API module gains a typed paginated list call while retaining the current array list call. The session adapter tracks current page, `has_more`, and loaded persisted chat identities. Initial refresh replaces persisted page data with page 1 while preserving pending local sessions and resolved temporary-session mappings. Loading another page appends only unseen persisted chats.

Direct `GET /chats/{chat_id}` remains authoritative for message history. If the current URL references a chat that is not present in the loaded list page, the frontend still loads its detail directly and creates/retains enough session metadata for normal display and follow-up submission. Pagination must never turn a valid deep link into a new empty session.

### 5. Sidebar uses normal paginated rendering with scroll-to-end loading

The history sidebar removes `useVirtualizer`, its absolute-positioned spacer, and virtual row positioning. It renders the loaded sessions as normal rows and observes the actual history scroll container. When the user scrolls within a small threshold of the bottom and `has_more` is true, the Console requests the next page. The trigger is single-flight, appends the next page, preserves scroll position naturally, and exposes loading and retry states. A failed request disables automatic retriggering until the user activates the inline retry action.

Virtualization was useful when all sessions were loaded at once. With bounded initial loading and incremental fetching, removing it reduces coordination complexity between virtual indices, appended pages, deletion, and active-row updates. The DOM can still grow if a user scrolls through many pages; this is an accepted trade-off for this change and can be revisited if observed usage warrants windowing plus pagination.

### 6. Mutations reconcile pagination state without changing chat behavior

- A newly persisted chat is inserted or refreshed at the front of page-1 state without duplicating its temporary or real identity.
- Rename updates the matching loaded row locally and retains the current page state.
- Delete removes the row locally, preserves existing next-session navigation, and may refresh page 1 to refill/reconcile the visible list.
- Visibility/title refresh fetches page 1 rather than all chats and merges it with already loaded older pages by chat identity.
- Task-session filtering continues to run on every received page before rows enter the visible history list.

## Risks / Trade-offs

- **[JSON storage still requires a full file read and in-memory sort]** -> Keep the repository pagination boundary explicit, document the limitation, and ensure status lookup, response serialization, network transfer, and frontend work are page-bounded.
- **[Offset pagination can shift while chats are updated]** -> Use stable ordering, identity-based deduplication, and page-1 refresh reconciliation.
- **[Conditional response shapes can be misused by clients]** -> Keep separate typed frontend methods, validate that pagination parameters are paired, and retain regression tests for the unpaginated array contract.
- **[Active deep-linked chat may not be in page 1]** -> Continue direct detail loading and explicitly test recovery and follow-up identity behavior when the list page omits the active chat.
- **[Removing virtualization can grow the DOM after extended scrolling]** -> Use a conservative default page size, load only near the bottom, and monitor real usage.
- **[Refreshing page 1 could discard loaded older pages or pending sessions]** -> Centralize merge rules in the session adapter and test pending, resolved, duplicate, task-session, and active-chat cases.

## Migration Plan

1. Add backend pagination models and repository/manager tests while retaining the legacy list path.
2. Expose the optional query parameters and paginated response on root and agent-scoped chat routes.
3. Add the typed Console paginated API and session-state merge logic behind the existing chat UI.
4. Replace virtualized sidebar rendering with normal rows and scroll-to-end pagination, retaining an explicit retry action for failures.
5. Run backend API/manager tests, focused Console tests, type checking/build, and chat regression flows.

Rollback consists of returning the Console to the legacy unpaginated call and virtualized list; the backend extension can remain because callers that omit pagination parameters are unchanged.

## Open Questions

- Select the initial default page size during implementation based on current sidebar density and test fixtures; 30-50 items is the expected range, with a server maximum of 100.
- Load-more errors use an inline retry row so already loaded history remains visible and automatic retries do not loop.
