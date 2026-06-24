## 1. Impact Analysis and Test Baseline

- [x] 1.1 Run GitNexus impact analysis for the backend symbols that will be edited: `CronManager._register_system_jobs`, `CronManager.register_dream`, `internal_cron_callback`, `SafeJSONSession.save_merged_state`, and source system config registry helpers.
- [x] 1.2 Run GitNexus impact analysis for the Console system config page modules that will be edited.
- [x] 1.3 Add failing backend tests for cleanup config defaults, validation, and resolver behavior.
- [x] 1.4 Add failing backend tests for external scheduler system-job registration, disabled-job pause behavior, and internal callback dispatch.
- [x] 1.5 Add failing backend tests for filesystem session pruning, malformed-history preservation, derived job meta recomputation, and session write locking.
- [x] 1.6 Add failing Console registry/page tests for cleanup defaults, time-to-cron conversion, validation, and save payload preservation.

## 2. Source System Config

- [x] 2.1 Extend the source system config registry to support the cleanup settings: `enabled`, `retention_days`, and daily `cron`.
- [x] 2.2 Add cleanup config normalization and validation so retention is positive and cron is limited to `<minute> <hour> * * *`.
- [x] 2.3 Add a resolver for effective cleanup config with defaults `enabled=false`, `retention_days=30`, and `cron="0 1 * * *"`.
- [x] 2.4 Update backend source system config tests until the new config behavior passes.

## 3. Scheduler Integration

- [x] 3.1 Add a cleanup system job id and register/update/pause logic following the heartbeat/dream external scheduler pattern.
- [x] 3.2 Extend system-job registration so cleanup is refreshed during CronManager initialization.
- [x] 3.3 Add internal callback dispatch for the cleanup `task_type` without requiring a business `job_id`.
- [x] 3.4 Ensure cleanup system jobs are stored only in `system_jobs.json` and never in business `jobs.json`.
- [x] 3.5 Update scheduler and callback tests until they pass.

## 4. Filesystem Session Cleanup

- [x] 4.1 Add a per-task-session write lock shared by cron task session save and cleanup.
- [x] 4.2 Implement task session pruning by `task_runs[].ended_at` and matching `agent.memory.content` ranges.
- [x] 4.3 Implement `task_messages` pruning only for messages with reliable timestamps.
- [x] 4.4 Preserve malformed or time-ambiguous records and log skipped counts.
- [x] 4.5 Reduce fully expired sessions to minimal history while keeping business task/chat/session bindings outside the session file.
- [x] 4.6 Recompute only derived job metadata after cleanup and preserve identity, binding, schedule, notification, model/source, enabled, and pause fields.
- [x] 4.7 Update cleanup tests until they pass.

## 5. Console Configuration UI

- [x] 5.1 Extend the SystemConfigPage registry with cleanup defaults, read/write helpers, daily time conversion, and validation.
- [x] 5.2 Add a SystemConfigPage card for the cleanup switch, retention days, and daily run time.
- [x] 5.3 Preserve unknown raw source config keys when saving cleanup changes.
- [x] 5.4 Update Console tests until the new cleanup UI and registry behavior pass.

## 6. Verification

- [x] 6.1 Run targeted backend pytest files for source system config, cron scheduler integration, internal callback dispatch, and task session cleanup.
- [x] 6.2 Run targeted Console tests for `SystemConfigPage` registry/page behavior.
- [x] 6.3 Run `openspec.cmd validate add-cron-task-session-cleanup --strict`.
- [x] 6.4 Run GitNexus `detect_changes()` before any commit or final implementation handoff.
- [x] 6.5 Review the diff for scope drift and update OpenSpec artifacts if implementation changes the agreed behavior.
