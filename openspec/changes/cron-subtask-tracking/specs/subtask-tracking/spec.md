# Spec: 定时任务子任务跟踪系统

## 1. 数据表设计

### 1.1 子任务表 `swe_cron_subtasks`

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | BIGINT | 是 | AUTO_INCREMENT | 主键ID |
| trace_id | VARCHAR(64) | 是 | - | 主任务trace_id |
| task_id | VARCHAR(128) | 是 | - | 子任务task_id |
| status | VARCHAR(16) | 否 | NULL | 子任务状态: SUC/FAIL/PART_SUC |
| info | VARCHAR(2048) | 否 | '' | 预留扩展信息 |
| created_at | DATETIME | 是 | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | DATETIME | 否 | NULL | 更新时间 |

**索引**:
- `uk_trace_task (trace_id, task_id)` - 唯一索引，防止重复
- `idx_trace_id (trace_id)` - 关联查询索引
- `idx_status (status)` - 状态筛选索引
- `idx_created_at (created_at)` - 时间排序索引

### 1.2 执行记录表扩展

**新增字段** `async_status`:
- 位置: `status` 字段之后
- 类型: `VARCHAR(16)`
- 默认值: `NULL`
- 说明: 异步任务执行状态: success/error

**新增索引**: `idx_async_status`

## 2. API 接口设计

### 2.1 写入子任务记录

**接口**: `POST /monitor/subtasks`

**请求体**:
```json
{
  "trace_id": "string",  // 必填
  "task_id": "string"    // 必填
}
```

**响应体**:
```json
{
  "success": true,
  "id": 1,
  "message": "Subtask created"
}
```

**行为**:
1. 验证必传字段
2. 检查是否已存在 `(trace_id, task_id)`
3. 如已存在返回成功（幂等）
4. 如不存在则插入，`created_at = NOW()`, `updated_at = NULL`, `status = NULL`

### 2.2 同步子任务状态

**接口**: `POST /monitor/subtasks/sync-status`

**请求体**: 无（或可选的批量参数）

**响应体**:
```json
{
  "success": true,
  "total_scanned": 100,
  "total_updated": 85,
  "total_failed": 15,
  "details": [
    {
      "task_id": "xxx",
      "old_status": null,
      "new_status": "SUC",
      "error": null
    }
  ]
}
```

**行为**:
1. 查询 `status IS NULL OR status = ''` 的记录
2. 分批处理（每批50条）
3. 对每条记录调用外部 API
4. 解析响应，更新 `status` 和 `updated_at`
5. 返回处理统计

### 2.3 汇总异步执行状态

**接口**: `POST /monitor/cron/executions/sync-async-status`

**请求体**: 无（或可选的批量参数）

**响应体**:
```json
{
  "success": true,
  "total_scanned": 50,
  "total_updated": 50,
  "total_success": 40,
  "total_error": 10
}
```

**行为**:
1. 查询 `async_status IS NULL OR async_status = ''` 的执行记录
2. 通过 `trace_id` 关联子任务表
3. 判断规则:
   - 无子任务 → `async_status = 'success'`
   - 所有子任务 `status = 'SUC'` → `async_status = 'success'`
   - 存在子任务 `status IN ('FAIL', 'PART_SUC')` → `async_status = 'error'`
4. 更新执行记录的 `async_status`

## 3. 外部 API 集成

### 3.1 接口规范

**URL模板**:
```
{base_url}/app/{appKey}/tag/{envTag}/result/query/{taskId}
```

**请求头**:
```
Content-type: application/json;charset=utf-8
API-Key: {api-key}
```

**请求体**: 空

**响应示例**:
```json
{
  "returnCode": "SUC000",
  "errorMsg": "SUC",
  "actionResults": [{
    "actionKey": "xxx",
    "status": "SUC"
  }]
}
```

### 3.2 状态映射

| actionResults.status | 存储值 |
|---------------------|--------|
| SUC | SUC |
| FAIL | FAIL |
| PART_SUC | PART_SUC |

## 4. 配置设计

### 4.1 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| MONITOR_ASYNC_TASK_QUERY_URL | 外部 API 基础 URL | https://test.com/opanapi/runtime-async |
| MONITOR_ASYNC_TASK_APP_KEY | 应用 Key | your-app-key |
| MONITOR_ASYNC_TASK_ENV_TAG | 环境标签 | prod |
| MONITOR_ASYNC_TASK_API_KEY | API Key | your-api-key |

### 4.2 配置加载

```python
# constant.py
ASYNC_TASK_QUERY_URL = EnvVarLoader.get_str("MONITOR_ASYNC_TASK_QUERY_URL", "")
ASYNC_TASK_APP_KEY = EnvVarLoader.get_str("MONITOR_ASYNC_TASK_APP_KEY", "")
ASYNC_TASK_ENV_TAG = EnvVarLoader.get_str("MONITOR_ASYNC_TASK_ENV_TAG", "")
ASYNC_TASK_API_KEY = EnvVarLoader.get_str("MONITOR_ASYNC_TASK_API_KEY", "")
```

## 5. 错误处理

### 5.1 外部 API 调用失败

| 场景 | 处理 |
|------|------|
| 网络超时 | 记录日志，跳过该条，下次重试 |
| returnCode != SUC000 | 记录日志，跳过该条 |
| actionResults 为空 | 记录日志，跳过该条 |
| status 值无效 | 记录日志，跳过该条 |

### 5.2 配置缺失

| 场景 | 处理 |
|------|------|
| URL 为空 | 返回 500 错误 |
| appKey 为空 | 返回 500 错误 |
| apiKey 为空 | 返回 500 错误 |

## 6. 性能考虑

| 场景 | 优化措施 |
|------|---------|
| 大量待更新子任务 | 分批处理，每批50条 |
| 外部 API 响应慢 | 独立超时10秒 |
| 执行记录数量大 | 分批扫描，每批100条 |