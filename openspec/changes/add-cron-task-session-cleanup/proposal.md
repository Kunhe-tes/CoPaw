## Why

Scheduled task sessions can accumulate long-running filesystem history through repeated cron executions, increasing workspace storage usage while most old task run details have low operational value. The system needs a source-scoped, administrator-controlled cleanup policy that reduces task session history without deleting tasks or audit records.

## What Changes

- Add a source system config section for scheduled task session cleanup with defaults:
  - `cron_task_session_cleanup.enabled=false`
  - `cron_task_session_cleanup.retention_days=30`
  - `cron_task_session_cleanup.cron="0 1 * * *"`
- Register cleanup as an external scheduler system job that runs daily at the configured time.
- Clean only filesystem task session history older than the configured retention window.
- Preserve business cron jobs, chat/session bindings, monitor records, tracing records, and execution audit data.
- Recompute only derived scheduled-task display metadata after cleanup.
- Coordinate cleanup and cron task session saves with a per-task-session write lock so currently running tasks do not permanently prevent cleanup and do not race session writes.
- Keep malformed or time-ambiguous history records rather than guessing deletion eligibility.
- Extend the current source system config page to manage the cleanup switch, retention days, and daily run time.

## Capabilities

### New Capabilities

- `cron-task-session-cleanup`: Source-scoped daily cleanup of scheduled task filesystem session history.

### Modified Capabilities

- `current-source-system-config-page`: Manage the scheduled task session cleanup configuration for the active source.

## Impact

- Backend source system config registry, validation, and effective config resolution.
- Cron system job registration and internal scheduler callback dispatch.
- Task session filesystem state pruning and session save locking.
- Scheduled-task job metadata recomputation for derived UI fields.
- Console system config page registry, validation, and UI controls.
- Unit tests for config defaults/validation, cleanup pruning, scheduler registration, callback dispatch, and Console registry behavior.
