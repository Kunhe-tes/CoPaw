# Worker Capacity Event Carousel

## Scope

- Keep the current-capacity snapshot unchanged.
- Replace the eight-row recent adjustment history with one visible adjustment record at a time.
- Keep the visible record expandable so its existing detailed fields remain available.
- Add accessible previous/next controls and a current-position indicator.
- Disable navigation at the oldest/newest boundaries and reset to the newest record when refreshed data changes.
- Preserve the existing Monitor API contract and the eight-record client display limit.

## Implementation Steps

1. Extend the existing Cron batch-dispatch page test fixture to contain multiple capacity events.
2. Add a failing interaction test proving only the newest event is initially visible, navigation changes the visible event, boundary controls disable correctly, and the selected event still expands.
3. Add a focused `CapacityEventHistory` component that owns the visible history index and renders one existing `CapacityEventRow`.
4. Add compact responsive styles for the position label and icon navigation controls.
5. Run the targeted Vitest file, formatting checks, TypeScript/build verification as feasible, and GitNexus change detection.

## Verification

- Expected red test before implementation: the recent-adjustment section renders more than one event and has no previous/next controls.
- Expected green test after implementation: one event is visible at a time; previous/next navigation, boundary states, refresh reset, and detail expansion work.
- `cd console; .\node_modules\.bin\vitest.cmd run src/pages/Monitor/CronBatchDispatch/index.test.tsx`
- `cd console; .\node_modules\.bin\prettier.cmd --check src/pages/Monitor/CronBatchDispatch/index.tsx src/pages/Monitor/CronBatchDispatch/index.module.less src/pages/Monitor/CronBatchDispatch/index.test.tsx`
- `cd console; npm run build`
- GitNexus `detect_changes` for the final uncommitted diff.
