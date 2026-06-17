## Why

Chat history pagination currently lets the Console load only the first page of sessions, but route initialization still treats the loaded session list as the gate for opening `/chat/:id`. This can prevent valid task links or direct chat URLs from calling the chat detail endpoint, and a naive fallback can also make a newly created chat flicker by reloading when its temporary id resolves to a real chat id.

## What Changes

- Decouple chat opening from the paginated session list: `/chat/:id` should be treated as an authoritative backend `chat_id` when existing identity resolution cannot match it locally.
- Preserve temporary-session runtime identity when a new chat resolves to a real backend `chat_id`, so URL synchronization does not clear visible messages or show a reload state.
- When a chat detail request recovers a valid chat outside the loaded page, merge that recovered session into local session state without refreshing page 1 or disturbing pagination cursors.
- Keep the existing task open target priority, while ensuring a valid `task.chat_id` can open even when it is absent from the loaded session page.
- Keep the temporary mitigation of a larger frontend initial page size and backend page-size ceiling, but do not rely on it for correctness.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `chat-history-pagination`: clarify and enforce that paginated history loading must not block direct chat detail recovery, task deep links, or temporary-to-real chat identity resolution.

## Impact

- Console chat session initialization and URL-to-session synchronization.
- Console session API identity merge behavior for chats recovered from `/api/chats/{chatId}`.
- ChatAnywhere session loader behavior around `currentSessionId` changes and message clearing.
- Regression tests for task deep links, direct chat URLs outside loaded pages, pending-session resolution, and normal history navigation.
- No backend API contract change is required beyond the already planned page-size ceiling configuration.
