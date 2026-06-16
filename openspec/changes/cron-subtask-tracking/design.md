## Context

部分定时任务会拆分成多个子任务异步执行，这些子任务的执行状态需要独立跟踪。当前 `swe_cron_executions` 表只记录主任务的执行状态，无法反映子任务的执行结果。

### 业务场景

1. 定时任务执行时，主任务创建多个异步子任务
2. 每个子任务有独立的 `task_id`，通过外部异步任务系统执行
3. 需要追踪每个子任务的执行状态
4. 最终需要根据子任务状态汇总主任务的异步执行状态

### 外部任务状态查询接口

```
POST https://test.com/opanapi/runtime-async/app/{appKey}/tag/{envTag}/result/query/{taskId}
Header: Content-type: application/json;charset=utf-8
Header: API-Key: {api-key}
Body: (empty)

Response:
{
  "returnCode": "SUC000",
  "errorMsg": "SUC",
  "actionResults": [{
    "actionKey": "xxx",
    "status": "SUC"
  }]
}
```

子任务状态枚举：
- `SUC` - 成功
- `FAIL` - 失败
- `PART_SUC` - 部分成功

## Goals / Non-Goals

**Goals:**
- 设计子任务信息存储表
- 提供子任务记录写入接口
- 提供子任务状态查询并更新接口（调用外部API）
- 在执行记录表添加异步任务执行状态字段
- 提供异步执行状态汇总接口

**Non-Goals:**
- 不涉及子任务创建逻辑（由 SWE 侧负责）
- 不修改现有的定时任务执行流程
- 不支持子任务重试机制

## Decisions

### 决策 1: 新建子任务表存储子任务信息

**选择**: 创建独立的 `swe_cron_subtasks` 表

**理由**:
- 子任务与主任务是一对多关系
- 子任务状态独立更新，不影响主任务记录
- 便于扩展子任务相关字段

**表结构**:
```sql
CREATE TABLE swe_cron_subtasks (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    trace_id     VARCHAR(64) NOT NULL COMMENT '主任务trace_id',
    task_id      VARCHAR(128) NOT NULL COMMENT '子任务task_id',
    status       VARCHAR(16) DEFAULT NULL COMMENT '子任务状态: SUC/FAIL/PART_SUC',
    info         VARCHAR(2048) DEFAULT '' COMMENT '预留扩展信息',
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at   DATETIME DEFAULT NULL COMMENT '更新时间',

    UNIQUE INDEX uk_trace_task (trace_id, task_id),
    INDEX idx_trace_id (trace_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务子任务表';
```

### 决策 2: 执行记录表添加异步执行状态字段

**选择**: 在 `swe_cron_executions` 表的 `status` 字段后添加 `async_status` 字段

**理由**:
- 位置明确，语义清晰
- 与现有 status 字段区分（status 表示主任务执行状态，async_status 表示子任务汇总状态）

**ALTER SQL**:
```sql
ALTER TABLE swe_cron_executions
ADD COLUMN async_status VARCHAR(16) DEFAULT NULL
COMMENT '异步任务执行状态: success/error'
AFTER status;

ADD INDEX idx_async_status (async_status);
```

**状态说明**:
- `NULL` - 未设置或无子任务
- `success` - 所有子任务成功或无子任务
- `error` - 存在失败或部分成功的子任务

### 决策 3: 外部 API 配置存储在环境配置文件

**选择**: URL、appKey、envTag、API-Key 存储在 `dev.json` / `prd.json`

**理由**:
- 不同环境使用不同的配置
- 与现有配置管理模式一致
- 敏感信息不写死在代码中

**配置项**:
```json
{
  "MONITOR_ASYNC_TASK_QUERY_URL": "https://test.com/opanapi/runtime-async",
  "MONITOR_ASYNC_TASK_APP_KEY": "your-app-key",
  "MONITOR_ASYNC_TASK_ENV_TAG": "prod",
  "MONITOR_ASYNC_TASK_API_KEY": "your-api-key"
}
```

