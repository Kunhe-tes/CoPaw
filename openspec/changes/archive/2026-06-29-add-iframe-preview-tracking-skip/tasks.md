## 1. Contract And Context

- [x] 1.1 Run GitNexus impact checks for the iframe message/store and chat tracking symbols before editing.
- [x] 1.2 Add `skipPreviewTracking` to iframe message and context types.
- [x] 1.3 Store `skipPreviewTracking` from `USER_DATA.data` using existing iframe boolean parsing and session context persistence.

## 2. Preview Tracking Wiring

- [x] 2.1 Read `skipPreviewTracking` in the Chat page.
- [x] 2.2 Pass `disableEventRecording` through `HtmlPreviewTrackingProvider` when iframe context has opted out while preserving task metadata.

## 3. Tests And Verification

- [x] 3.1 Add or update iframe message tests for true, string true, false, and omitted `skipPreviewTracking` behavior.
- [x] 3.2 Add or update Chat/FilePreviewModal tests proving iframe opt-out suppresses recording and default chat/task behavior still records.
- [x] 3.3 Run focused frontend tests, type check, and OpenSpec validation.
