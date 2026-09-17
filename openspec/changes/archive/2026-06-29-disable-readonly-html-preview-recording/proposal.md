## Why

Operations users can open another user's read-only conversation history from the business overview and interact with auto-preview HTML reports. Those interactions currently reuse the same preview tracking path as normal chat, so operational inspection can pollute customer-manager click and view statistics.

## What Changes

- Add a read-only preview recording guard for the business overview user detail conversation replay.
- Preserve HTML preview interactivity, including nested preview links, while suppressing event recording in the guarded read-only context.
- Keep normal chat, scheduled task, and generated auto-preview statistics unchanged.
- Ensure both HTML click events and list snapshot/view recording are disabled when the read-only guard is active.
- Add regression coverage proving the guard suppresses recording only for operations read-only replay.

## Capabilities

### New Capabilities

- `html-preview-event-recording`: Defines when HTML preview click and list snapshot events must be recorded or suppressed across normal chat, task auto-preview, and read-only operations replay.

### Modified Capabilities

- None.

## Impact

- Affected frontend code:
  - `console/src/components/agentscope-chat/HtmlPreviewTrackingContext.tsx`
  - `console/src/components/agentscope-chat/FilePreviewModal/index.tsx`
  - `console/src/pages/Analytics/BusinessOverview/components/UserDetailModal/ReadOnlySessionChat.tsx`
- Affected tests:
  - HTML preview modal/tracking tests for event suppression and preserved nested preview behavior.
  - Business overview read-only session chat tests for provider scoping.
- No backend API or schema changes are expected.
- No visual design changes are expected.
