## 1. Content-only identity resolution

- [x] 1.1 Wait for initial session-list loading and resolve the requested identity before applying the numeric temporary-ID unavailable fallback.
- [x] 1.2 Clear stale unavailable state for a resolved persisted session while preserving existing selection, agent alignment, route canonicalization, and normal chat behavior.

## 2. Regression coverage

- [x] 2.1 Cover a numeric logical `sessionId` resolving to its persisted `chat.id` without rendering unavailable.
- [x] 2.2 Cover the list-loading boundary and preserve genuinely unresolved, mapped temporary, persisted, and normal-mode routes.

## 3. Verification and specification sync

- [x] 3.1 Run focused session initialization tests plus applicable lint, formatting, and build/type checks.
- [x] 3.2 Validate the OpenSpec change, inspect GitNexus change scope, and synchronize the corrected requirements.
