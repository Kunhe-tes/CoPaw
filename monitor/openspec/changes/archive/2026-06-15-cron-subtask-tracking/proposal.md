# Cron Subtask Tracking - Implementation Proposal

## Timeline

- **Date**: 2026-06-15
- **Status**: Completed

## Components

### 1. Database Layer

**Table: swe_cron_subtasks**
- Stores subtask execution records
- Unique constraint on (trace_id, task_id)
- Supports idempotent creation

**Table Modification: swe_cron_executions**
- New field: async_status
- Values: success, error, or NULL

### 2. Model Layer

**SubtaskModel**: Database record representation
**SubtaskCreateRequest**: API request validation
**SubtaskSyncStatusResponse**: Sync operation result
**ExecutionAsyncStatusResponse**: Aggregation result

### 3. Service Layer

**QueryService** (`services/subtask/query_service.py`):
- create_subtask()
- get_pending_subtasks()
- get_subtasks_by_trace_id()
- update_subtask_status()
- get_pending_executions()
- update_execution_async_status()

**SyncService** (`services/subtask/sync_service.py`):
- sync_subtask_status() - Main sync entry point
- _query_task_status() - External API call
- _parse_api_response() - Response parsing
- _mark_pending_as_timeout() - Timeout handling
- sync_execution_async_status() - Aggregation
- _compute_execution_async_status() - Status computation

### 4. Router Layer

**Endpoints** (`routers/subtask.py`):
- POST /monitor/subtasks
- POST /monitor/subtasks/sync-status
- POST /monitor/cron/executions/sync-async-status

### 5. Configuration

**Environment Variables**:
- MONITOR_ASYNC_TASK_QUERY_URL
- MONITOR_ASYNC_TASK_APP_KEY
- MONITOR_ASYNC_TASK_ENV_TAG
- MONITOR_ASYNC_TASK_API_KEY
- MONITOR_ASYNC_TASK_TIMEOUT_HOUR (default: 18)

## Dependencies

- httpx: Async HTTP client for external API
- pydantic: Request/response validation
- aiomysql: Database operations

## Testing Considerations

1. Idempotent creation test
2. External API mock tests
3. Timeout logic test
4. Status aggregation test
5. Batch processing test

## Security Considerations

- API key stored in environment config
- No sensitive data in logs (task_id truncated)
- Input validation via Pydantic