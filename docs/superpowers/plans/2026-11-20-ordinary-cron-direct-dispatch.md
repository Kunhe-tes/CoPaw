# 普通定时任务直接派发实施计划

> 按仓库约定在主线程顺序实施。每步先验证回归测试失败，再验证实现通过。

**目标**：普通触发及普通任务整点补跑即时派发。相同任务已有执行在跑时，记录本次跳过。执行记录继续支持跟踪和故障恢复。

1. [x] 在 SWE 启动事务中验证普通任务重叠触发被跳过，并保留正在运行的执行。覆盖 `test_managed_cron_execution_boundaries.py`。
2. [x] 在普通回调和补跑登记提交后直接派发。恢复扫描单独处理普通执行，批扫描继续使用现有容量控制。覆盖 `test_managed_cron_callbacks.py`、`test_daily_failure_retry_runtime.py` 和 `test_managed_cron_capacity_dispatch.py`。
3. [x] 从批 Worker 的候选、占位、反馈和当前占用明细排除独立普通执行。已关联真实批次的历史执行继续按批任务处理。覆盖 `test_managed_cron_capacity.py`、`test_managed_cron_feedback.py` 和 `test_managed_board_api.py`。
4. [x] 运行受影响的 Scheduler、SWE 和 Monitor 测试，检查跨服务状态契约与部署文档。

## 单任务「立即执行」

1. [x] 增加手动 API 受理后派发以及无批容量领取的回归测试。
2. [x] 将独立 `manual` 执行纳入直接派发与故障恢复，从批 Worker 候选、占位、反馈和 Monitor 明细排除。
3. [x] 复跑 Cron 回归，确认实际批任务仍受同一个 Worker 容量限制。
