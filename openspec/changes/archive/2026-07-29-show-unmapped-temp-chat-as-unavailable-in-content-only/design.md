## Context

New chats use a numeric timestamp-like UI session ID until the backend returns a persisted `chat.id`. The frontend stores the temporary-to-persisted mapping in session storage and uses the loaded session list to select the persisted record.

A content-only page is a fixed, read-only deep link and cannot create or switch conversations. If that page starts with a temporary ID after its mapping has disappeared, there is no persisted identity that the frontend can resolve. Passing the temporary ID into the normal detail-loading path is incorrect because it is not a backend chat ID, while leaving the session unselected produces the same blank region used by a valid content-only empty state.

The existing content-only missing-chat behavior already renders a non-interactive unavailable result when a persisted chat detail request returns HTTP 404. The change should reuse that presentation while keeping the normal new-chat lifecycle unchanged.

## Goals / Non-Goals

**Goals:**

- Recognize an unmapped numeric temporary ID during content-only route initialization.
- Stop that unresolved ID from reaching the backend chat detail loader.
- Reuse the existing `sessionNotFound` state and unavailable rendering.
- Preserve mapped temporary-ID recovery and all non-content-only behavior.

**Non-Goals:**

- Requesting the backend with a temporary ID to confirm that it is missing.
- Treating arbitrary persisted chat IDs, non-404 failures, or valid empty chats as unavailable.
- Adding recovery actions, navigation, session switching, or a new visual treatment.
- Changing the temporary-session lifecycle used to create a normal chat.

## Decisions

### 1. Detect the unresolved temporary identity at route initialization

`ChatSessionInitializer` will inspect the concrete `/chat/{id}` target before its existing empty-session-list early return. When content-only presentation is active, the target follows the numeric local-session convention, and `getResolvedChatId` has no mapping, the initializer will clear `currentSessionId`, set `sessionNotFound`, and stop initialization.

This placement prevents the shared session provider from issuing a detail request with the temporary ID and allows the unavailable result to render even when no session list has loaded.

Alternative considered: wait for the detail API to return HTTP 404. This is rejected because the ID is known to be a frontend-only identity and deliberately should not be sent to the backend.

### 2. Keep mapped temporary IDs on the existing restoration path

If `getResolvedChatId` returns a persisted ID, the initializer will continue into `getInitialSessionSelection`. The loaded session list remains the source used to select that persisted record and replace the route with its real `chat.id`.

Alternative considered: select the mapped ID immediately without the session list. This is unnecessary because the existing selection path already coordinates session metadata and agent selection, and the product constraint guarantees that a valid mapping corresponds to an entry in the session list.

### 3. Reuse the existing content-only unavailable state

The unresolved route will set the same `sessionNotFound` state used by an active persisted-chat HTTP 404. `MessageList` therefore keeps one focused missing-chat presentation regardless of whether absence was established locally before a request or by the backend response.

Alternative considered: introduce a separate invalid-temporary-ID render state. This would duplicate an indistinguishable user outcome and broaden shared session state without adding a recovery path.

### 4. Gate the behavior strictly by content-only presentation

The temporary-ID check will run only when `useChatContentOnly()` is active. Normal chat initialization will continue selecting an unmapped temporary ID so the existing new-chat flow can persist it.

No source parameter, iframe condition, backend contract, or persistent storage behavior is changed.

## Risks / Trade-offs

- **[Risk] A persisted chat ID is entirely numeric and is mistaken for a local ID.** → Retain the established numeric temporary-ID convention; persisted backend IDs are expected to use the existing non-temporary format.
- **[Risk] A valid mapping is present before the session list loads.** → Do not mark it unavailable; wait for the existing session-list-driven resolution path.
- **[Risk] The new branch affects normal chat creation.** → Require active content-only presentation and cover normal-mode initialization with a paired regression test.
- **[Risk] The unavailable state causes a backend request before current selection clears.** → Handle the route before normal selection and return immediately after clearing `currentSessionId`.

## Migration Plan

No data or API migration is required. Deploy the frontend and specification updates together. Rollback removes the initializer guard and its focused tests; the earlier persisted-chat HTTP 404 behavior remains intact.

## Open Questions

None.
