# 批调度入队前跳过明细

> 按仓库约定由主线程顺序实施，先验证用例失败，再实现并复测。

**目标** 在新版批次的执行成员页展示回调筛选时跳过了哪些成员及其原因。

- [x] 扩展 `tests/unit/scheduler/test_managed_board_query.py` 与批回调测试，复现零成员批次无法解释未读暂停、部分成员入队，以及旧回执无明细。
- [x] 在 `scheduler/src/scheduler/app/services/cron/managed/scheduling.py` 由同一个准入判断生成入队名单和跳过快照。将快照保存到既有 `response_json`，按父子归属、用户、任务标识、任务名与原因码记录。
- [x] 在 `monitor/src/monitor/app/services/cron/managed_board.py` 读取本批次回执，在详情返回 `skipped_members`。旧回执返回 null，已记录但无人跳过返回空数组。
- [x] 在 `console/src/pages/Monitor/ManagedBatchDispatch/BatchDetail.test.tsx` 复现未读暂停未显示，再更新界面及详情类型。使用现有表格展示跳过成员，零成员旧批次显示历史提示。
- [x] 执行 Scheduler 批回调与 Monitor 看板测试、Console 看板单测、构建及当前 Chromium 的模拟接口检查。
- [ ] 部署 Scheduler、Monitor、Console 后在现场 Chromium 108 核对页面，无需 SQL 变更。
