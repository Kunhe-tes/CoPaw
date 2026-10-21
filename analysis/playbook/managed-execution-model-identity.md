# 新版批调度的任务 ID 与实际模型

- 执行成员行中任务名下方展示 `job_id`，它是定时任务 ID；`execution_id` 标识一次执行，不能替代任务 ID。
- 看板模型字段直接来自 `swe_cron_execution_runs.provider_id/model_id`，不能仅改前端把 `default` 翻译成模型名称。
- Agent 入队时，Scheduler 调用 SWE `/api/internal/cron/managed/resolve-model`，按目标 tenant/source 的 ProviderManager 解析有效模型，写入运行记录及执行快照 `model_slot`。任务定义仍保留“跟随用户默认配置”的选择；不同次执行分别解析，同一次重复受理复用已有快照。
- 解析失败不创建带占位模型的 Agent 运行；需同时部署 SWE 模型解析接口和 Scheduler 入队变更。批任务按接收人的配置分别解析，不能借用父任务或调度操作者的默认模型。
- 执行器发生模型回退时，结果提交使用 `execution_meta.effective_model_slot` 更新运行记录中的实际模型；调度请求元数据保留原冻结池信息，供审计原始调度决策。
- Workflow 沿用发布绑定里的模型解析。纯文本不调用模型，保留既有容量分组，不从用户默认配置伪造一次模型调用。
- 历史 `default/default` 记录只能从该次执行的结果 JSON 或历史 `meta.execution.effective_model_slot` 核验实际模型，不能用用户今天的默认配置覆盖历史。此次不自动改写历史数据。

回归入口：`test_managed_cron_resolved_model.py`、`test_managed_cron_model_resolution.py`、`test_managed_cron_execution_pool.py`、`BatchDetail.test.tsx`。
