## 1. Backend Pagination Contract

- [x] 1.1 Add failing manager/repository tests for filtered newest-first pagination, deterministic `id` tie-breaking, totals, empty out-of-range pages, and page-size boundaries.
- [x] 1.2 Add a structured chat-page result model and implement repository/manager pagination after existing `user_id` and `channel` filters.
- [x] 1.3 Add failing API tests proving that `GET /chats` without pagination retains the legacy array shape/order and that paired pagination parameters return metadata and only annotate page-item statuses.
- [x] 1.4 Extend the chat-list route with validated paired `page`/`page_size` parameters and the conditional paginated response, including agent-scoped route coverage.
- [x] 1.5 Add or update CLI/API documentation examples without changing the existing unpaginated CLI behavior.

## 2. Frontend API And Session Pagination State

- [x] 2.1 Add paginated chat response types and a dedicated typed API method while retaining the existing array-returning `listChats` method.
- [x] 2.2 Add failing session-adapter tests for initial page loading, next-page append, single-flight loading, deduplication, `has_more`, and identity-reset behavior.
- [x] 2.3 Implement paginated state in `SessionApi`, including page-1 replacement/reconciliation and older-page append after task-session filtering.
- [x] 2.4 Add regression tests and implementation for pending local sessions and temporary-to-real chat resolution so pagination never creates duplicate logical rows.
- [x] 2.5 Preserve direct detail loading for a URL chat absent from loaded pages and verify that follow-up requests continue using the recovered logical `session_id`.
- [x] 2.6 Reconcile create/title refresh/rename/delete flows with loaded pages without clearing older loaded rows or changing active-chat navigation.

## 3. Sidebar Paginated History UI

- [x] 3.1 Add failing component tests for first-page display, load-more visibility, loading lock, append order, retry after failure, and terminal no-more state.
- [x] 3.2 Remove `useVirtualizer`, the virtual spacer/absolute row positioning, and virtual-list-only styling from the history sidebar.
- [x] 3.3 Render loaded history rows normally and add an accessible load-more interaction with loading and retry states that preserves existing rows and scroll context.
- [x] 3.4 Preserve history title/timestamp presentation, collapse behavior, active-row styling, item click navigation, rename, and delete behavior.
- [x] 3.5 Verify collapsed-sidebar history panel behavior remains functional or explicitly shares the same paginated state without triggering an unpaginated fetch.

## 4. Regression And Performance Verification

- [x] 4.1 Run focused backend manager/API tests covering legacy and paginated list paths plus unchanged chat detail timestamps/messages.
- [x] 4.2 Run focused Console session API and sidebar tests, including session identity, reconnect, delete navigation, and task-session filtering suites.
- [x] 4.3 Run Console TypeScript checking/build and relevant backend lint/type checks used by the repository.
- [x] 4.4 Exercise the chat page with a large generated history fixture and confirm initial network payload, status lookups, frontend transformation, and rendered rows are bounded by the configured page size.
- [x] 4.5 Manually verify new chat creation, first-response ID resolution, existing history opening, message display, follow-up send, streaming, stop, reconnect, rename, delete, page refresh, and deep-link recovery.
  - Read-only browser smoke covered history opening, message display, collapsed history, refresh, and deep-link recovery; mutating and streaming flows were covered by focused regression tests to avoid changing live user data.

## 5. Scroll-To-End Pagination Follow-up

- [x] 5.1 Add failing UI tests for near-bottom loading, non-bottom scrolling, single-flight locking, failure retry, terminal no-more behavior, and collapsed-panel reuse.
- [x] 5.2 Replace the idle load-more button with a shared scroll-to-end trigger while retaining loading and explicit retry feedback.
- [x] 5.3 Attach the shared trigger to the expanded sidebar and collapsed history panel scroll containers without changing session ordering or navigation behavior.
- [x] 5.4 Run focused UI/session regressions and production build checks for expanded, collapsed, refresh, and deep-link flows.
  - The focused Console suite passed 54 tests, the backend regression suite passed 21 tests, and the production build completed successfully. A fresh browser launch was attempted but blocked by the local approval quota; the existing read-only browser baseline remains covered by the new integration tests.
- [x] 5.5 Finalize the delta specs for synchronization and archive the completed OpenSpec change.
