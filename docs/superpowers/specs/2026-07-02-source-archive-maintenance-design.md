# Source Archive Maintenance Design

## Context

File governance currently runs archive maintenance as a side effect of dream execution. After `CronManager.run_dream()` finishes dream memory optimization, it calls `run_dream_archive_maintenance()`, which archives old orphan files and purges expired archive files in the same maintenance pass. This couples file governance to agent-level dream scheduling and lets automatic work delete archived files.

The target behavior is to separate these responsibilities:

- dream cron keeps its current dream-only behavior.
- orphan file archive maintenance becomes a source-level scheduled task and is enabled by default.
- archived file deletion is never automatic and can only be triggered manually by an administrator.
- archive maintenance settings are configured from the System Settings -> System Feature Configuration page, which maps to source system config.

## Goals

- Register a default-on source-level archive maintenance task for each source.
- Configure archive maintenance enablement and daily execution time in source system config.
- Scan all tenant workspaces under the source, including all valid agent workspaces for each tenant.
- Archive orphan files that have not been modified for the configured threshold, defaulting to 3 days.
- Preserve existing archive indexes and continuous-governance read model writes.
- Keep purge as a manual admin action only.
- Avoid starting agent runtimes for archive maintenance.
- Bound filesystem and database work so large sources do not create I/O spikes.

## Non-Goals

- Do not change dream memory optimization behavior beyond removing archive side effects.
- Do not automatically purge archived files from any scheduled task.
- Do not recursively scan archive file storage during normal purge.
- Do not add organization, BBK, tenant, or agent overrides for archive maintenance in this change.
- Do not repair orphaned archive files whose physical files exist without metadata; that remains a separate administrator repair workflow.

## Source System Config

Add a new source system config section named `archive_maintenance`.

```json
{
  "archive_maintenance": {
    "enabled": true,
    "cron": "0 3 * * *",
    "old_orphan_days": 3,
    "max_workspaces_per_run": 200,
    "max_files_per_workspace": 100,
    "max_files_per_run": 5000,
    "timeout_seconds": 900
  }
}
```

The System Feature Configuration page exposes:

- an enable switch bound to `archive_maintenance.enabled`;
- a daily execution time selector bound to `archive_maintenance.cron` through the existing `HH:mm <-> cron` conversion pattern;
- optional numeric advanced limits if the implementation chooses to expose them immediately.

The user-facing control is "daily execution time". The persisted backend value is `cron` so the scheduler can consume the same shape used by `cron_task_session_cleanup`. The initial default is 03:00 every day.

Backend defaults are registered in `src/swe/app/source_system_config/registry.py` so `DEFAULT_SOURCE_SYSTEM_CONFIG` includes archive maintenance. Runtime access should be provided by a resolver in `src/swe/app/source_system_config/runtime.py`, for example `resolve_archive_maintenance_config()`, returning a typed object with the effective enabled flag, cron, threshold, and limits.

## Scheduler Design

Extend `SourceSystemTaskScheduler` with a second source-level task type.

New constants:

- `SOURCE_ARCHIVE_MAINTENANCE_JOB_ID = "_source_archive_maintenance"`
- `SOURCE_ARCHIVE_MAINTENANCE_NAME = "archive_maintenance"`
- scheduler callback `task_type = "archive_maintenance"`

New methods:

- `refresh_archive_maintenance(source_id, config, identity)`
- `run_archive_maintenance(source_id)`

`refresh_archive_maintenance()` mirrors `refresh_task_session_cleanup()`:

- resolve `archive_maintenance` from source system config;
- if disabled, pause the existing external scheduler job and persist `enabled=false`;
- if enabled, register or update an external source-level job using the configured cron;
- persist the external job binding in `swe_source_system_task_binding`.

`run_archive_maintenance()` is different from task-session cleanup: it must not call `multi_agent_manager.get_agent()`. It reads tenant rows from the tenant init source store, resolves source-scoped tenant directories, enumerates workspace directories, and calls file-governance helpers directly.

## Runtime Flow

1. A manager saves System Feature Configuration for the current source.
2. The source config service stores the config and refreshes source-level scheduler bindings.
3. The external scheduler calls the internal cron callback with `task_type=archive_maintenance` and `source_id`.
4. The internal router dispatches to `SourceSystemTaskScheduler.run_archive_maintenance(source_id)`.
5. The scheduler reads source tenants from `swe_tenant_init_source`.
6. For each tenant, it resolves the runtime tenant directory with `resolve_runtime_tenant_id(tenant_id, source_id)`.
7. For each valid workspace under `workspaces/*`, it scans orphan candidates.
8. It archives candidates older than `old_orphan_days` until limits are reached.
9. It writes local archive metadata and continuous-governance read-model rows.
10. It returns a summary with counts, skipped work, errors, and whether limits stopped the run early.

The task summary shape should include:

- `source_id`
- `scopes_seen`
- `workspaces_seen`
- `workspaces_processed`
- `workspaces_failed`
- `files_seen`
- `files_archived`
- `files_skipped`
- `bytes_archived`
- `limit_reached`
- `errors`

## Archive Semantics

Archive maintenance reuses the existing orphan-file rules:

- skip root keep files such as `AGENTS.md`, `HEARTBEAT.md`, `dream_logs.json`, and `agent.json`;
- skip root keep directories such as `memory`, `sessions`, `backup`, `skills`, and `governance`;
- skip hidden files and hidden directories;
- skip paths in `governance/archive/protected_paths.json`;
- only archive regular files;
- move the file to `governance/archive/files/{archive_item_id}`;
- append metadata to `governance/archive/index.json`.

