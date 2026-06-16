# 子任务同步接口逻辑优化

## Context

优化两个同步接口的状态更新逻辑，增加时间阈值判断和当天数据过滤，避免不必要的 API 调用和状态更新。

**变更日期**: 2026-06-16

---

## 新增字段（同时完成）

在 `swe_cron_subtasks` 表新增字段：

| 字段名 | 类型 | 说明 | 是否必填 |
|--------|------|------|----------|
| `task_type` | VARCHAR(16) | 任务类型: list(清单)/plan(方案) | 可空 |
| `custuid` | VARCHAR(64) | 任务中客户ID | 可空 |
| `cust_nm` | VARCHAR(255) | 任务中客户名称 | 可空 |
| `notification_content_wplus` | VARCHAR(5000) | W+渠道通知消息内容 | 可空 |
| `notification_content_zhaohu` | VARCHAR(5000) | 招乎渠道通知消息内容 | 可空 |

---

## 接口一：subtasks/sync-status（子任务状态同步）

### 新逻辑

**查询范围调整：**
- 只查询当天创建的子任务（created_at >= 当天 00:00:00）
- 排除已成功(SUC)的终态子任务

**按原状态分类处理：**

| 原状态 | 当前时间 >= timeout_hour | 当前时间 < timeout_hour | 处理方式 |
|--------|--------------------------|-------------------------|----------|
| NULL/空 | 始终查询API并更新 | 始终查询API并更新 | 查询更新 |
| FAIL/PART_SUC/TIMEOUT | 不查询，不更新 | 查询API，状态变化时更新 | 有变化才更新 |
| SUC | 已通过查询排除 | 已通过查询排除 | 终态，不处理 |

**流程图：**
```
1. 获取当天创建的子任务（created_at >= 当天00:00:00，排除SUC）
2. 对每个子任务：
   a. 如果原状态为 NULL/空：
      - 始终查询API并更新（不管是否超时）
   b. 如果原状态为 FAIL/PART_SUC/TIMEOUT：
      - 时间 >= threshold → 跳过（不查询，不更新）
      - 时间 < threshold → 查询API，状态变化时更新
```

---

## 接口二：subtasks/executions/sync-async-status（主任务状态聚合）

### 新逻辑

**按时间阈值分类处理：**

| 条件 | 子任务状态情况 | 处理方式 |
|------|----------------|----------|
| 时间 >= threshold | 所有子任务都有状态 | 按子任务状态聚合更新 |
| 时间 >= threshold | 存在子任务无状态 | 不更新，等待下次同步 |
| 时间 < threshold | 所有子任务为 SUC | 更新为 success |
| 时间 < threshold | 存在非 SUC 子任务 | 不更新，继续等待 |

**聚合规则（时间 >= threshold 时）：**
- 没有 subtasks → async_status = "success"
- 存在 FAIL/PART_SUC/TIMEOUT → async_status = "error"
- 全部 SUC → async_status = "success"

**流程图：**
```
1. 获取 pending executions
2. 检查当前时间是否 >= timeout_hour
3. 对每个 execution：
   a. 查询其所有 subtasks
   b. 如果没有 subtasks → 更新为 success
   c. 如果时间 >= threshold：
      - 存在无状态子任务 → 跳过
      - 全部有状态 → 按规则聚合更新
   d. 如果时间 < threshold：
      - 全部 SUC → 更新为 success
      - 存在非 SUC → 跳过，继续等待
```

---

## 修改文件列表

| 文件 | 修改内容 |
|------|----------|
| `database/schema.py` | 新增5个字段定义，新增ALTER语句 |
| `models/subtask.py` | SubtaskModel新增5个字段，SubtaskCreateRequest新增5个可选字段 |
| `services/subtask/query_service.py` | 新增 get_today_pending_subtasks() 方法，新增5个字段参数 |
| `services/subtask/sync_service.py` | 重构 sync_subtask_status() 和 sync_execution_async_status() 逻辑 |
| `routers/subtask.py` | 传递新字段参数 |

---

## 配置项

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ASYNC_TASK_TIMEOUT_HOUR` | 超时阈值（小时） | 18 |

---

## Verification

1. 验证当天子任务过滤正确（只查询 created_at >= 00:00:00）
2. 验证 NULL/空状态始终查询API
3. 验证 FAIL/PART_SUC/TIMEOUT 在超时模式下跳过
4. 验证无 subtasks 的 execution 标记为 success
5. 验证聚合逻辑正确