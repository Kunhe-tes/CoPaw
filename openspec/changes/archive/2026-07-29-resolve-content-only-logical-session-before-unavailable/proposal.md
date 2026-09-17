## Why

A numeric URL target is not necessarily an expired local temporary ID: it can be the logical `sessionId` of an existing persisted chat. The current content-only guard marks such targets unavailable before the session list can resolve them, so a successful chat detail response can remain hidden behind the 404 result.

## What Changes

- Wait for the initial session list to finish loading before classifying a numeric content-only route target as unresolved.
- Run the existing session identity resolution first so `id`, `realId`, `sessionId`, and valid temporary mappings can restore the persisted chat.
- Set the unavailable state only when the loaded session list cannot resolve the numeric target to a persisted session.
- Clear a premature or stale unavailable flag when the target resolves successfully.
- Preserve the no-backend-request behavior for a genuinely unresolved temporary ID and preserve normal chat initialization.
- Add focused regression coverage for list-loading, logical numeric `sessionId`, and genuinely unresolved temporary-ID scenarios.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chat-content-only-mode`: Define an unresolved temporary target only after loaded session identities and mappings fail to resolve it.
- `chat-welcome-layout`: Prevent the unavailable result from masking a successfully resolved logical session deep link.

## Impact

- Frontend content-only route initialization under `console/src/pages/Chat/components/ChatSessionInitializer/`.
- Focused initializer regression tests.
- Existing content-only unavailable-state specifications.
- No backend API, session-list contract, normal chat creation flow, or visual design changes.
