## Context

The chat session list represents several identities for one persisted conversation: backend `chat.id`, resolved local `realId`, and logical `sessionId`. `resolveRequestedSessionId` already checks those identities and selects the newest persisted chat for a logical-session deep link.

The content-only missing-ID guard currently runs before the initial session list is available. It classifies every numeric route target without a session-storage mapping as an expired local timestamp ID. A valid logical `sessionId` can also be numeric, so the guard sets `sessionNotFound` before the existing resolver discovers the persisted chat. The provider can then load the correct chat successfully, but the stale flag still wins at the message-list render boundary and displays 404 over the loaded messages.

## Goals / Non-Goals

**Goals:**

- Give the loaded session identities priority over the temporary-ID fallback.
- Avoid writing unavailable state while the initial session list is still loading.
- Keep the existing no-request behavior for a numeric target that remains unresolved after list loading.
- Clear unavailable state when a loaded session resolves the requested identity.

**Non-Goals:**

- Changing how session lists, chat details, or logical session IDs are returned by the backend.
- Requesting a genuinely unresolved local timestamp ID from the backend.
- Changing normal chat creation, pagination, source scoping, or content-only presentation.
- Adding a new error state or visual treatment.

## Decisions

### 1. Use the existing session-list loading state as the resolution boundary

`ChatSessionInitializer` will read `isSessionsListLoading` from the shared sessions context. It will not classify a numeric content-only target as unavailable until this flag is false.

Alternative considered: delay by a fixed timeout. This is rejected because request duration is variable and the context already exposes the authoritative loading state.

### 2. Resolve the route target before applying the local-ID fallback

After list loading, the initializer will call `getInitialSessionSelection` and find the session whose `id` equals the resolved ID. This existing path covers direct `id`, `realId`, logical `sessionId`, and valid temporary mapping resolution. A numeric target is unavailable only when that process yields no matching persisted session.

Alternative considered: duplicate `id`, `realId`, and `sessionId` comparisons in the initializer. This is rejected because it would create a second identity-resolution implementation that can drift from normal route behavior.

### 3. Clear stale unavailable state for a resolved target

When a persisted session matches, the initializer will set `sessionNotFound` to false before continuing the existing agent selection, current-session selection, and route canonicalization steps. This makes the state consistent with a successful resolution and prevents an earlier or stale flag from masking messages.

Alternative considered: clear the flag in every successful shared detail load. This is broader than necessary because the regression is caused by the content-only initializer and normal chat does not render the flag.

### 4. Preserve the unresolved temporary-ID branch

Once list loading completes, a numeric content-only target with no matching persisted session will still clear `currentSessionId`, set `sessionNotFound`, and return before normal selection. It therefore does not become the owner of a backend detail request.

## Risks / Trade-offs

- **[Risk] The initial session-list request fails and leaves no identities to resolve.** → Preserve the existing provider loading lifecycle; this focused change does not redefine list-request error handling.
- **[Risk] A valid logical session exists outside the loaded list.** → Keep the current product boundary that deep-link-restorable identities are present in the initialized session list.
- **[Risk] Normal chat initialization is delayed.** → Gate the new waiting and unavailable logic by content-only presentation; retain the normal-mode path.
- **[Risk] Route canonicalization changes.** → Continue using the existing resolved ID and navigation conditions after a match.

## Migration Plan

No migration is required. Deploy the initializer and regression tests with the synchronized specifications. Rollback restores the previous early numeric-ID guard.

## Open Questions

None.
