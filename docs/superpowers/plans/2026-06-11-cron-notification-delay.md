# Cron Notification Delay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable automatic scheduled-job notification delay across backend timing, CLI creation, and Console create/edit/display surfaces.

**Architecture:** Store the delay as `meta.notification_delay_minutes`, normalize it at the cron execution-to-Monitor boundary, and keep Monitor claim logic unchanged. Frontend forms collect value plus minute/hour unit and convert to stored minutes.

**Tech Stack:** Python Click CLI, FastAPI cron backend, Pydantic cron job models, React/TypeScript Console, Vitest, pytest, OpenSpec.

---

### Task 1: Backend Notification Timing

**Files:**
- Modify: `src/swe/app/crons/manager.py`
- Modify: `src/swe/app/crons/api.py`
- Test: `tests/unit/app/test_cron_manager_completed_cancellation.py`
- Test: `tests/unit/app/test_tenant_cron_api.py`

- [ ] **Step 1: Write failing tests**

Add tests that call `_sync_execution_to_monitor()` with:
- normal automatic job and `meta.notification_delay_minutes = 120`, expecting `notification_due_at = actual_time + 120 minutes`
- manual job with the same metadata, expecting `notification_due_at is None`
- automatic broadcast child with `broadcast_offset_minutes = 20` and `notification_delay_minutes = 120`, expecting `actual_time + 140 minutes`
- invalid metadata such as `-5` or `"bad"`, expecting no custom delay

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/app/test_cron_manager_completed_cancellation.py -q`
Expected: new tests fail before implementation.

- [ ] **Step 2: Implement backend normalization**

Add a small helper near the cron manager notification code that returns an integer delay in `[0, 10080]` from `job.meta["notification_delay_minutes"]`. In `_sync_execution_to_monitor()`, apply this delay only when `exec_status == "success"` and `is_manual` is false. For broadcast jobs, add it to the existing `broadcast_offset_minutes` branch.

- [ ] **Step 3: Verify backend tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/app/test_cron_manager_completed_cancellation.py tests/unit/app/test_tenant_cron_api.py -q`
Expected: all selected tests pass.

### Task 2: CLI Creation Flag

**Files:**
- Modify: `src/swe/cli/cron_cmd.py`
- Test: `tests/unit/cli/test_cron_cmd.py` or nearest existing CLI cron test file

- [ ] **Step 1: Write failing CLI payload tests**

Test `_build_payload_from_args()` or `_build_spec_from_cli()` with omitted delay and explicit `120`, asserting `payload["meta"]["notification_delay_minutes"]`.

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/cli -q`
Expected: new tests fail before implementation.

- [ ] **Step 2: Implement CLI flag**

Add `--notification-delay-minutes` to `swe cron create`, default it to `0`, validate as integer range `0..10080`, and pass it into inline payload construction. JSON-file creation remains unchanged except files can already include the meta field.

- [ ] **Step 3: Verify CLI tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/cli -q`
Expected: selected CLI tests pass.

### Task 3: Console Forms And Display

**Files:**
- Modify: `console/src/utils/cron.ts`
- Modify: `console/src/components/ScheduledTaskPopup/index.tsx`
- Modify: `console/src/components/ScheduledTaskPopup/index.module.less`
- Modify: `console/src/pages/Control/CronJobs/helpers.ts`
- Modify: `console/src/pages/Control/CronJobs/components/JobDrawer.tsx`
- Modify: `console/src/pages/Control/CronJobs/components/columns.tsx`
- Modify: `console/src/pages/Control/CronJobs/components/constants.ts`
- Modify: `console/src/api/types/cronjob.ts`
- Test: `console/src/utils/cron.test.ts`
- Test: `console/src/components/ScheduledTaskPopup/index.test.tsx`
- Test: `console/src/pages/Control/CronJobs/helpers.test.ts`

- [ ] **Step 1: Write failing frontend tests**

Add tests for:
- quick popup calling `onConfirm` with a converted delay when user enters `2` and selects hours
- `buildCronJobSpec()` storing `meta.notification_delay_minutes`
- Cron Jobs helper hydrating `120` as `2 hours`
- Cron Jobs helper submitting `2 hours` as `120`
- list formatter rendering `2 hours`

Run: `cd console; npm.cmd run test:run -- src/utils/cron.test.ts src/components/ScheduledTaskPopup/index.test.tsx src/pages/Control/CronJobs/helpers.test.ts`
Expected: new tests fail before implementation.

- [ ] **Step 2: Implement frontend conversion helpers**

Add shared helpers to normalize stored minutes, convert from UI value/unit, choose edit unit, and format display text. Keep default as `0 minutes`.

- [ ] **Step 3: Implement UI controls**

Add numeric input plus unit select to the quick popup and Cron Jobs drawer. Pass the converted minutes into `meta.notification_delay_minutes`. Add a list column showing `Immediately`, `<n> minutes`, or `<n> hours`.

- [ ] **Step 4: Verify frontend tests**

Run: `cd console; npm.cmd run test:run -- src/utils/cron.test.ts src/components/ScheduledTaskPopup/index.test.tsx src/pages/Control/CronJobs/helpers.test.ts`
Expected: all selected Vitest tests pass.

### Task 4: Final Validation

**Files:**
- Modify: `openspec/changes/add-cron-notification-delay/tasks.md`

- [ ] **Step 1: Run OpenSpec validation**

Run: `openspec.cmd validate add-cron-notification-delay --strict`
Expected: validation passes.

- [ ] **Step 2: Run GitNexus change detection**

Run `detect_changes({scope: "all", repo: "CoPaw"})` and review impacted symbols and processes.

- [ ] **Step 3: Review final diff**

Run: `git diff --stat` and `git diff --check`
Expected: changed files match this plan and no whitespace errors are reported.
