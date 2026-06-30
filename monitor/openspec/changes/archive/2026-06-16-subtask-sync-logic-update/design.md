# 子任务同步接口逻辑优化

## Context

优化两个同步接口的状态更新逻辑，简化处理流程，添加兜底机制。

**变更日期**: 2026-06-16
**补充修复**: 2026-06-17（修复历史数据漏洞、简化逻辑）

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

### 最终逻辑（简化版）

**查询范围：**
- 只查询无状态的子任务（status IS NULL OR status = ''），不限制时间

**状态分类：**
- NULL/空：查询API并更新，超过24小时标记TIMEOUT（兜底）
- FAIL/PART_SUC/TIMEOUT/SUC：终态，不再查询

**流程图：**
```
1. 获取所有无状态的子任务（不限制时间）
2. 对每个子任务：
   a. 检查是否超过24小时 → 标记 TIMEOUT（兜底）
   b. 否则查询API并更新
```

---

## 接口二：subtasks/executions/sync-async-status（主任务状态聚合）

### 最终逻辑（简化版）

**聚合规则（不需要等待时间阈值）：**
- 没有 subtasks → success
- 存在无状态子任务 → 跳过，等待下次同步
- 存在 FAIL/PART_SUC/TIMEOUT → error
- 全部 SUC → success

**流程图：**
```
1. 获取 pending executions
2. 对每个 execution：
   a. 查询其所有 subtasks
   b. 如果没有 subtasks → 更新为 success
   c. 如果存在无状态子任务 → 跳过
   d. 否则按规则聚合更新
```

---

## 兜底机制

超过24小时的 pending 子任务，直接标记 TIMEOUT，强制推进状态，避免消息永远无法发送。

---

## 修改文件列表

| 文件 | 修改内容 |
|------|----------|
| `database/schema.py` | 新增5个字段定义，新增ALTER语句 |
| `models/subtask.py` | SubtaskModel新增5个字段，SubtaskCreateRequest新增5个可选字段 |
| `services/subtask/query_service.py` | 新增 get_today_pending_subtasks() 方法 |
| `services/subtask/sync_service.py` | 重构同步逻辑，简化流程 |
| `routers/subtask.py` | 传递新字段参数 |

---

## Verification

1. 验证无状态子任务查询不限制时间
2. 验证超过24小时 pending 子任务标记 TIMEOUT
3. 验证主任务只要子任务都有状态就能聚合更新
4. 验证批量更新 SQL 正确执行

---

## 性能优化（2026-06-17）

### 问题
原代码使用循环逐条处理 executions，batch_size=100 限制导致：
- 大量任务时无法及时处理
- `ORDER BY created_at DESC` 导致旧任务永远排在后面

### 解决方案
使用 SQL JOIN 批量更新，一次处理所有符合条件的 executions：

```sql
-- 更新 success
UPDATE swe_cron_executions e
SET async_status = 'success'
WHERE (e.async_status IS NULL OR e.async_status = '')
AND NOT EXISTS (
    SELECT 1 FROM swe_cron_subtasks s
    WHERE s.trace_id = e.trace_id
    AND (s.status IS NULL OR s.status = '')
)
AND NOT EXISTS (
    SELECT 1 FROM swe_cron_subtasks s
    WHERE s.trace_id = e.trace_id
    AND s.status IN ('FAIL', 'PART_SUC', 'TIMEOUT')
);

-- 更新 error
UPDATE swe_cron_executions e
SET async_status = 'error'
WHERE (e.async_status IS NULL OR e.async_status = '')
AND EXISTS (
    SELECT 1 FROM swe_cron_subtasks s
    WHERE s.trace_id = e.trace_id
    AND s.status IN ('FAIL', 'PART_SUC', 'TIMEOUT')
)
AND NOT EXISTS (
    SELECT 1 FROM swe_cron_subtasks s
    WHERE s.trace_id = e.trace_id
    AND (s.status IS NULL OR s.status = '')
);
```