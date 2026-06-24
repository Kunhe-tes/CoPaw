## Context

The Console keeps a paginated history list in `sessions`, while task navigation uses cron job metadata to navigate to `/chat/:chatId`. Those two data sets are intentionally different: tasks can point to older chats that are not in the first loaded history page.

`ChatSessionInitializer` is responsible for one direction of synchronization: URL `chatId` to the chat runtime's `currentSessionId`. The existing initializer resolved the URL against the loaded `sessions` list and only called `setCurrentSessionId` when it found a matching session object. That made pagination visible to task navigation.

The chat runtime already has a lower-level session loader that calls `options.api.getSession(currentSessionId)` and can load messages by chat id through the chat detail endpoint. The safest fix is to let that loader handle off-page chats instead of making the initializer construct or inject history-list sessions.

## Goals / Non-Goals

**Goals:**

- Allow valid `/chat/:id` routes to activate even when the corresponding chat is not in the loaded history page.
- Preserve existing behavior when the session is present in `sessions`.
- Preserve new-chat local pending-session behavior during first response persistence.
- Avoid adding new backend endpoints or changing history pagination behavior.

**Non-Goals:**

- Fetching or inserting off-page chats into the history sidebar during URL initialization.
- Changing task target resolution order.
- Changing chat list page size, cursor behavior, sorting, or load-more behavior.
- Redesigning the sidebar or task list.

## Decisions

### 1. Select missing URL ids instead of injecting session objects

**Decision:** If the URL resolves to an id that is not present in the loaded `sessions` page, `ChatSessionInitializer` calls `setCurrentSessionId(resolvedSessionId)` directly.

**Rationale:** This reuses the existing runtime loader and chat detail endpoint, which already own message loading, reconnect handling, loading state, and race checks. It avoids introducing partially shaped history-list objects.

**Alternative considered:** Have the initializer call `sessionApi.getSession()` and prepend the returned object into `sessions`. Rejected because this can insert incomplete history metadata and can interfere with new-chat local pending-session resolution.

### 2. Guard active local pending sessions

**Decision:** If the currently active session id is a local timestamp id, the initializer does not replace it with a missing URL id.

**Rationale:** During first response persistence, the app may briefly move from a local pending id to a backend chat id. Replacing `currentSessionId` in that window can interrupt the in-progress conversation and cause flicker.

**Alternative considered:** Always select the URL id. Rejected because it reproduced new-chat instability after the first answer completes.

### 3. Keep agent alignment limited to known session objects

**Decision:** Agent alignment still runs only when a matching loaded session object exists and exposes metadata.

**Rationale:** Missing-page sessions do not have loaded metadata in the initializer. The runtime loader remains responsible for loading the chat; agent switching for missing-page history is not added as part of this narrow pagination fix.
