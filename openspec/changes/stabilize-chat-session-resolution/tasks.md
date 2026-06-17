## 1. Regression Coverage

- [x] 1.1 Add a `ChatSessionInitializer` regression test where `/chat/{chat_id}` is absent from the loaded sessions page and the initializer still selects the URL chat id for detail loading.
- [x] 1.2 Add a task-open regression test proving a valid `task.chat_id` outside the loaded sessions page navigates to `/chat/{chat_id}` and does not require a loaded-list match.
- [x] 1.3 Add a pending-session regression test where temporary id to real `chat_id` URL synchronization does not switch `currentSessionId` to the real id or clear visible messages.
- [x] 1.4 Add a `SessionApi.getSession` regression test proving recovered detail metadata is merged into local session state without resetting page, cursor, or loaded older sessions.

## 2. Session Resolution Implementation

- [x] 2.1 Implement route-level direct-detail recovery in `ChatSessionInitializer` for `/chat/:id` values that are absent from the loaded session page.
- [x] 2.2 Detect current pending-session-to-real-id equivalence and skip `setCurrentSessionId(realId)` when the URL update refers to the active runtime conversation.
- [x] 2.3 Preserve selected-agent alignment for loaded-list matches and recovered sessions without introducing agent changes before metadata is known.
- [x] 2.4 Keep `resolveRequestedSessionId` behavior conservative unless tests prove a minimal helper extraction is safer.

## 3. Recovered Session Merge

- [x] 3.1 Ensure `SessionApi.getSession(chatId)` inserts or merges recovered chat metadata into the local session list when the chat is absent from loaded pages.
- [x] 3.2 Deduplicate recovered, loaded, pending, and resolved sessions by known identity keys so later page loads do not create duplicate rows.
- [x] 3.3 Preserve existing pagination state (`sessionPage`, `hasMoreSessionPages`, `nextSessionCursor`, and loaded older rows) during direct detail recovery.

## 4. Verification

- [x] 4.1 Run focused frontend tests for chat session initialization, session API identity recovery, session loader behavior, and sidebar/task navigation.
- [x] 4.2 Run backend chat pagination tests to confirm the current page-size ceiling and list/detail contracts remain valid.
- [x] 4.3 Run GitNexus `detect_changes()` before commit and confirm the affected scope matches chat session resolution and pagination recovery.
- [x] 4.4 Manually verify the two primary user flows: task opens an older chat outside the initial page, and a new chat's first answer does not flicker when the URL resolves to the backend chat id.
