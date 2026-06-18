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
  - [x] NULL/空状态：始终查询API并更新
  - [x] FAIL/PART_SUC/TIMEOUT：超时跳过，未超时查询有变化才更新
- [x] 重构 sync_service.sync_execution_async_status() 逻辑
  - [x] 无 subtasks 标记 success
  - [x] 超时模式：全有状态才聚合，有 pending 跳过
  - [x] 正常模式：全 SUC 才更新，否则跳过
- [x] 删除废弃的辅助方法

### 漏洞修复（2026-06-17）
- [x] 修复历史数据无法处理的问题
  - [x] 查询范围调整：所有无状态子任务（不限制时间）
  - [x] 当天 FAIL/PART_SUC/TIMEOUT 子任务正常查询
- [x] 添加24小时兜底机制
  - [x] 超过24小时的 pending 子任务标记 TIMEOUT

### 文档归档
- [x] 创建 openspec/design.md 记录变更
- [x] 更新 openspec/design.md 记录漏洞修复

---

## 变更日期

- 2026-06-16：初始实现
- 2026-06-17：漏洞修复