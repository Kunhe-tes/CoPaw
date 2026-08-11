## Context

The shared chat runtime clears messages, marks the selected session as loading, and calls the configured session API whenever `currentSessionId` changes. A missing backend chat causes that promise to reject with an error carrying `status: 404`; the loader currently has no error state, so loading stops and content-only rendering falls through to an empty wrapper because its Welcome surface is intentionally omitted.

The content-only flag is presentation-only and source-independent. The embedded content-only surface displays one fixed routed chat and does not offer session switching; loading another chat creates a new page and provider lifecycle. This change must keep normal chat, valid empty chats, streaming, message actions, URL activation, and backend contracts unchanged while making the missing-chat outcome explicit.

## Goals / Non-Goals

**Goals:**

- Represent an HTTP 404 from the active session detail load as explicit runtime state.
- Render a centered Conversation Workspace 404 result only in content-only presentation.
- Prevent stale failures from a previously selected session from replacing the current session.
- Preserve existing behavior for valid empty sessions and non-404 failures.

**Non-Goals:**

- Treating every empty message list as a missing chat.
- Adding backend endpoints, changing response contracts, or coupling the behavior to `source=ruice`.
- Defining new behavior for 401, 403, 500, offline, or timeout failures.
- Changing normal chat message actions, session restoration, streaming, or mutation behavior.

## Decisions

### 1. Store a narrow session-not-found flag in the shared session context

The session context will expose a `sessionNotFound` boolean and its setter next to `isSessionLoading`. The provider initializes the flag to `false`, and `loadSessionMessages` sets it to `true` only when an HTTP 404 still belongs to the fixed routed session. It does not add reset writes for session switching because the embedded content-only surface cannot switch sessions within the same provider lifecycle.

Alternative considered: infer 404 from `messages.length === 0`. This is rejected because an empty list is also valid before initialization and for an existing conversation with no messages.

### 2. Handle only active HTTP 404 failures

The loader will recognize errors carrying numeric `status === 404`, consume that failure, and expose it to rendering. Non-404 failures will continue through the existing failure path so this focused change does not silently redefine authentication, permission, transport, or server-error behavior. A stale 404 will be ignored when `currentSessionId` has changed.

Alternative considered: convert every session load failure into the same unavailable state. This is rejected because it would mislabel permission and service failures as missing data.

### 3. Render the unavailable result at the message-list state boundary

`MessageList` already owns the loading, empty/welcome, and message branches and can read both session state and `useChatContentOnly()`. It will render a centered Ant Design 404 `Result` after loading completes when content-only presentation is active and `sessionNotFound` is true. The existing empty branch remains unchanged for valid empty chats and normal presentation.

The state copy will explain that the conversation does not exist or has been deleted. No new navigation action is added because content-only presentation is host-controlled and has no universally valid recovery destination.

Alternative considered: render the result in `ChatPage`. This is rejected because `ChatPage` does not own the detail request result and duplicating session state there would broaden the change.

### 4. Keep source and backend behavior unchanged

The normal authenticated `/chats/{chatId}` request continues to carry the existing source-scoped headers. The backend remains responsible for returning 404; the frontend only distinguishes that existing response for presentation.

## Risks / Trade-offs

- **[Risk] A slow missing-session request completes after the user switches sessions.** → Compare the requested session ID with the current session before storing the error, matching the existing successful-result race guard.
- **[Risk] A valid empty chat is mislabeled as missing.** → Drive the result exclusively from HTTP status, never message count.
- **[Risk] Normal chat gains an unexpected error page.** → Gate the new result with `useChatContentOnly()` and add paired regression coverage.
- **[Risk] The shared loader swallows unrelated failures.** → Consume only current-session 404 errors and preserve the existing non-404 rejection path.

## Migration Plan

No data or API migration is required. Deploy the frontend change normally. Rollback removes the session error state and content-only result branch.

## Open Questions

None.
