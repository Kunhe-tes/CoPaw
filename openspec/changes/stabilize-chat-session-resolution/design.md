## Context

The chat history pagination change made the Console load a bounded first page of sessions. The session adapter already has direct detail recovery in `SessionApi.getSession(chatId)`: when a chat is absent from the current list, it can call the chat detail endpoint and append the recovered metadata locally.

The current route initializer still blocks this recovery because it only calls `setCurrentSessionId` when the requested URL id resolves to a loaded list item. When the target chat is outside the loaded page, no current session is selected and the detail request never runs. A previous fallback that set `currentSessionId` from the URL fixed task deep links but also made new-chat first replies flicker: after the backend resolved a temporary local session to a real chat id, URL synchronization caused the loader to treat the same in-flight conversation as a different selected session and clear messages.

GitNexus impact analysis found low direct dependency counts for `ChatSessionInitializer`, `loadSessionMessages`, `getTaskOpenTarget`, and `SessionApi.getSessionList`, but `resolveRequestedSessionId` has HIGH upstream impact across sidebar click handling, Context, and SessionApi. The safer design keeps identity resolution semantics stable and adds explicit route/detail recovery at the initialization boundary.

## Goals / Non-Goals

**Goals:**

- Treat `/chat/:id` as an authoritative backend `chat_id` when existing loaded-list or resolved-mapping identity resolution does not find a local session.
- Allow task links and direct URLs for chats outside the loaded page to call `/api/chats/{chatId}` and render the recovered chat.
- Preserve the runtime identity of a pending local session when its real chat id is resolved, so URL synchronization does not clear currently visible messages.
- Merge recovered detail metadata into local session state without refreshing page 1, changing pagination cursors, or duplicating identity-equivalent rows.
- Keep existing task target priority and normal sidebar/history navigation behavior.

**Non-Goals:**

- Replacing chat list pagination with unpaginated loading.
- Changing backend chat detail, create, update, delete, stop, reconnect, or streaming contracts.
- Redesigning task metadata or changing `getTaskOpenTarget` priority.
- Reworking the whole identity model into a new state machine in this change.
- Depending on larger page sizes for correctness.

## Decisions

### 1. Keep `resolveRequestedSessionId` conservative

`resolveRequestedSessionId` should continue resolving only identities it can prove from the loaded sessions or temporary-to-real mapping. It should not grow a "guess this is a backend chat id" branch because GitNexus marks its upstream impact as HIGH and it participates in sidebar selection and context initialization.

Alternative considered: return the requested id whenever mapping is absent. This is simple but makes all callers inherit fallback semantics, including places where an unresolved logical `session_id` should not be silently treated as a persisted chat id.

### 2. Add route-level direct-detail recovery

`ChatSessionInitializer` should distinguish three cases:

- Loaded-list match: keep the existing behavior, including selected-agent alignment and `setCurrentSessionId(matching.id)`.
- Current pending session resolved to the URL chat id: treat the URL and current runtime session as the same conversation and avoid changing `currentSessionId`.
- No loaded-list match for `/chat/:id`: select the requested id as a backend chat id so the existing session loader calls `SessionApi.getSession(id)`, which is responsible for detail recovery.

This keeps the fallback close to the route context where `/chat/:id` has meaning, instead of changing lower-level identity helpers globally.

### 3. Recovered detail metadata is merged locally only

When `SessionApi.getSession(chatId)` successfully fetches a chat that is missing from `sessionList`, it should add or merge that recovered session into local state by identity. The recovery path must not call `getSessionList`, refresh page 1, reset `hasMoreSessionPages`, or alter `nextSessionCursor`.

The recovered chat can later be deduplicated naturally when page 1 refresh or load-more returns the same identity.

### 4. Temporary-to-real resolution must not reload the active pending conversation

When a pending local session resolves to a real backend chat id, the URL may be replaced with `/chat/{realId}`, but the active runtime `currentSessionId` should remain the pending/local id while the conversation is rendering. The `realId` mapping and `realId` field should be enough for URL guards, title updates, follow-up requests, and future history loads.

This avoids calling `loadSessionMessages` with `clearBeforeLoad: true` for the same conversation and prevents the first-answer flicker.

### 5. Keep the page-size increase as mitigation, not correctness

The frontend initial session page size can remain 200 and the backend maximum can remain 500, but tests and implementation must pass when the active chat is not in the loaded page. The page-size change reduces support noise but is not the root fix.

## Risks / Trade-offs

- [Mistaking a logical `session_id` for a backend `chat_id`] -> Keep fallback at the route initializer and rely on detail endpoint failure handling instead of changing global identity resolution.
- [New-chat flicker returns] -> Add a regression test where pending local id resolves to real chat id and URL changes without calling `setCurrentSessionId(realId)` or clearing messages.
- [Recovered sessions duplicate rows] -> Merge and dedupe by known identity keys: id, realId, logical sessionId, and temporary mapping.
- [Stale rapid navigation applies the wrong detail result] -> Preserve the existing session race guard and selected-session intent checks.
- [Agent selection is unknown for recovered chats until detail returns] -> Use loaded metadata when available; for missing-list recovery, align agent only after recovered session metadata exists.

## Migration Plan

1. Add focused regression tests for direct URL/task chat ids outside the loaded page and for pending-session URL resolution without message clearing.
2. Implement the route-level direct-detail recovery branch without changing `resolveRequestedSessionId` globally.
3. Ensure recovered detail sessions are merged into local session state and surfaced to React context without a page-1 refresh.
4. Re-run focused Console tests for `ChatSessionInitializer`, `sessionApi`, `ChatAnywhereSessionsContext`, and sidebar navigation.
5. Re-run backend pagination tests for the current page-size ceiling.
6. Use GitNexus `detect_changes()` before commit to confirm affected flows are limited to chat session resolution and pagination recovery.

Rollback is to keep the temporary page-size mitigation and revert the route/detail recovery logic. Backend detail contracts remain unchanged.
