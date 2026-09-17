## Context

HTML preview statistics are recorded in the shared `FilePreviewModal` path. Auto-preview HTML files opened from normal chat, scheduled task outputs, Markdown file links, and tool-rendered file cards all eventually render a `DownloadFileCard`, open `FilePreviewModal`, attach iframe click tracking, and call `htmlPreviewEventsApi.recordClick` and optionally `recordListSnapshot`.

The business overview user detail modal renders another user's conversation history through `ReadOnlySessionChat`. That UI is intended for operational inspection, but it reuses the same response card and file preview components as normal chat. As a result, an operations user clicking buttons inside another user's auto-preview HTML can be counted as a real customer-manager click.

The current tracker also owns nested preview behavior. Disabling the tracker entirely would suppress recording, but it would also break nested preview links inside the HTML. The change therefore needs to separate "attach preview interaction handlers" from "record analytics events."

## Goals / Non-Goals

**Goals:**

- Suppress HTML preview click event recording in the business overview read-only session replay.
- Suppress list snapshot/view recording in the same read-only replay context.
- Preserve HTML preview interactivity, including nested preview links and dynamic-render nested previews.
- Preserve normal chat and scheduled task auto-preview statistics.
- Keep the change frontend-only unless implementation reveals a backend contract gap.

**Non-Goals:**

- Do not change backend event classification, event storage, analytics aggregation, or API contracts.
- Do not change visual design or layout of the business overview, chat, or preview modal.
- Do not globally disable auto-preview tracking.
- Do not alter which files qualify as auto-preview HTML.

## Decisions

1. Add a recording-specific flag to `HtmlPreviewTrackingContext`.

   The flag should be named for event recording, such as `disableEventRecording`, rather than click tracking. This avoids conflating analytics suppression with iframe interaction handling. The default value remains falsy, so existing providers and all normal chat flows keep their current behavior without code changes.

   Alternative considered: add `enableClickTracking={false}` in `ReadOnlySessionChat`. This is rejected because `DownloadFileCard` can re-enable tracking for auto-preview HTML and dynamic render links, and because disabling tracking entirely would also disable nested preview behavior.

2. Scope the flag only around business overview read-only replay.

   `ReadOnlySessionChat` should wrap its read-only runtime renderer in `HtmlPreviewTrackingProvider` with `disableEventRecording: true`. This localizes the behavior to operational replay and avoids changing the normal `Chat` page provider that carries task metadata.

   Alternative considered: add a prop through response cards and file cards. This is more invasive, easier to miss in Markdown/tool-render paths, and would create duplicate plumbing for a cross-cutting runtime context.

3. Keep `attachHtmlPreviewClickTracker` attached, but replace analytics reporters in `FilePreviewModal`.

   When `disableEventRecording` is active, `FilePreviewModal` should still call `attachHtmlPreviewClickTracker`, passing a no-op `reporter` and no `listSnapshotReporter`. This preserves click parsing and nested preview routing while preventing calls to `/html-preview/events` and `/html-preview/list-snapshot`.

   Alternative considered: add suppression inside `attachHtmlPreviewClickTracker`. This is possible, but the modal already resolves runtime context and API reporters, so gating at reporter selection keeps the tracker focused on DOM event extraction and nested preview handling.

4. Let nested `FilePreviewModal` inherit the same context.

   The nested preview modal is rendered inside the same React tree and currently passes `enableClickTracking`. The context flag should continue to apply there, so nested previews opened from read-only replay also avoid recording.

## Risks / Trade-offs

- [Risk] A future maintainer may interpret the flag as disabling preview interaction and bypass the tracker entirely. → Mitigation: use a recording-specific flag name and add tests that nested preview behavior remains available while analytics are suppressed.
- [Risk] A new operations replay surface may render chat messages outside `ReadOnlySessionChat` and miss the provider. → Mitigation: document the requirement in the spec and keep tests close to the read-only replay component.
- [Risk] A normal chat provider could accidentally set `disableEventRecording`. → Mitigation: do not modify `Chat/index.tsx` context value except for type compatibility; add regression tests for normal auto-preview recording.
- [Risk] List snapshot suppression may reduce analytics for operationally opened lists. → Mitigation: this is intended only for read-only replay; normal user-opened auto-preview lists continue to record snapshots.

## Migration Plan

1. Add the context flag with default falsy behavior.
2. Scope the flag to business overview read-only session replay.
3. Gate `FilePreviewModal` reporter selection with the flag while still attaching the tracker.
4. Add focused tests for suppressed recording in read-only replay and unchanged recording in normal preview flows.
5. Run relevant frontend tests for preview tracking, file cards, and business overview read-only chat.

Rollback is straightforward: remove the provider flag usage from `ReadOnlySessionChat` or revert the reporter gating. No persisted data migration is needed.
