# Managed Worker Occupancy Implementation Plan

> **For agentic workers:** Follow the repository's sequential execution convention, with test-first changes and verification before completion.

**Goal:** Show current shared Worker occupants and plot sampled occupancy alongside effective capacity in the managed batch board.

**Architecture:** Reuse the Scheduler occupancy predicates and existing capacity samples. Add one scoped read endpoint and leave dispatch and database schemas unchanged.

## Current occupancy

- [x] In `tests/unit/scheduler/test_managed_board_api.py`, verify role and Source scope, legacy and managed occupancy, queued exclusion, pool filtering, metadata and totals on an empty page.
- [x] Add the query to `monitor/src/monitor/app/services/cron/managed_board_occupancy.py` and the manager-protected route to `monitor/src/monitor/app/routers/managed_cron_board.py`. Return page and count from the same statement. Use the managed execution snapshot and the matching legacy intent attempt for metadata and start time.

## Console

- [x] In `console/src/pages/Monitor/CronBatchDispatch/workerHistory.test.ts`, cover sampled occupancy, zero values and gaps at unsampled baseline records.
- [x] In the managed board API client and `WorkerOccupants.tsx`, load current occupancy independently of the date range. Show the total, a refresh control, model filter, and paged task details.
- [x] In `SharedWorkers.tsx` and the shared chart, show occupancy only on the managed board. Match column edges while charts are collapsed. Let the right panel expand independently and keep the narrow layout stacked.

## Verification

- [x] Run managed board pytest tests, targeted Console Vitest, typecheck and changed-file lint. Chromium 142 verified alignment and interactions with ordinary and embedded layouts at 1440×900, 1280×720, and 1024×720. Chromium 108 and the deployed MySQL instance were unavailable.
