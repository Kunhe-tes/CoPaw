## 1. Session loading state

- [x] 1.1 Add an active session-not-found flag to the shared sessions context with a default value of false.
- [x] 1.2 Capture only the active session detail HTTP 404 while ignoring stale 404 results and preserving existing handling for non-404 failures.
- [x] 1.3 Keep the fixed-chat embedded lifecycle minimal by writing the flag only when the active request returns HTTP 404.

## 2. Content-only unavailable state

- [x] 2.1 Render a centered, non-interactive 404 result in the content-only message area when the active session detail load error is 404.
- [x] 2.2 Preserve the existing valid-empty, loading, normal chat, and populated conversation render paths.

## 3. Verification

- [x] 3.1 Add session-loading tests for active 404 capture, successful-load behavior, and stale request protection.
- [x] 3.2 Add message-list tests covering content-only 404, valid empty sessions, and normal chat compatibility.
- [x] 3.3 Run focused frontend tests plus the applicable type/build checks and inspect the GitNexus change impact.
