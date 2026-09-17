## 1. Content-only session initialization

- [x] 1.1 Detect an unmapped numeric temporary route ID before normal session selection, clear the active session, and expose the existing unavailable state only in content-only presentation.
- [x] 1.2 Preserve mapped temporary-ID restoration, persisted non-temporary deep links, and the normal chat temporary-session creation path.

## 2. Regression coverage

- [x] 2.1 Cover unmapped content-only temporary IDs without navigation or backend-loading ownership.
- [x] 2.2 Cover mapped temporary IDs, persisted deep links, and normal-mode temporary IDs to protect the behavior boundary.

## 3. Verification

- [x] 3.1 Run the focused initializer tests and applicable frontend formatting, lint, and type/build checks.
- [x] 3.2 Validate the OpenSpec change and inspect the final GitNexus change scope before archive.
