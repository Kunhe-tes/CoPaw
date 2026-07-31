## Why

A content-only chat opened with a missing backend chat ID currently ends on a blank conversation surface after the history request returns 404. The focused view should explain that the conversation is unavailable without treating every empty or temporarily loading conversation as missing.

## What Changes

- Track whether the active chat session detail request returned HTTP 404 alongside the existing loading state.
- Render a focused 404 unavailable state only when the active content-only chat detail request returns HTTP 404.
- Ignore stale 404 results if the active session identity changes before the request finishes.
- Preserve valid empty chats, non-404 error behavior, normal chat presentation, URL activation, session restoration, and backend APIs.
- Add focused regression coverage for missing, successful, empty, normal-mode, and stale-request scenarios.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chat-content-only-mode`: Define the focused unavailable state for a content-only route whose active chat detail request returns 404.
- `chat-welcome-layout`: Distinguish a content-only 404 result from a valid empty chat while continuing to suppress question-entry surfaces.

## Impact

- Frontend session runtime state and message-list rendering under `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/`.
- Focused frontend tests for session loading and content-only message-list composition.
- No backend route, request contract, iframe/source handling, persistent browser storage, or normal chat mutation behavior changes.
