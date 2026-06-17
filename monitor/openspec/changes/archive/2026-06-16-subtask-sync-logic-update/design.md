# 子任务同步接口逻辑优化

## Context

优化两个同步接口的状态更新逻辑，增加时间阈值判断和兜底机制，避免不必要的 API 调用和历史数据无法处理的问题。

**变更日期**: 2026-06-16
**补充修复**: 2026-06-17（修复历史数据漏洞）

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

**查询范围调整（修复历史数据漏洞）：**
1. **所有无状态的子任务**（status IS NULL OR status = ''）- **不限制时间**
2. **当天创建的 FAIL/PART_SUC/TIMEOUT 状态子任务**

**兜底机制：**
- 超过24小时的 pending 子任务，直接标记 TIMEOUT，强制推进状态

**按原状态分类处理：**

| 原状态 | 当前时间 >= timeout_hour | 当前时间 < timeout_hour | 处理方式 |
|--------|--------------------------|-------------------------|----------|
| NULL/空 | 始终查询API并更新，超过24h标记TIMEOUT | 始终查询API并更新，超过24h标记TIMEOUT | 查询更新+兜底 |
| FAIL/PART_SUC/TIMEOUT（当天） | 不查询，不更新 | 查询API，状态变化时更新 | 有变化才更新 |
| SUC | 已通过查询排除 | 已通过查询排除 | 终态，不处理 |

**流程图：**
```
1. 获取待同步子任务：
   - 所有无状态的子任务（不限制时间）
   - 当天创建的 FAIL/PART_SUC/TIMEOUT 子任务
2. 对每个子任务：
   a. 如果原状态为 NULL/空：
      - 检查是否超过24小时 → 标记 TIMEOUT（兜底）
      - 否则查询API并更新
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

## 漏洞修复

### 原问题
原来的逻辑只查询当天创建的子任务，可能导致：
- 昨天创建的 pending 子任务无法被查询
- execution.async_status 永远无法更新
- 消息永远无法发送

### 修复方案
1. **放宽查询范围**：无状态子任务不限制时间
2. **添加兜底机制**：超过24小时的 pending 子任务标记 TIMEOUT

---

## 修改文件列表

| 文件 | 修改内容 |
|------|----------|
| `database/schema.py` | 新增5个字段定义，新增ALTER语句 |
| `models/subtask.py` | SubtaskModel新增5个字段，SubtaskCreateRequest新增5个可选字段 |
| `services/subtask/query_service.py` | 新增 get_today_pending_subtasks() 方法，查询逻辑调整 |
| `services/subtask/sync_service.py` | 重构同步逻辑，添加24小时兜底机制 |
| `routers/subtask.py` | 传递新字段参数 |

---

## 配置项

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ASYNC_TASK_TIMEOUT_HOUR` | 超时阈值（小时） | 18 |

---

## Verification

1. 验证无状态子任务查询不限制时间
2. 验证当天 FAIL/PART_SUC/TIMEOUT 子任务查询正确
3. 验证超过24小时 pending 子任务标记 TIMEOUT
4. 验证聚合逻辑正确
5. 验证历史数据能正常处理