## Context

The normal Conversation Workspace is a stateful, interactive surface. `MainLayout` renders the global Header and Sidebar, `ChatPage` renders its own `ChatSidebar`, and the AgentScope Runtime renders the chat title, messages, composer, message actions, session controller, and stream controller. A direct `/chat/{chat.id}` already restores persisted content and reconnects to a running response when applicable.

The requested mode is only a focused composition of that existing page. It hides navigation, model/file selectors, and the question-entry surfaces, but it is not a second chat renderer, a read-only policy, or a new request path. Any chat capability that remains visible must behave exactly as it does on the normal route.

## Goals / Non-Goals

**Goals:**

- Resolve a source-independent presentation mode from `/chat/{chat.id}?showContentOnly=true`.
- Hide the global shell, chat sidebar, generated-files entry/list, model selector, composer, and upload surfaces.
- Preserve the existing title, full conversation, message cards, and message-level actions.
- Preserve the normal route's loading, streaming, reconnect, approval, feedback, retry, preview, and background behavior.
- Leave normal chat and existing `hideMenu`/`origin=Y` embedding unchanged when the parameter is inactive.

**Non-Goals:**

- Creating a read-only or authorization boundary.
- Blocking approval, feedback, retry/regenerate, suggestion, preview, or other message-level actions.
- Changing `USER_DATA`, iframe initialization, session-list behavior, session restoration, controller events, request ownership, cancel behavior, SSE/reconnect, preview tracking, or backend APIs.
- Adding content-only loading, empty, unavailable, identity, or stream state machines.
- Redesigning the normal Conversation Workspace or message cards.

## Decisions

### 1. Resolve presentation mode from the URL only

A shared pure resolver activates content-only presentation only for a concrete `/chat/{chat.id}` route whose parsed query contains the exact lower-case value `showContentOnly=true`. It does not inspect `source` or iframe presence and does not persist the flag into `USER_DATA`, Zustand, session storage, or another store.

This makes the first render deterministic, supports direct local testing, and lets future sources reuse the same presentation.

### 2. Limit the mode to component composition

`showContentOnly` is consumed only at rendering boundaries:

- `MainLayout` omits the global Header, global Sidebar, and unrelated floating shell chrome.
- `ChatPage` omits the whole `ChatSidebar`, generated-files entry/list, model selector, question composer, and page-level upload surface.
- The shared Chat surface does not mount its input/upload component while content-only presentation is active.

The mode is not passed into the session provider, runtime controller, response cards, approval handlers, feedback handlers, retry handlers, request layer, stream ownership, or preview-recording policy. Message actions retain their existing visibility, permission checks, state checks, and handlers.

Conditionally not mounting hidden input/upload components prevents those hidden surfaces from remaining focusable or accepting local drag/paste input. This is a presentation composition decision; no controller event is blocked or redefined.

### 3. Inherit normal `/chat/{chat.id}` behavior

The normal chat route remains the single source of behavior for identity readiness, detail/session loading, state selection, message conversion, title resolution, running-stream reconnect, follow-up effects, approvals, feedback, retries, suggestions, cancellation, and preview tracking.

Content-only presentation neither adds nor removes requests. If the existing route can restore a chat or display subsequent SSE output, the same content continues to appear because the same providers and controllers are mounted unchanged.

### 4. Suppress shell chrome at both layout layers

`MainLayout` owns the global Header and Sidebar. `ChatPage` independently owns `ChatSidebar`, including the expanded task/history sections, collapsed toolbar, and expandable panels. Both layers must omit their respective surfaces so the conversation uses the available width without an empty rail.

This is independent of the existing `hideMenu` contract. `hideMenu` and `origin=Y` retain their current behavior; content-only presentation simply contributes another URL-derived reason to hide the global shell on the target chat route.

## Risks / Trade-offs

- **[Risk] Presentation checks leak into chat behavior.** → Keep the mode out of session, controller, request, response-action, approval, feedback, reconnect, and preview-tracking code; verify the diff and normal-mode behavior.
- **[Risk] A hidden input surface remains mounted and focusable.** → Conditionally omit the composer/input and upload overlay instead of relying only on CSS.
- **[Risk] The chat sidebar leaves reserved width.** → Omit the entire `ChatSidebar` component, including its collapsed variant, and verify all target desktop sizes.
- **[Risk] Normal message actions are accidentally hidden.** → Add paired normal/content-only tests showing that approval, feedback, retry/regenerate, suggestions, copy, download, and preview continue to follow the same existing rules.
- **[Risk] Normal embedding changes.** → Keep existing `hideMenu`/`origin=Y` logic intact and add regression coverage.

## Migration Plan

1. Keep the shared URL resolver and two-layer layout suppression.
2. Remove the previously introduced identity, session, controller, response-action, approval, feedback, reconnect, and preview-tracking policies.
3. Retain only conditional rendering for the requested hidden surfaces.
4. Update focused tests and run normal chat, embedded, and streaming regressions.

Rollback is frontend-only: stop emitting `showContentOnly=true` or revert the presentation wiring. No persisted data, backend schema, or API migration is involved.

## Open Questions

None. The latest accepted boundary is presentation-only: hide the surrounding navigation, file/model selectors, and question-entry surfaces while leaving all chat behavior unchanged.
