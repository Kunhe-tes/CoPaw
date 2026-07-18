## Why

Deep-linked chat records currently open the full Conversation Workspace, including global navigation, chat history, task navigation, model selection, generated-file entry points, and the question composer. Embedded hosts and local reviewers need a focused way to display one `/chat/{chat.id}` without those surrounding surfaces.

This is a presentation requirement, not a read-only or authorization mode. The selected chat must continue to use the existing loading, streaming, message-card, approval, feedback, retry, preview, and request behavior.

## What Changes

- Add `showContentOnly=true` as an opt-in query parameter for `/chat/{chat.id}`. Activation is independent of iframe presence and `source`, so the same URL works in embedded hosts and direct local testing.
- Hide the global Header and Sidebar, the entire chat sidebar (including tasks, history, and its collapsed toolbar), the generated-files entry/list, the model selector, the question composer, and upload surfaces.
- Keep the existing chat title and complete conversation content.
- Keep all message-level interactions governed by their existing normal-chat rules, including approval/deny, feedback, retry/regenerate, suggestions, copy, download, preview, and disclosure controls.
- Reuse the normal `/chat/{chat.id}` identity initialization, session restoration, loading/empty/error behavior, request ownership, SSE reconnect, stream rendering, background effects, and HTML-preview tracking without adding content-only branches.
- Preserve all existing Conversation Workspace behavior when the query parameter is absent or not exactly `true`.

## Capabilities

### New Capabilities

- `chat-content-only-mode`: URL activation and focused Conversation Workspace presentation for an existing chat route.

### Modified Capabilities

- `sidebar-task-list`: Define complete visual suppression of the chat sidebar in content-only presentation while preserving its normal-mode behavior.
- `chat-welcome-layout`: Hide composer and upload surfaces in content-only presentation without changing normal chat state selection or data behavior.
- `console-design-system`: Document the reusable content-only Conversation Workspace presentation variant.

## Impact

- Console URL-mode resolution and global layout under `console/src/layouts/MainLayout/`.
- Conditional composition under `console/src/pages/Chat/` and the shared Chat surface for hiding the composer.
- Focused layout, normal-mode regression, message-action compatibility, and running-stream presentation tests.
- `console/DESIGN.md` and affected OpenSpec capabilities.
- No backend contract, `USER_DATA`, iframe identity, session provider, runtime controller, response card, approval, feedback, preview-recording, or streaming logic change is required.
