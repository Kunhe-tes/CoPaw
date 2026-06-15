## Context

Scheduled task runs currently append filesystem session state under the task session id. Cron execution records, monitor synchronization, and tracing retention already have separate storage and retention behavior, so this change targets only task session JSON history.

System feature configuration is source-scoped through `source_system_config`. Heartbeat and dream already use the external scheduler platform as system jobs stored in `system_jobs.json`, while business cron jobs are stored in `jobs.json`. The cleanup job should follow the system-job pattern, not the business-job pattern.

Task session saves currently read existing state, append the current run memory and `task_runs`, then write the merged JSON back. Cleanup must therefore coordinate with the same session write path to avoid lost updates.

## Goals / Non-Goals

**Goals:**

- Add a source-scoped scheduled task session cleanup policy that is disabled by default.
- Run cleanup once per day through the external scheduler platform.
- Keep at most one cleanup scheduler job per source when different users edit the same source config.
- Apply each cleanup callback to all users bound to the callback source.
- Delete only expired filesystem task session history.
- Preserve business tasks, chat/session bindings, monitor records, tracing records, and execution audit data.
- Keep cleanup safe around currently running tasks by serializing per-session writes.
- Keep the current-source system config page as the only administrator UI for this policy.

**Non-Goals:**

- Do not clean `swe_cron_executions`, monitor tables, tracing stores, or token usage data.
- Do not delete business cron jobs or task chats.
- Do not auto-resume tasks paused by unread auto-pause.
- Do not introduce arbitrary cron scheduling for cleanup; the policy is daily with configurable run time.

## Decisions

### Use `source_system_config` as the source of truth

The cleanup policy is a system feature setting scoped to the current source, so it belongs in `source_system_config` alongside the existing source-level switches and numeric controls.

Alternatives considered:

- Tenant `config.json`: rejected because it would create a second source of truth for source-scoped behavior.
- Per-job metadata: rejected because cleanup is an administrative retention policy, not a business-task setting.

### Store daily run time as a scheduler cron

The persisted config uses `cron_task_session_cleanup.cron` with a five-field daily cron such as `0 1 * * *`. The Console presents this as a daily time control and converts it to the stored cron form.

Alternatives considered:

- Store `run_time="01:00"`: easier for the UI, but every scheduler registration path would still need cron conversion.
- Allow arbitrary cron: rejected because the requirement is daily cleanup, and arbitrary schedules make storage deletion cadence harder to reason about.

### Register cleanup as an external system job

Cleanup registration extends the heartbeat/dream system-job pattern. The job id is stored in source-scoped system job id storage, callback dispatch uses `task_type="cleanup"`, enabled config registers or updates the external system job, and disabled config pauses the external job instead of writing anything to business `jobs.json`.

The callback payload still carries `tenant_id` because the scheduler platform and existing callback contract include it, but cleanup does not use that field as the deletion boundary. For cleanup, `source_id` is the boundary: the internal callback lists all logical tenants bound to that source, resolves each tenant/source pair to its runtime scope, and invokes that tenant's CronManager cleanup runner.

Heartbeat and dream continue to use the current manager's `system_jobs.json`. Cleanup uses source-level external job id storage so a second user saving the same source config can update the existing scheduler job instead of creating another one.

Alternatives considered:

- Internal background loop: rejected because existing heartbeat/dream scheduling is already delegated to the scheduler platform.
- Business cron job: rejected because it would appear in user task surfaces and participate in business task semantics.

### Prune only reliable expired history

Cleanup uses `task_runs[].ended_at` as the retention timestamp. Runs with missing or unparsable timestamps, invalid memory ranges, or ambiguous structure are preserved and logged. `task_messages` are pruned only when their timestamps are reliable.

Alternatives considered:

- Use chat `updated_at`: rejected because one recent run would keep all old runs.
- Force-delete malformed records: rejected because old or partially written session formats could be corrupted.

### Coordinate session writes by task session id

Cron task save and cleanup both acquire the same per-task-session write lock. Cleanup does not skip an entire task merely because a run is active; it only waits for or skips sessions whose write lock cannot be acquired within a short timeout.

Alternatives considered:

- Skip running jobs entirely: rejected because tasks scheduled at the cleanup time could be skipped indefinitely.
- No locking: rejected because cleanup and run completion could overwrite each other's session state.

### Recompute only derived task metadata

After pruning, cleanup updates only UI-derived job metadata: `task_has_scheduled_result`, `task_last_scheduled_preview`, `task_last_scheduled_run_at`, and `task_unread_execution_count`. It preserves task identity, binding, business schedule, notification, model/source configuration, and pause fields.

Alternatives considered:

- Leave metadata untouched: rejected because the task list would display stale previews and unread counts for deleted history.
- Clear pause state when unread becomes zero: rejected for the first version to avoid changing task execution state as a side effect of storage cleanup.

## Risks / Trade-offs

- [Risk] Per-process locks do not coordinate multiple application instances writing the same filesystem session. -> Mitigation: use filesystem-level locking where available for the session JSON path, or ensure the lock implementation covers the deployed shared storage model before enabling multi-instance cleanup.
- [Risk] A manager may expect the cleanup job immediately after enabling the switch. -> Mitigation: current-source config saves refresh the current Agent system-job registration, and manager initialization still reconciles the job on restart.
- [Risk] Malformed old sessions may still consume storage. -> Mitigation: preserve them in the first version and log counts so a later migration can target known legacy shapes.
- [Risk] Updating source config may not immediately refresh the external scheduler job. -> Mitigation: registration refresh should run on manager initialization and after relevant config saves, or the callback should self-disable when effective config is disabled.

## Migration Plan

- Add default config values through the registry so sources without explicit records inherit cleanup disabled with a 30-day retention value and 01:00 daily run time.
- Register or update the system cleanup job on CronManager initialization only when the effective config is enabled.
- Refresh the current Agent cleanup system job after current-source config saves so turning the switch on creates the external scheduler job without waiting for restart.
- When config is disabled, pause the existing external scheduler job and keep its id for future re-enable.
- Rollback by disabling the source config switch; already-pruned filesystem history is not restored.

## Open Questions

None. The current agreed scope is ready for implementation.
