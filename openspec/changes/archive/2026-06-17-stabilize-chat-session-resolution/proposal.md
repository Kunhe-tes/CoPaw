## Why

Chat history is paginated in the Console, so the in-memory `sessions` list may only contain the first loaded page. Clicking a scheduled task can navigate to a valid chat whose history row is outside that loaded page. Before this fix, URL-to-session initialization only selected sessions already present in the loaded list, leaving task navigation unable to activate off-page chats.

A first attempt to repair this by injecting a fetched session into the loaded history list caused new-chat regressions: the newly persisted chat could briefly replace the local pending session, produce incomplete history metadata, and interrupt follow-up conversation. The completed fix needs to preserve normal new-chat resolution while allowing valid off-page chat IDs to load through the existing runtime session loader.

## What Changes

- When `/chat/:id` points to a session already present in the loaded `sessions` page, keep the existing selection and agent-alignment behavior.
- When `/chat/:id` points to a valid chat not present in the loaded `sessions` page, select the URL id directly so the existing session loader can fetch chat detail by id.
- Do not inject ad hoc fetched sessions into the history list during URL initialization.
- Do not replace an active local pending session while a newly created chat is resolving from a local timestamp id to a backend chat id.
- Add focused tests for off-page URL activation and the local pending-session guard.

## Capabilities

### Modified Capabilities

- `chat-history-pagination`: Console session initialization now supports chat detail activation for valid `/chat/:id` routes even when that chat is outside the currently loaded history page.

## Impact

- Affected Console component: `ChatSessionInitializer`.
- Affected tests: `ChatSessionInitializer` unit tests.
- No backend API contract, pagination parameter, task API, or history-list rendering changes.
