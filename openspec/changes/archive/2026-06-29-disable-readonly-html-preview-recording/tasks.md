## 1. Impact And Scope Checks

- [x] 1.1 Run GitNexus impact analysis for `HtmlPreviewTrackingProvider`, `useHtmlPreviewTracking`, `FilePreviewModal`, and `ReadOnlySessionChat` before editing their symbols.
- [x] 1.2 Confirm current call sites for `DownloadFileCard`, Markdown file links, tool-rendered file cards, and normal chat task preview paths.

## 2. Recording Context

- [x] 2.1 Add a recording-specific optional flag, `disableEventRecording`, to `HtmlPreviewTrackingContextValue`.
- [x] 2.2 Keep the default context value backward-compatible so existing providers continue recording unless they explicitly opt out.

## 3. Read-Only Replay Integration

- [x] 3.1 Wrap the business overview `ReadOnlySessionChat` rendered message tree in `HtmlPreviewTrackingProvider` with `disableEventRecording: true`.
- [x] 3.2 Ensure the provider scope covers nested preview modals created from read-only replay without affecting other business overview analytics widgets.

## 4. Preview Modal Recording Gate

- [x] 4.1 Update `FilePreviewModal` to derive a `shouldRecordHtmlPreviewEvents` value from `useHtmlPreviewTracking()`.
- [x] 4.2 Keep `attachHtmlPreviewClickTracker` attached when click tracking is enabled, even when event recording is disabled.
- [x] 4.3 Pass `htmlPreviewEventsApi.recordClick` only when recording is enabled; otherwise pass a no-op reporter.
- [x] 4.4 Pass `htmlPreviewEventsApi.recordListSnapshot` only when recording is enabled and list snapshot tracking is enabled.
- [x] 4.5 Confirm nested `FilePreviewModal` instances inherit the disabled recording context.

## 5. Tests

- [x] 5.1 Add or update tests proving normal auto-preview HTML still enables click tracking and records eligible click events.
- [x] 5.2 Add or update tests proving scheduled task auto-preview tracking context still records task-associated events.
- [x] 5.3 Add or update tests proving business overview read-only replay does not call click or list snapshot recording APIs.
- [x] 5.4 Add or update tests proving nested previews still open in read-only replay while recording remains disabled.

## 6. Verification

- [x] 6.1 Run the focused frontend tests for HTML preview tracking, file preview modal behavior, download file cards, and business overview user detail read-only chat.
- [x] 6.2 Run the relevant frontend type/lint checks for the touched Console files.
- [x] 6.3 Run `detect_changes()` before commit to confirm the affected symbols and flows match the approved scope.
