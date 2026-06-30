## Context

HTML preview event recording is currently controlled at the `FilePreviewModal` boundary through `HtmlPreviewTrackingContext.disableEventRecording`. Operations read-only replay already sets that context to suppress click and list snapshot recording while preserving preview interactions.

Embedded Console sessions receive parent application context through `USER_DATA` iframe messages handled by `iframeMessage.ts` and stored in `iframeStore`. Chat uses `HtmlPreviewTrackingProvider` to pass task metadata into preview tracking, but it does not currently let iframe context suppress recording.

## Goals / Non-Goals

**Goals:**

- Accept a short iframe `USER_DATA.data.skipPreviewTracking` parameter.
- Treat boolean `true` and string `"true"` as suppression, matching existing iframe boolean parsing behavior.
- Preserve current recording behavior when the parameter is omitted, `false`, or `"false"`.
- Reuse the existing preview recording gate so nested previews and list snapshot suppression remain consistent.
- Keep task tracking metadata intact when recording is not suppressed.

**Non-Goals:**

- Do not add a backend API flag or change HTML preview event payload schema.
- Do not change URL `origin=Y` initialization unless a future requirement explicitly asks for URL parameter support.
- Do not disable unrelated analytics outside HTML preview click and list snapshot recording.

## Decisions

1. Store `skipPreviewTracking` in `IframeContext`.

   Rationale: iframe `USER_DATA` parameters already flow through `iframeStore` and are persisted in session storage. Storing the flag there makes refresh behavior consistent with other iframe context fields and avoids a separate event bus.

   Alternative considered: read the raw message only in `iframeMessage.ts` and set a module global. That would be less observable from React and easier to lose on refresh.

2. Wire suppression through `HtmlPreviewTrackingProvider` in Chat.

   Rationale: `FilePreviewModal` already suppresses real reporters when `disableEventRecording` is true. Feeding iframe context into the provider keeps the recording decision at one established boundary and avoids duplicating API guards in `htmlPreviewEventsApi`.

   Alternative considered: make `htmlPreviewEventsApi.recordClick` no-op when iframe context says skip. That would hide the behavior inside an API layer used by reporting pages too, and would be harder to combine with explicit preview contexts.

3. Use OR semantics with existing suppression.

   Rationale: Any explicit suppression source should win. Read-only replay remains suppressed through its provider. Chat suppresses when `skipPreviewTracking` is true. Omitted or false iframe values preserve normal chat and task auto-preview recording.

## Risks / Trade-offs

- [Risk] Persisting the flag in session storage can keep suppression after a refresh until a later `USER_DATA` message updates it. → Mitigation: this matches the existing iframe context persistence model; false or omitted values reset to normal when the parent sends fresh context.
- [Risk] The short name could sound broader than HTML preview only. → Mitigation: document it in iframe types and scope the implementation to the HTML preview tracking provider, not global analytics.
