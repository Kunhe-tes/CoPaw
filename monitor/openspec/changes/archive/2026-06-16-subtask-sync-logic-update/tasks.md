# 子任务同步接口逻辑优化 - 任务清单

## 已完成任务

### 新增字段
- [x] 设计 swe_cron_subtasks 表新增5个字段
- [x] 更新 database/schema.py CREATE_TABLE 和 ALTER 语句
- [x] 更新 models/subtask.py SubtaskModel 和 SubtaskCreateRequest
- [x] 更新 query_service.py create_subtask() 新增字段参数
- [x] 更新 routers/subtask.py 传递新字段参数

### 同步逻辑优化
- [x] 新增 query_service.get_today_pending_subtasks() 方法
- [x] 重构 sync_service.sync_subtask_status() 逻辑
  - [x] 只查询当天子任务
  - [x] NULL/空状态：始终查询API并更新
  - [x] FAIL/PART_SUC/TIMEOUT：超时跳过，未超时查询有变化才更新
- [x] 重构 sync_service.sync_execution_async_status() 逻辑
  - [x] 无 subtasks 标记 success
  - [x] 超时模式：全有状态才聚合，有 pending 跳过
  - [x] 正常模式：全 SUC 才更新，否则跳过
- [x] 删除废弃的辅助方法

### 文档归档
- [x] 创建 openspec/design.md 记录变更

---

## 变更日期

2026-06-16