**constant.py 新增**:
```python
ASYNC_TASK_QUERY_URL = EnvVarLoader.get_str("MONITOR_ASYNC_TASK_QUERY_URL", "")
ASYNC_TASK_APP_KEY = EnvVarLoader.get_str("MONITOR_ASYNC_TASK_APP_KEY", "")
ASYNC_TASK_ENV_TAG = EnvVarLoader.get_str("MONITOR_ASYNC_TASK_ENV_TAG", "")
ASYNC_TASK_API_KEY = EnvVarLoader.get_str("MONITOR_ASYNC_TASK_API_KEY", "")
```

### 册策 4: 接口设计

**写入接口**: `POST /monitor/subtasks`
- 请求体: `{ trace_id: string, task_id: string }`
- 自动填充 `created_at = now()`, `updated_at = NULL`

**状态更新接口**: `POST /monitor/subtasks/sync-status`
- 扫描 `status IS NULL OR status = ''` 的记录
- 调用外部 API 查询状态
- 更新 `status` 和 `updated_at`

**异步状态汇总接口**: `POST /monitor/cron/executions/sync-async-status`
- 扫描 `async_status IS NULL OR async_status = ''` 的执行记录
- 关联子任务表（通过 `trace_id`）
- 规则:
  - 无子任务或所有子任务 `status = 'SUC'` → `async_status = 'success'`
  - 存在子任务 `status IN ('FAIL', 'PART_SUC')` → `async_status = 'error'`

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|---------|
| 外部 API 调用失败 | 记录日志，跳过该条记录，下次重试 |
| 外部 API 响应超时 | 设置独立超时（10秒），不影响其他记录 |
| 子任务数量过多 | 分批查询，每批 50 条 |
| 配置缺失导致接口不可用 | 配置验证，URL/appKey/apiKey 缺失时返回错误 |

## Design Details

### 写入接口流程

```
POST /monitor/subtasks
    ↓
验证必传字段: trace_id, task_id
    ↓
检查是否已存在 (trace_id, task_id)
    │
    ├── 已存在 → 返回成功（幂等）
    └── 不存在 → INSERT
                    ↓
                created_at = NOW()
                updated_at = NULL
                status = NULL
    ↓
返回成功响应
```

### 状态同步接口流程

```
POST /monitor/subtasks/sync-status
    ↓
查询 status IS NULL OR status = '' 的记录
    ↓
分批处理 (每批 50 条)
    │
    ├── 对每条记录:
    │       ↓
    │   构造外部 API URL:
    │   {base_url}/app/{appKey}/tag/{envTag}/result/query/{taskId}
    │       ↓
    │   发送 POST 请求 (带 API-Key header)
    │       ↓
    │   解析响应:
    │       │
    │       ├── returnCode = "SUC000" → 提取 actionResults[0].status
    │       └── 其他 → 记录日志，跳过
    │       ↓
    │   更新记录: status = 提取值, updated_at = NOW()
    │
    └── 循环处理下一批
    ↓
返回处理结果统计
```

### 异步状态汇总接口流程

```
POST /monitor/cron/executions/sync-async-status
    ↓
查询 async_status IS NULL OR async_status = '' 的执行记录
    ↓
对每条执行记录:
    │
    ├── 通过 trace_id 关联子任务表
    │       ↓
    │   查询该 trace_id 下所有子任务状态
    │       │
    │       ├── 无子任务 → async_status = 'success'
    │       ├── 所有 status = 'SUC' → async_status = 'success'
    │       └── 存在 FAIL 或 PART_SUC → async_status = 'error'
    │       ↓
    │   更新执行记录的 async_status 字段
    │
    └── 循环处理下一条
    ↓
返回处理结果统计
```

### 外部 API 响应解析

