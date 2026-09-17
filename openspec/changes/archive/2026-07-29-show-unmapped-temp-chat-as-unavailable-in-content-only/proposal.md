## Why

A `showContentOnly` deep link can retain a temporary numeric session ID after its client-side persisted mapping has disappeared. Because that identifier is not a backend chat ID, treating it as a normal session can leave the focused read-only surface blank or send a meaningless detail request instead of reporting that the conversation cannot be resolved.

## What Changes

- Detect an unmapped temporary numeric session ID only while content-only presentation is active.
- Render the existing non-interactive unavailable result for that unresolved deep link without requesting chat detail with the temporary ID.
- Continue resolving mapped temporary IDs to their persisted chat IDs through the existing session list.
- Preserve the normal new-chat temporary-session lifecycle outside content-only presentation.
- Preserve the existing HTTP 404, valid-empty, streaming, message interaction, and backend API behavior.
- Add focused regression coverage for unmapped, mapped, non-temporary, and normal-mode session initialization.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chat-content-only-mode`: Extend the focused missing-chat exception to an unresolved temporary deep-link ID while forbidding a backend detail request with that ID.
- `chat-welcome-layout`: Define that the existing unavailable result also replaces the blank content-only region for an unresolved temporary deep link.

## Impact

- Frontend chat session initialization under `console/src/pages/Chat/components/ChatSessionInitializer/`.
- Existing content-only unavailable state exposed through the shared session context and message-list rendering.
- Focused frontend tests for session initialization.
- No backend route, request contract, persistent browser storage, visual design rule, or normal chat creation behavior changes.
