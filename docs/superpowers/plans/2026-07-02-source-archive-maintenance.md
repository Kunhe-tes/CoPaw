# Source Archive Maintenance Implementation Plan

## Goal

Split file archive behavior into three execution paths:

1. Keep existing dream cron/manual dream execution focused on dream optimization only.
2. Add a source-level archive maintenance scheduled task that is enabled by default and archives old orphan files across tenants and agent workspaces under that source.
3. Keep archived-file deletion/purge manual only, using archive metadata and read-model records instead of recursively scanning archive directories.

## Confirmed Boundaries

- "System Feature Configuration" is the existing Source System Configuration surface.
- Archive maintenance config lives under `archive_maintenance` in source system config.
- Source scheduled task registration follows the existing task-session-cleanup scheduler pattern.
- The archive maintenance runner must not instantiate agent runtime just to scan files.
- Automatic archive maintenance does not purge expired archive files.
- Manual purge continues to delete exact archive paths from metadata/read-model rows.

## Backend Tasks

### 1. Source config defaults and runtime resolver

Files:

- `src/swe/app/source_system_config/registry.py`
- `src/swe/app/source_system_config/runtime.py`
- `src/swe/app/source_system_config/__init__.py`
- `tests/unit/app/test_source_system_config.py`

Tests first:

- Default config contains `archive_maintenance.enabled = true` and `archive_maintenance.cron = "0 3 * * *"`.
- Runtime resolver returns defaults when config is absent.
- Runtime resolver accepts explicit source config and normalizes registered values.
- Invalid registered numeric values are rejected by existing validation.

Implementation:

- Register `archive_maintenance` settings:
  - `enabled`: bool, default `true`
  - `cron`: string, default `"0 3 * * *"`
  - `old_orphan_days`: int, default `3`, `ge=1`
  - `max_workspaces_per_run`: int, default `200`, `ge=1`
  - `max_files_per_workspace`: int, default `100`, `ge=1`
  - `max_files_per_run`: int, default `5000`, `ge=1`
  - `timeout_seconds`: int, default `900`, `ge=1`
- Add `ArchiveMaintenanceConfig` and `resolve_archive_maintenance_config()`.

### 2. Archive-only workspace maintenance service

Files:

- `src/swe/app/file_governance/archive_maintenance.py`
- `src/swe/app/routers/dream_logs.py`
- `tests/unit/app/test_archive_maintenance.py`
- `tests/unit/routers/test_dream_logs_dual_write.py`

Tests first:

- `archive_old_orphans_for_workspace()` archives old orphan files and returns counts.
- Per-workspace and per-run limits are honored.
- Protected/root keep files are not archived.
- Archive-only helper never calls purge helpers.
- Existing manual archive endpoint behavior still writes archive state.

Implementation:

- Extract or wrap existing orphan scanning/archive code into a router-independent service.
- Allow caller-provided `old_orphan_days`, per-workspace limit, and run remaining capacity.
- Preserve existing archive index format and DB dual-write behavior.
- Keep manual archive endpoints using the same archive primitive.

### 3. Source-level archive scheduler

Files:

- `src/swe/app/source_system_config/task_scheduler.py`
- `src/swe/app/source_system_config/router.py`
- `src/swe/app/routers/internal.py`
- `src/swe/app/_app.py`
- `tests/unit/app/test_source_system_task_scheduler.py`
- `tests/unit/app/test_external_cron_scope_refresh.py`
- `tests/unit/app/test_source_system_config.py`

Tests first:

- Refresh registers default-enabled `archive_maintenance` with task type `archive_maintenance` and cron `"0 3 * * *"`.
- Refresh updates/resumes an existing archive maintenance job when cron changes.
- Refresh pauses an existing archive maintenance job when disabled.
- Source config update/delete refreshes both cleanup and archive maintenance tasks.
- Internal cron callback dispatches `archive_maintenance` to `SourceSystemTaskScheduler.run_archive_maintenance()`.
- Running source archive maintenance enumerates source tenants, resolves runtime tenant directories with `encode_scope_id()`, scans valid agent workspaces, and does not call `multi_agent_manager.get_agent()`.

Implementation:

- Add source archive task constants and `refresh_archive_maintenance()`.
- Add `run_archive_maintenance(source_id)` summary result.
- Add a tenant-dir resolver dependency to `SourceSystemTaskScheduler`; initialize it from `tenant_workspace_pool.get_tenant_workspace_dir`.
- Use tenant source rows plus filesystem `workspaces/*` directories to find valid agent workspaces.
- Apply `max_workspaces_per_run`, `max_files_per_workspace`, `max_files_per_run`, and `timeout_seconds`.
- Add internal callback branch before runtime agent dispatch.
- Change config router refresh helper to refresh both source tasks.

### 4. Remove dream auto archive side effect

Files:

- `src/swe/app/crons/manager.py`
- `src/swe/app/routers/dream_logs.py`
- `tests/unit/app/test_scheduled_run_source_system_config_binding.py`

Tests first:

- Scheduled dream/manual dream no longer invokes `run_dream_archive_maintenance()`.
- Existing dream optimization behavior remains intact.

Implementation:

- Remove archive maintenance invocation from `CronManager.run_dream()`.
- Remove manual dream archive side effect from dream-log trigger path if still present.
- Keep manual orphan archive and manual purge endpoints unchanged.

## Frontend Tasks

Files:

- `console/src/api/types/sourceSystemConfig.ts`
- `console/src/pages/SystemConfigPage/registry.ts`
- `console/src/pages/SystemConfigPage/index.tsx`
- `console/src/pages/SystemConfigPage/registry.test.ts`
- `console/src/pages/SystemConfigPage/index.test.tsx`

Tests first:

- Registry reads default archive maintenance config.
- Registry converts daily run time to `archive_maintenance.cron`.
- Invalid archive maintenance cron is rejected as non-daily.
- System Config page renders archive maintenance switch and execution time.
- Toggling switch / changing time writes source config under `archive_maintenance`.

Implementation:

- Add `ArchiveMaintenanceConfig` type.
- Add defaults/read/write helpers mirroring existing cleanup cron helpers.
- Add UI controls in the existing scheduled-task settings card:
  - enabled switch
  - daily execution time input
- Keep advanced limits backend-only for now.

## Verification Commands

Backend:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_source_system_config.py tests/unit/app/test_source_system_task_scheduler.py tests/unit/app/test_external_cron_scope_refresh.py tests/unit/app/test_archive_maintenance.py tests/unit/routers/test_dream_logs_dual_write.py tests/unit/app/test_scheduled_run_source_system_config_binding.py
```

Frontend:

```powershell
.\node_modules\.bin\vitest.cmd run console/src/pages/SystemConfigPage/registry.test.ts console/src/pages/SystemConfigPage/index.test.tsx
```

Final sanity:

```powershell
git diff --check
git status --short --branch
```
