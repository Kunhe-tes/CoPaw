## 1. Safety and baseline

- [x] 1.1 Re-read `AGENTS.md`, `console/DESIGN.md`, and the revised change artifacts; inspect the working tree and preserve unrelated user changes.
- [x] 1.2 Run GitNexus upstream impact analysis before editing existing symbols and report any HIGH or CRITICAL result before proceeding.
- [x] 1.3 Reassess the prior strict-read-only implementation against the new presentation-only boundary.

## 2. URL mode and shell presentation

- [x] 2.1 Keep a pure URL resolver for exact `/chat/{chat.id}?showContentOnly=true`, independent of iframe presence and `source`.
- [x] 2.2 Hide the global Header, global Sidebar, and unrelated shell chrome only for the active content-only chat route.
- [x] 2.3 Hide the whole `ChatSidebar`, including expanded task/history sections, collapsed toolbar, and panels, without changing sidebar state or data logic.
- [x] 2.4 Hide generated-files entry/list, model selection, question composer, and drag/paste/upload surfaces while retaining the existing title and full conversation.

## 3. Restore normal chat behavior

- [x] 3.1 Remove the content-only iframe identity gate, timeout, special session loader, direct-history bypass, and custom loading/error lifecycle.
- [x] 3.2 Remove content-only guards from session, controller, request ownership, submit/cancel/reconnect, and follow-up logic.
- [x] 3.3 Restore approval/deny, feedback, retry/regenerate, suggestions, task/message cards, and other message-level actions to their normal visibility and handlers.
- [x] 3.4 Restore the existing HTML-preview recording policy and keep content-only out of preview telemetry decisions.
- [x] 3.5 Confirm no content-only branch remains in chat data, session, controller, response-card, or request logic.

## 4. Documentation and verification

- [x] 4.1 Update `console/DESIGN.md` to define content-only as a presentation variant rather than a read-only policy.
- [x] 4.2 Keep or add focused tests for URL activation, global/chat shell suppression, hidden composer/upload surfaces, retained title, and normal message actions.
- [x] 4.3 Remove strict-read-only, identity-gate, special-session, controller-no-op, and preview-suppression tests that no longer describe the requirement.
- [x] 4.4 Run focused Vitest suites plus representative normal Chat, `hideMenu`/`origin=Y`, approval, feedback, retry, preview, and running-reconnect regressions.
- [x] 4.5 Run frontend lint/type/build checks in proportion to the change and report unrelated baseline failures separately.
- [ ] 4.6 Verify content-only presentation at `1280x720`, `1440x900`, and `1920x1080` in top-level and embedded use, checking clipping, empty rails, focusability, and horizontal overflow. Top-level checks passed at all three sizes; embedded visual verification is blocked by the local browser's iframe security policy.
- [x] 4.7 Run GitNexus `detect_changes` for the working changes and against `main`. The working changes are LOW risk with zero affected execution flows; the branch-wide `main` comparison is independently CRITICAL because the existing `v1.0.0` branch differs from `main` by 3,151 files.
