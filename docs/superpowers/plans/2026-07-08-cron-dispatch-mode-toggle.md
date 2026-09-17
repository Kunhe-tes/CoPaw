# Cron Dispatch Mode Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move normal/batch dispatch selection into the cron distribution dialog and make both modes use the same offset window.

**Architecture:** Keep the existing broadcast dialog as the single distribution entry. Add a dispatch mode segmented control in the dialog; on confirm, apply the selected scheduler mode through the existing batch-dispatch enable/disable API, then run the existing broadcast flow with the same offset options.

**Tech Stack:** React, TypeScript, Vitest, FastAPI/Pydantic existing cron APIs.

---

### Task 1: Frontend Tests

**Files:**
- Modify: `console/src/pages/Control/CronJobs/index.test.tsx`
- Modify: `console/src/pages/Control/CronJobs/components/columns.test.tsx`

- [x] Add mocks for `enableCronBatchDispatch` and `disableCronBatchDispatch`.
- [x] Add a page test that opens the distribution dialog, selects batch mode, changes the offset window, confirms, and asserts `enableCronBatchDispatch(jobId, { offset_window_hours })` runs before `broadcastCronJob(..., { enable_offset, offset_window_hours })`.
- [x] Update column tests so the action menu no longer contains `batch_dispatch`.

### Task 2: Dialog Mode Toggle

**Files:**
- Modify: `console/src/pages/Control/CronJobs/index.tsx`

- [x] Import `Segmented`.
- [x] Add `broadcastDispatchMode: "normal" | "batch"` state.
- [x] Default the mode from `job.meta.broadcast_dispatch_intents_enabled` when opening the dialog.
- [x] In confirm, call `enableCronBatchDispatch` or `disableCronBatchDispatch` with the same offset window before broadcasting.
- [x] Keep the offset switch/window controls shared between both modes.

### Task 3: Remove List Entry

**Files:**
- Modify: `console/src/pages/Control/CronJobs/components/columns.tsx`
- Modify: `console/src/pages/Control/CronJobs/useCronJobs.ts`

- [x] Remove the `batch_dispatch` menu item from row actions.
- [x] Stop passing `onToggleBatchDispatch` from the page to column handlers if unused.
- [x] Leave API helpers in place because the dialog uses them directly.

### Task 4: Verification

**Commands:**
- [x] `cd console; .\node_modules\.bin\vitest.cmd run src/pages/Control/CronJobs/index.test.tsx src/pages/Control/CronJobs/components/columns.test.tsx`
- [x] `git diff --check -- console/src/pages/Control/CronJobs/index.tsx console/src/pages/Control/CronJobs/components/columns.tsx console/src/pages/Control/CronJobs/index.test.tsx console/src/pages/Control/CronJobs/components/columns.test.tsx`
- [x] `node .gitnexus/run.cjs detect_changes`
