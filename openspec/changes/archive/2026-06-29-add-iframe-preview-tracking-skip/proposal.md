## Why

Embedded parent applications need a lightweight way to open Console chat previews without contributing HTML preview click or list snapshot analytics. The existing read-only replay suppression covers operations replay, but iframe `USER_DATA` contexts still always keep normal preview recording behavior.

## What Changes

- Add a `skipPreviewTracking` boolean-style parameter to iframe `USER_DATA.data`.
- When `skipPreviewTracking` is `true` or `"true"`, HTML preview click and list snapshot recording is suppressed for previews opened in the embedded Console session.
- When `skipPreviewTracking` is omitted, `false`, or `"false"`, existing recording behavior is preserved.
- Preserve HTML preview interactions such as nested preview opening while suppressing only analytics recording.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `html-preview-event-recording`: add iframe-driven suppression for HTML preview click and list snapshot recording.

## Impact

- Frontend iframe message contract: `console/src/types/iframe.ts`
- Frontend iframe context store and message handling: `console/src/stores/iframeStore.ts`, `console/src/utils/iframeMessage.ts`
- Chat HTML preview tracking context wiring: `console/src/pages/Chat/index.tsx`
- Existing HTML preview modal recording gate and focused tests
