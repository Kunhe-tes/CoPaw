# Managed Batch Retry Tracing Implementation Plan

> **For agentic workers:** Use Superpowers test-driven development and verification before completion. Follow the repository's sequential execution convention.

**Goal:** Record retry blocks caused by individual task pauses and let operators trace a batch execution by ID.

**Architecture:** Write a deduplicated dispatch event in the existing auto-retry transaction. Reuse the managed Monitor detail API, event scope, and Console data models.

## Scheduler

- [x] In `tests/unit/scheduler/test_managed_batch_auto_retry.py`, verify that both unread pause and manual task disable record one block event for a settled Prompt failure across repeated scans and leave the original attempt in place.
- [x] In `managed/auto_retry.py`, `managed/batch_failures.py`, and `managed/dispatch_events.py`, record the event for an otherwise retry-eligible current attempt while its task has either pause reason.

## Monitor and Console

- [x] In `test_managed_board_api.py`, verify the batch detail endpoint applies the execution ID filter to both event count and results, together with the event type filter.
- [x] In `models/managed_board.py` and `services/cron/managed_board.py`, accept a bounded execution ID and match it within the current source and batch before pagination.
- [x] In `BatchDetail.test.tsx`, cover the member execution ID, blocked-event reason and server-side event filter. Update `BatchDetail.tsx` and the retry receipt in `index.tsx`. Reuse the existing execution ID column in the attempt history.

## Verification

- [x] Run targeted Scheduler and Monitor pytest suites and ManagedBatchDispatch Vitest suites. Check TypeScript, changed-file lint, and the diff.
- [x] Verify the changed layout and search interaction in an available browser, and report Chromium 108 availability. Chromium 142 passed at 1440×900 and 1280×720 with the latter using `hideMenu=true`. Chromium 108 was unavailable.
