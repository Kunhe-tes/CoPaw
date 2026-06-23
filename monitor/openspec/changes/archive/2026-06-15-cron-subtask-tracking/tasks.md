# Cron Subtask Tracking - Task Checklist

## Completed Tasks

### Database Design
- [x] Design swe_cron_subtasks table schema
- [x] Add filename field (required)
- [x] Design unique constraint (trace_id, task_id)
- [x] Add async_status field to swe_cron_executions

### Configuration
- [x] Add ASYNC_TASK_QUERY_URL config
- [x] Add ASYNC_TASK_APP_KEY config
- [x] Add ASYNC_TASK_ENV_TAG config
- [x] Add ASYNC_TASK_API_KEY config
- [x] Add ASYNC_TASK_TIMEOUT_HOUR config (default: 18)
- [x] Update dev.json, prd.json, envs.json.example

### Models
- [x] Create SubtaskModel
- [x] Create SubtaskCreateRequest (with filename required)
- [x] Create SubtaskCreateResponse
- [x] Create SubtaskSyncDetailItem
- [x] Create SubtaskSyncStatusResponse
- [x] Create ExecutionAsyncStatusResponse

### Services
- [x] Create query_service.py
- [x] Implement create_subtask() with idempotency
- [x] Implement get_pending_subtasks()
- [x] Implement get_subtasks_by_trace_id()
- [x] Implement update_subtask_status()
- [x] Implement get_pending_executions()
- [x] Implement update_execution_async_status()

- [x] Create sync_service.py
- [x] Implement sync_subtask_status()
- [x] Implement _query_task_status()
- [x] Implement _parse_api_response() (body.get("status"), returnCode SUC0000)
- [x] Implement _process_single_subtask()
- [x] Implement _mark_pending_as_timeout()
- [x] Implement sync_execution_async_status()
- [x] Implement _compute_execution_async_status()

### Routers
- [x] Create subtask.py router
- [x] Implement POST /monitor/subtasks
- [x] Implement POST /monitor/subtasks/sync-status
- [x] Implement POST /monitor/cron/executions/sync-async-status

### Code Quality
- [x] Fix pylint R0915 (too-many-statements)
- [x] Fix pylint W0611 (unused-import)
- [x] Fix pylint R0911 (too-many-return-statements)
- [x] Fix type errors (arg-type)
- [x] Fix missing final newline

### Documentation
- [x] Write openspec design documents
- [x] Archive to openspec/changes/archive/

## Summary

All tasks completed successfully on 2026-06-15.