```python
# 成功响应示例
{
    "returnCode": "SUC000",
    "errorMsg": "SUC",
    "actionResults": [{
        "actionKey": "xxx",
        "status": "SUC"  # 或 FAIL / PART_SUC
    }]
}

# 解析逻辑
if response.get("returnCode") == "SUC000":
    action_results = response.get("actionResults", [])
    if action_results:
        status = action_results[0].get("status", "")
        # 验证状态值有效性
        if status in ("SUC", "FAIL", "PART_SUC"):
            return status
return None  # 无效响应
```

## File Structure

```
monitor/src/monitor/
├── app/
│   ├── models/
│   │   └── subtask.py           # 新增：子任务数据模型
│   ├── routers/
│   │   └── subtask.py           # 新增：子任务路由
│   ├── services/
│   │   └── subtask/
│   │       ├── __init__.py      # 新增
│   │       ├── query_service.py # 新增：查询服务
│   │       └── sync_service.py  # 新增：状态同步服务
│   └── database/
│       └── schema.py            # 修改：添加新表 SQL
├── config/
│   ├── constant.py              # 修改：添加异步任务配置
│   └── envs/
│       ├── dev.json             # 修改：添加配置项
│       └── prd.json             # 修改：添加配置项
```

## Migration Plan

### 部署前准备

1. 执行数据库 ALTER:
   - 创建 `swe_cron_subtasks` 表
   - 添加 `swe_cron_executions.async_status` 字段

2. 配置环境变量:
   - `dev.json` / `prd.json` 添加异步任务 API 配置

### 数据库变更

```sql
-- 1. 创建子任务表
CREATE TABLE swe_cron_subtasks (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID',
    trace_id     VARCHAR(64) NOT NULL COMMENT '主任务trace_id',
    task_id      VARCHAR(128) NOT NULL COMMENT '子任务task_id',
    status       VARCHAR(16) DEFAULT NULL COMMENT '子任务状态: SUC/FAIL/PART_SUC',
    info         VARCHAR(2048) DEFAULT '' COMMENT '预留扩展信息',
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at   DATETIME DEFAULT NULL COMMENT '更新时间',

    UNIQUE INDEX uk_trace_task (trace_id, task_id),
    INDEX idx_trace_id (trace_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务子任务表';

-- 2. 执行记录表添加字段
ALTER TABLE swe_cron_executions
ADD COLUMN async_status VARCHAR(16) DEFAULT NULL
COMMENT '异步任务执行状态: success/error'
AFTER status;

ALTER TABLE swe_cron_executions
ADD INDEX idx_async_status (async_status);
```

### 配置示例

**dev.json**:
```json
{
  "MONITOR_ASYNC_TASK_QUERY_URL": "https://dev.test.com/opanapi/runtime-async",
  "MONITOR_ASYNC_TASK_APP_KEY": "dev-app-key",
  "MONITOR_ASYNC_TASK_ENV_TAG": "dev",
  "MONITOR_ASYNC_TASK_API_KEY": "dev-api-key"
}
```

**prd.json**:
```json
{
  "MONITOR_ASYNC_TASK_QUERY_URL": "https://test.com/opanapi/runtime-async",
  "MONITOR_ASYNC_TASK_APP_KEY": "prod-app-key",
  "MONITOR_ASYNC_TASK_ENV_TAG": "prod",
  "MONITOR_ASYNC_TASK_API_KEY": "prod-api-key"
}
```

### 验证步骤

1. 启动 Monitor 服务
2. 测试写入接口:
   ```bash
   curl -X POST http://localhost:9090/monitor/subtasks \
     -H "Content-Type: application/json" \
     -d '{"trace_id": "test-trace", "task_id": "test-task-1"}'
   ```
3. 测试状态同步接口:
   ```bash
   curl -X POST http://localhost:9090/monitor/subtasks/sync-status
   ```
4. 测试异步状态汇总接口:
   ```bash
   curl -X POST http://localhost:9090/monitor/cron/executions/sync-async-status
   ```
5. 查询数据库验证字段更新正确