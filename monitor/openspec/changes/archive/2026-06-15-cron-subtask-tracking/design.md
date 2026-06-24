# Cron Subtask Tracking System Design

## Overview

This document describes the design for a subtask tracking system that monitors asynchronous cron task executions.

## Problem Statement

Cron tasks often trigger multiple asynchronous subtasks. We need to:
1. Track each subtask's execution status
2. Sync status from external API periodically
3. Aggregate subtask statuses to determine overall execution status
4. Handle timeout scenarios when external API queries are not available

## Solution

### Database Schema

#### New Table: `swe_cron_subtasks`

```sql
CREATE TABLE swe_cron_subtasks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    trace_id VARCHAR(64) NOT NULL COMMENT '主任务trace_id',
    task_id VARCHAR(128) NOT NULL COMMENT '子任务task_id',
    filename VARCHAR(512) NOT NULL COMMENT '文件名',
    status VARCHAR(16) DEFAULT NULL COMMENT '子任务状态: SUC/FAIL/PART_SUC/TIMEOUT',
    info VARCHAR(2048) DEFAULT '' COMMENT '预留扩展信息',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT NULL COMMENT '更新时间',
    UNIQUE INDEX uk_trace_task (trace_id, task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务子任务跟踪表';
```

#### Modified Table: `swe_cron_executions`

Add `async_status` field to track aggregated execution status:

```sql
ALTER TABLE swe_cron_executions
ADD COLUMN async_status VARCHAR(16) DEFAULT NULL
COMMENT '聚合状态: success/error' AFTER status;
```

### Status Values

| Status | Description |
|--------|-------------|
| `SUC` | Subtask completed successfully |
| `FAIL` | Subtask failed |
| `PART_SUC` | Partial success |
| `TIMEOUT` | Timeout - marked when past configured hour |
| NULL/Empty | Pending - awaiting status sync |

### Configuration

Add environment variables for external API:

| Variable | Description | Default |
|----------|-------------|---------|
| `MONITOR_ASYNC_TASK_QUERY_URL` | External API base URL | "" |
| `MONITOR_ASYNC_TASK_APP_KEY` | Application key | "" |
| `MONITOR_ASYNC_TASK_ENV_TAG` | Environment tag | "" |
| `MONITOR_ASYNC_TASK_API_KEY` | API key for authentication | "" |
| `MONITOR_ASYNC_TASK_TIMEOUT_HOUR` | Hour threshold for timeout (0-23) | 18 |

### API Endpoints

#### 1. POST /monitor/subtasks

Create a new subtask record.

**Request Body:**
```json
{
    "trace_id": "string (required, 1-64 chars)",
    "task_id": "string (required, 1-128 chars)",
    "filename": "string (required, 1-512 chars)"
}
```

**Response:**
```json
{
    "success": true,
    "id": 123,
    "message": "Subtask created"
}
```

#### 2. POST /monitor/subtasks/sync-status

Sync subtask statuses from external API.

**Behavior:**
- If current hour >= `ASYNC_TASK_TIMEOUT_HOUR`: Mark pending subtasks as TIMEOUT
- Otherwise: Query external API for each pending subtask

**External API Request:**
```
POST {QUERY_URL}/app/{APP_KEY}/tag/{ENV_TAG}/result/query/{task_id}
Headers: API-Key: {API_KEY}
Body: {}
```

**External API Response Parsing:**
- Check `returnCode == "SUC0000"` for success
- Extract `status` from `body.get("status")`
- Valid statuses: `SUC`, `FAIL`, `PART_SUC`

**Response:**
```json
{
    "success": true,
    "total_scanned": 50,
    "total_updated": 45,
    "total_failed": 5,
    "details": [
        {
            "task_id": "...",
            "old_status": null,
            "new_status": "SUC",
            "error": null
        }
    ]
}
```

#### 3. POST /monitor/cron/executions/sync-async-status

Aggregate subtask statuses to update execution async_status.

**Logic:**
- Get executions with NULL async_status
- For each execution, check all its subtasks:
  - If any subtask status in `FAIL`, `PART_SUC`, `TIMEOUT` → `async_status = "error"`
  - If all subtasks have `SUC` status → `async_status = "success"`
  - If any subtask still pending → skip (wait for next sync)

**Response:**
```json
{
    "success": true,
    "total_scanned": 100,
    "total_updated": 80,
    "total_success": 75,
    "total_error": 5
}
```

## Implementation Details

### Services

- `QueryService`: Database operations (create, query, update)
- `SyncService`: External API sync and status aggregation

### Timeout Logic

When `datetime.now().hour >= ASYNC_TASK_TIMEOUT_HOUR`:
1. Skip external API queries
2. Mark all pending subtasks as `TIMEOUT`
3. Log timeout action for monitoring

### Batch Processing

- Default batch size: 50 subtasks per sync cycle
- Process sequentially to avoid overwhelming external API

### Error Handling

- API timeout: Log warning, mark as failed in sync details
- API error response: Parse returnCode, log error
- Invalid status: Skip update, record error in details

## Files Changed

| File | Changes |
|------|---------|
| `monitor/src/monitor/app/database/schema.py` | Add subtasks table, async_status field |
| `monitor/src/monitor/config/constant.py` | Add async task config variables |
| `monitor/src/monitor/app/models/subtask.py` | Add Pydantic models |
| `monitor/src/monitor/app/services/subtask/query_service.py` | Add database operations |
| `monitor/src/monitor/app/services/subtask/sync_service.py` | Add sync logic |
| `monitor/src/monitor/app/routers/subtask.py` | Add API endpoints |
| `monitor/config/envs/dev.json` | Add config entries |
| `monitor/config/envs/prd.json` | Add config entries |
| `monitor/envs.json.example` | Add config entries |