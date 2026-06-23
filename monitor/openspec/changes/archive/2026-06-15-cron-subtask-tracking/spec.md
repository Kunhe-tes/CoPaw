# Cron Subtask Tracking - API Specification

## API Endpoints

### POST /monitor/subtasks

Create a new subtask record.

**Request Headers:**
```
Content-Type: application/json
```

**Request Body Schema:**
```json
{
    "trace_id": {
        "type": "string",
        "minLength": 1,
        "maxLength": 64,
        "required": true,
        "description": "主任务trace_id"
    },
    "task_id": {
        "type": "string",
        "minLength": 1,
        "maxLength": 128,
        "required": true,
        "description": "子任务task_id"
    },
    "filename": {
        "type": "string",
        "minLength": 1,
        "maxLength": 512,
        "required": true,
        "description": "文件名"
    }
}
```

**Response Schema (200 OK):**
```json
{
    "success": {
        "type": "boolean",
        "default": true
    },
    "id": {
        "type": "integer",
        "nullable": true,
        "description": "创建的记录ID"
    },
    "message": {
        "type": "string",
        "default": "Subtask created"
    }
}
```

---

### POST /monitor/subtasks/sync-status

Sync subtask statuses from external API.

**Request Headers:**
```
Content-Type: application/json
```

**Request Body:**
```json
{}
```

**Response Schema (200 OK):**
```json
{
    "success": {
        "type": "boolean",
        "default": true
    },
    "total_scanned": {
        "type": "integer",
        "default": 0,
        "description": "扫描总数"
    },
    "total_updated": {
        "type": "integer",
        "default": 0,
        "description": "更新总数"
    },
    "total_failed": {
        "type": "integer",
        "default": 0,
        "description": "失败总数"
    },
    "details": {
        "type": "array",
        "items": {
            "task_id": "string",
            "old_status": "string|null",
            "new_status": "string|null",
            "error": "string|null"
        }
    }
}
```

**Behavior:**
- If current hour >= ASYNC_TASK_TIMEOUT_HOUR (default 18):
  - Mark all pending subtasks as TIMEOUT
  - Skip external API queries
- Otherwise:
  - Query external API for each pending subtask
  - Parse response: returnCode == "SUC0000", body.get("status")
  - Valid statuses: SUC, FAIL, PART_SUC

---

### POST /monitor/cron/executions/sync-async-status

Aggregate subtask statuses to execution async_status.

**Request Headers:**
```
Content-Type: application/json
```

**Request Body:**
```json
{}
```

**Response Schema (200 OK):**
```json
{
    "success": {
        "type": "boolean",
        "default": true
    },
    "total_scanned": {
        "type": "integer",
        "default": 0,
        "description": "扫描总数"
    },
    "total_updated": {
        "type": "integer",
        "default": 0,
        "description": "更新总数"
    },
    "total_success": {
        "type": "integer",
        "default": 0,
        "description": "成功数"
    },
    "total_error": {
        "type": "integer",
        "default": 0,
        "description": "错误数"
    }
}
```

**Aggregation Logic:**
- For each execution with NULL async_status:
  - Get all subtasks by trace_id
  - If any subtask status in (FAIL, PART_SUC, TIMEOUT) → async_status = "error"
  - If all subtasks have SUC status → async_status = "success"
  - If any subtask pending (NULL/empty) → skip this execution

## Database Schema

### swe_cron_subtasks

| Field | Type | Description |
|-------|------|-------------|
| id | BIGINT | Primary key, auto-increment |
| trace_id | VARCHAR(64) | Main task trace_id |
| task_id | VARCHAR(128) | Subtask task_id |
| filename | VARCHAR(512) | File name |
| status | VARCHAR(16) | Status: SUC/FAIL/PART_SUC/TIMEOUT/NULL |
| info | VARCHAR(2048) | Reserved for extension |
| created_at | DATETIME | Creation time |
| updated_at | DATETIME | Update time |

**Indexes:**
- PRIMARY KEY (id)
- UNIQUE INDEX uk_trace_task (trace_id, task_id)

### swe_cron_executions (modified)

| New Field | Type | Description |
|-----------|------|-------------|
| async_status | VARCHAR(16) | Aggregated status: success/error/NULL |

## Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| MONITOR_ASYNC_TASK_QUERY_URL | string | "" | External API base URL |
| MONITOR_ASYNC_TASK_APP_KEY | string | "" | Application key |
| MONITOR_ASYNC_TASK_ENV_TAG | string | "" | Environment tag |
| MONITOR_ASYNC_TASK_API_KEY | string | "" | API authentication key |
| MONITOR_ASYNC_TASK_TIMEOUT_HOUR | int | 18 | Hour threshold for timeout (0-23) |