Scheduled archive maintenance uses:

- `archived_by = "source_archive_maintenance"`
- `archive_reason = "source_auto_mtime_3_days"` unless the threshold is changed, in which case the reason should include the configured day count.

The implementation should split the current combined maintenance behavior into separate operations:

- `archive_old_orphans_for_workspace(...)`: archive only;
- `purge_archive_items_for_workspace(...)`: purge only, used by manual APIs;
- `run_source_archive_maintenance(...)`: source-level orchestration.

Dream execution should no longer call archive maintenance after dream memory completes.

## Manual Purge Semantics

Archived file deletion remains manual. The existing admin purge endpoint may continue to support:

- selected archive item purge;
- expired archive purge across source workspaces.

Normal purge must read metadata instead of recursively scanning archive storage:

- use `governance/archive/index.json` and read-model rows to find candidate archive item IDs;
- map each `archive_item_id` to `archive_path`;
- delete only the referenced file path;
- remove the item from local index;
- delete the read-model row;
- write cleanup audit.

The report can continue to show pending purge files, including files whose `archived_at` is older than 10 days. No scheduled path may call purge.

An optional follow-up can add a purge preview API that returns candidate count and total bytes before deletion. That preview should still read metadata, not recursively scan physical archive files.

## Performance Controls

The scheduled archive path must be bounded:

- Do not instantiate `Workspace`, `AgentRunner`, `CronManager`, or memory manager.
- Query source tenant rows once at the start.
- Enumerate workspace directories from disk without starting agent runtimes.
- Skip known high-volume keep directories before recursion.
- Stop after `max_workspaces_per_run`.
- Stop after `max_files_per_workspace` per workspace.
- Stop after `max_files_per_run` globally.
- Stop when `timeout_seconds` is reached.
- Write archive index only when at least one file was archived.
- Batch continuous-governance read-model writes by workspace or small batches.

If limits are reached, the result should set `limit_reached=true`. The next scheduled run continues from the remaining filesystem state; no explicit cursor is required for the first implementation.

## Error Handling

- A failed workspace does not fail the whole source task.
- Missing files during scan or move are skipped because another process may have moved or deleted them.
- Invalid tenant or agent directory names are skipped and recorded.
- A damaged archive index causes that workspace to be skipped; the task must not guess and overwrite the index.
- File move success plus DB write failure leaves local metadata as the source of truth and records reconcile health.
- External scheduler registration failure is logged and returned from the refresh operation; it must not corrupt source config.
- Manual purge returning a missing archive item remains an explicit 404 or partial failure. It must not recursively search for files to delete.

## UI Design

In `console/src/pages/SystemConfigPage`, extend the existing scheduled task settings card with an "archive maintenance" section.

Controls:

- switch: "Source archive maintenance";
- select: "Daily run time", disabled when the switch is off;
- optional numeric inputs for old orphan days and limits if exposed.

The page should preserve unknown source config keys and follow the existing save/delete/inheritance behavior. It should use the same `dailyRunTimeToCron()` and `cronToDailyRunTime()` helpers currently used for task-session cleanup.

The Dream/Agent config page should not expose this setting; `running.memory_summary.dream_cron` remains only for dream memory optimization.

## API and Callback Changes

Internal callback dispatch should recognize `task_type=archive_maintenance` and route to source task scheduler. It should require `source_id`, just like source task-session cleanup.

No new public admin route is required for scheduled execution. Existing source system config APIs remain the management surface for enablement and execution time.

The dream logs router can keep manual archive and purge endpoints, but shared file-governance logic should move behind helpers to avoid source scheduler importing large router-only behavior.

## Migration and Defaults

Because source system config merges registered defaults, existing sources inherit:

- `archive_maintenance.enabled = true`
- `archive_maintenance.cron = "0 3 * * *"`
- `archive_maintenance.old_orphan_days = 3`
- conservative limits

On startup or source config refresh, enabled sources register the source-level scheduler job. If no external scheduler adapter is configured, registration behaves as it does for existing source-level tasks: no scheduled execution happens, but the configuration remains valid.

No data migration is required for existing archive indexes or read-model rows.

## Tests

Backend tests:

- source config defaults include `archive_maintenance`;
- source config normalization accepts enabled, cron, threshold, and limit values;
- runtime resolver returns default and overridden archive maintenance config;
- scheduler registers, updates, pauses, and persists archive maintenance bindings;
- internal callback routes `archive_maintenance` to source task scheduler and requires `source_id`;
- source archive maintenance scans all tenants under the source;
- source archive maintenance scans all valid agent workspaces under each tenant;
- scheduled archive maintenance archives old orphan files and does not purge expired archive items;
- protected paths, keep paths, hidden paths, and missing files are skipped;
- limits and timeout stop the run and mark `limit_reached`;
- DB dual-write failures record reconcile health without undoing file moves;
- dream cron no longer invokes archive maintenance;
- manual purge deletes by metadata path and does not recursively scan archive files.

Frontend tests:

- System Feature Configuration renders the archive maintenance switch and daily run-time selector;
- editing the run time writes `archive_maintenance.cron`;
- disabling archive maintenance keeps values but disables the time control;
- save payload preserves unrelated source config keys.

## Decisions

- The first UI release exposes only enablement and daily execution time. Advanced limits remain backend defaults registered in source system config and can be edited only through raw config or a later UI enhancement.
- Manual purge preview is a follow-up. The first implementation keeps the existing manual purge action and ensures it reads metadata rather than scanning archive storage.
