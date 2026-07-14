# 批调度 Scheduler 实现说明

## 背景

本次实现把广播定时任务的批量分发从 SWE 的定时扫描改成外部调度平台触发 Scheduler，再由 Scheduler 按 worker 槽位触发 SWE callback。SWE 仍然负责具体任务执行，Scheduler 只负责批次编排、并发控制、失败反馈和调度记录。

核心约束：

- 外部调度平台只触发父任务的物理定时器。
- Scheduler 不主动扫描父任务。
- 父任务和子任务进入同一个排序队列，不给父任务特殊优先级。
- worker 槽位按 `source_id + provider_id + model_id` 维度控制。
- 某个任务完成或失败并回传后，Scheduler 立即补发下一个待执行 intent。
- 关闭父任务批调度时支持回滚：父任务 callback 切回 SWE，子任务恢复外部调度平台注册或启用。

## 新增数据表

### `swe_cron_dispatch_batches`

记录每次父任务被外部平台触发后形成的批次。

关键字段：

- `batch_id`：批次主键，由 `parent_job_id + scheduled_fire_at` 哈希生成。
- `parent_job_id`：父任务 ID。
- `parent_external_job_id`：父任务在外部调度平台的 ID。
- `tenant_id/source_id/agent_id`：父任务运行身份。
- `scheduled_fire_at`：父任务本次理论触发时间。
- `callback_received_at`：Scheduler 收到 callback 的时间。
- `status/total_count/completed_count/failed_count/completed_at`：批次聚合状态。
- `callback_metadata`：外部平台 callback 原始参数。

幂等键：`(parent_job_id, scheduled_fire_at)`。

### `swe_cron_dispatch_intents`

记录批次内实际要触发 SWE callback 的 parent/child 执行 intent。

关键字段：

- `batch_id`：所属批次。
- `intent_role`：`parent` 或 `child`。
- `status`：`pending/claimed/dispatched/completed/failed/cancelled`。
- `source_id/provider_id/model_id`：worker scope。
- `tenant_id/agent_id/job_id/parent_job_id`：SWE callback 路由信息。
- `scheduled_fire_at`：父任务理论触发时间，传给 SWE 用于通知时间计算。
- `due_at/dispatch_order/viewer_heat_score`：领取与排序依据。
- `attempt_count/max_attempts`：重试计数。
- `payload`：传给 SWE callback 的补充元数据。

重复 callback 不会重开 `completed/failed/cancelled` 等终态 intent；`pending` 领取也要求 `attempt_count < max_attempts`。

### `swe_cron_dispatch_events`

记录关键事件：

- `batch_callback_received`
- `parent_execution_intent_queued`
- `child_execution_intent_queued`
- `callback_dispatched`
- `child_execution_completed`
- `child_execution_failed`
- `retry_scheduled`
- `child_execution_missing_failed`
- `execution_intent_mismatch`
- `execution_attempt_mismatch`

### `swe_cron_dispatch_worker_capacity`

记录每次 worker 容量初始化或调整快照。

关键字段：

- `worker_id`
- `source_id/provider_id/model_id`
- `strategy_id`
- `previous_workers/baseline_workers/min_workers/max_workers/effective_workers`
- `pending_count/claimed_count/running_count`
- `success_count/failure_count/error_rate`
- `matched_rule/decision_reason`

容量读取按 `source_id/provider_id/model_id/strategy_id/worker_id` 找最新快照。写入时间按现有执行记录存储约定落北京时间 naive，读取时按北京时间还原，避免调整间隔误差。

### `swe_cron_dispatch_model_worker_policy`

配置某个 `source_id + provider_id + model_id` 使用哪个策略。

字段：

- `source_id/provider_id/model_id`：主键。缺省使用 `default`。
- `default_strategy_id`：默认策略。
- `strategy_schedule`：按时间段切换策略的 JSON 配置。
- `enabled`：启停。

策略查找顺序从精确匹配逐步回退到 default source/default provider/default model。

### `swe_cron_dispatch_worker_strategy`

配置 worker 调整策略。

字段：

- `strategy_id`
- `min_workers/baseline_workers/max_workers`
- `adjust_interval_seconds`
- `feedback_window_seconds`
- `stale_execution_seconds`
- `error_rate_rules`

`error_rate_rules` 支持按错误率区间执行 `add/subtract/multiply/divide/set/hold`。

示例：

```json
[
  {
    "min_error_rate": 0.5,
    "operation": "multiply",
    "value": 0.5,
    "reason": "high_error_rate"
  },
  {
    "min_error_rate": 0,
    "max_error_rate": 0,
    "operation": "add",
    "value": 1,
    "reason": "stable_success"
  }
]
```

## 整体调用流程

### 开启批调度

1. 前端任务表单打开父任务 `meta.broadcast_dispatch_intents_enabled`。
2. SWE 保存父任务。
3. `CronManager` 识别它是批调度父任务，外部调度平台 job 的 `jobAddress` 注册为 Scheduler callback：`/api/scheduler/cron/callback`。
4. 异步处理已有广播子任务：给 child 写入 `broadcast_dispatch_intents_enabled=true`。
5. child 保存时 `CronManager` 识别它是批调度 child：
   - 如果已有 `external_job_id`，暂停外部调度平台 job。
   - 如果没有 `external_job_id`，不再注册外部调度平台 job。

### 新广播时使用批调度

1. 前端广播弹窗勾选 `enable_batch_dispatch`。
2. 后端先把 parent meta 更新为 `broadcast_dispatch_intents_enabled=true`，并通过 `CronManager` 重新注册父任务到 Scheduler callback。
3. 本次生成/刷新 child 时写入 `broadcast_dispatch_intents_enabled=true`。
4. child 外部调度同样被暂停或跳过注册。

### 外部调度平台触发

1. 外部平台按父任务 cron 触发 `jobAddress=/api/scheduler/cron/callback`。
2. Scheduler 从 `jobParam` 解码 `tenant_id/source_id/agent_id/job_id`。
3. Scheduler 不校验 callback token，直接按 `jobParam` 解析父任务身份。
4. Scheduler 查询父任务和批调度 child。
5. Scheduler 建立 batch，并把 parent + child 全部写入同一个 intent 队列。
6. Scheduler 按 `viewer_heat_score`、`due_at`、`tenant_id`、`job_id` 计算稳定排序。
7. Scheduler 按 scope 当前 `effective_workers` 领取可执行 intent 并调用 SWE `/api/internal/cron/callback`。

### SWE 执行和反馈

1. SWE internal callback 接收 Scheduler 触发请求。
2. SWE 把 `cron_dispatch` 写入执行 meta：
   - `intent_id`
   - `batch_id`
   - `dispatch_attempt`
   - `parent_scheduled_fire_at`
   - `provider_id/model_id`
3. SWE 正常执行任务。
4. SWE 执行记录同步发现执行 meta 里有 `cron_dispatch`，改为同步上报 Scheduler `/api/scheduler/cron/execution`。
5. Scheduler 根据 `intent_id + batch_id + dispatch_attempt` 更新 intent。
6. 如果 intent 进入完成或失败状态，Scheduler 刷新 batch 计数并立即补发下一个 pending intent。

## Worker 调整逻辑

pending intent 不是周期性扫描派发。派发入口只有两个：

- 父任务 callback 建立 batch 后，按当前 worker 槽位做初始派发。
- SWE 执行反馈进入完成或失败状态后，Scheduler 立即补发下一个 pending intent。

调度循环不扫描父任务，也不领取普通 pending intent，只按 DB 策略里的 `adjust_interval_seconds` 做 worker 容量维护。进程内部会定期醒来检查一次，但实际是否调整由数据库策略控制。每次派发时才会：

- 恢复 stale dispatched intent。
- 按 scope 读取当前策略。
- 计算当前 in-flight 数量：`claimed_count + running_count`。
- 可用槽位：`effective_workers - in_flight`。
- 领取并发送 pending intent。

当前只关心失败率，不区分失败、超时、限流等内部原因。失败统计包括：

- terminal `failed` intent。
- `retry_scheduled` 事件。
- stale 后超过最大次数的 `child_execution_missing_failed`。

## 通知时间变化

旧广播错峰模式下，子任务通知时间是：

`子任务完成时间 + broadcast_offset_minutes + notification_delay_minutes`

批调度模式下，子任务没有广播偏移，因此改为：

`父任务 scheduled_fire_at + notification_delay_minutes`

SWE 通过 `cron_dispatch.parent_scheduled_fire_at` 识别批调度执行，并保留 `broadcast_original_timezone` 作为通知时区。

## 回滚流程

关闭父任务 `broadcast_dispatch_intents_enabled` 后：

1. SWE 保存父任务。
2. 父任务重新同步外部调度平台，callback 切回 SWE `/api/internal/cron/callback`。
3. 后端异步处理 child：
   - 删除 child 的 `broadcast_dispatch_intents_enabled` 和旧 `dispatch_intents_enabled`。
   - 调用 child 所在 tenant 的 `CronManager.create_or_replace_job()`。
   - child 恢复或补注册外部调度平台 job。

维护接口和启动恢复也补齐了批调度分支：

- 批调度 child 即使保留 `external_job_id`，也会被暂停。
- 批调度 parent 缺失 `external_job_id` 时，恢复注册到 Scheduler callback，不会误注册到 SWE callback。

## 关键日志

Scheduler：

- `scheduler_parent_callback_received`
- `scheduler_parent_jobs_fetched`
- `scheduler_worker_initial_capacity`
- `scheduler_swe_callback_attempt`
- `scheduler_execution_feedback`
- `scheduler_dispatch_task_finished`
- `scheduler_worker_adjustment`

SWE：

- batch child 跳过注册或暂停外部调度平台。
- parent 注册外部调度平台 callback。
- dispatch-managed execution 上报 Scheduler 成功/失败。

## 配置项

Scheduler：

- 新增 `scheduler.config.constant` 和 `scheduler.config.envs/dev.json`、`prd.json`。
- `SCHEDULER_ENV`、`SCHEDULER_LOG_LEVEL`、`SCHEDULER_OPENAPI_DOCS`、`SCHEDULER_HOST`、`SCHEDULER_PORT`：Scheduler 服务自身配置。
- `SCHEDULER_DB_HOST`、`SCHEDULER_DB_PORT`、`SCHEDULER_DB_USER`、`SCHEDULER_DB_ACCESS`、`SCHEDULER_DB_NAME`、`SCHEDULER_DB_MIN_CONN`、`SCHEDULER_DB_MAX_CONN`：Scheduler 访问批调度表的数据库配置。
- `SCHEDULER_SWE_API_BASE_URL`：Scheduler 调 SWE internal callback 的 base URL。
- `SCHEDULER_CRON_DISPATCHED_STALE_SECONDS`：派发入口处理 dispatched 超时回收时使用；父任务发现只由外部调度平台 callback 触发，不再配置 due lookback。
- Scheduler 启动时会按 Monitor 的方式先读取 `SCHEDULER_SECRET_DIR/envs.json`，再读取包内 `scheduler/config/envs/{SCHEDULER_ENV}.json` 默认值；两层都不会覆盖进程里已经显式传入的环境变量。
- Docker 部署如果依赖持久化 envs，需要把包含 `SCHEDULER_DB_HOST` 等数据库配置的目录挂载给 Scheduler，并设置 `SCHEDULER_SECRET_DIR` 指向该目录；也可以直接通过容器环境变量传入 `SCHEDULER_DB_*`。
- Scheduler 初始化只建立数据库连接池，不自动建表；表结构由部署流程使用 `scripts/sql/cron_tables.sql` 或 DBA 单独初始化。`SCHEDULER_DB_INIT_TABLES` 保留为兼容字段，但启动流程不再执行 DDL。
- 批调度识别只认 `broadcast_dispatch_intents_enabled=true`；旧字段 `dispatch_intents_enabled` 不再作为兼容开关，只在保存或关闭批调度时被清理。

独立部署边界：

- Scheduler 包内不引用 `monitor.app.*`。
- Scheduler 只读取 `SCHEDULER_*` 环境变量，不读取其他服务的环境变量作为 fallback。
- 如果 Scheduler 连接既有 cron 数据库，由部署层显式配置 `SCHEDULER_DB_*`。
- 如果 Scheduler 调同一个 SWE 地址，由部署层显式配置 `SCHEDULER_SWE_API_BASE_URL`。

SWE：

- `SWE_CRON_DISPATCH_INTENTS_ENABLED=1`：SWE 与 Scheduler 共同使用的批调度总开关。
- `SWE_SCHEDULER_API_URL`：SWE 调 Scheduler 的 base URL，默认 `http://localhost:9100/api`。
- `SWE_SERVER_DOMAIN`：父任务注册到外部调度平台时使用的普通 SWE callback base URL。

内部 token：

- Scheduler callback/execution 不做 `X-Internal-Token` 校验。
- Scheduler 调 SWE callback 仍沿用 SWE internal callback 的现有鉴权方式，优先使用 SWE 实际接受的 `SWE_INTERNAL_TOKEN`；如需 Scheduler 侧单独配置，可使用 `SCHEDULER_SWE_INTERNAL_TOKEN`。

## 验证

已运行：

```powershell
python -m py_compile scheduler/src/scheduler/app/_app.py scheduler/src/scheduler/app/database/connection.py scheduler/src/scheduler/app/database/schema.py scheduler/src/scheduler/app/models/cron.py scheduler/src/scheduler/app/routers/cron.py scheduler/src/scheduler/app/services/cron/execution_sync_service.py scheduler/src/scheduler/app/services/cron/scheduling_service.py scheduler/src/scheduler/app/services/cron/dispatch_intent_service.py tests/unit/scheduler/test_scheduler_app.py tests/unit/scheduler/test_cron_dispatch_intent_service.py tests/unit/scheduler/test_cron_scheduling_service.py
git diff --check
```

未运行：

- `pytest`：当前 `D:\Anaconda\python.exe` 没有安装 `pytest`。
- 前端测试/构建：当前 worktree 没有 `node_modules`，`pnpm` 也不可用。

## 代码检视修复点

本次多轮检视后已修复：

- 关闭父任务批调度时回滚入口不可达。
- Scheduler `/execution` 反馈入口一度补了鉴权，后续按当前设计移除。
- Scheduler 调 SWE callback 的 token 优先级与 SWE 校验不一致。
- 批调度 child 残留 `external_job_id` 时维护接口直接跳过。
- 重复 parent callback 会重开 terminal failed/cancelled intent。
- capacity 快照时区读写不一致。
- batch 唯一键与 batch_id 维度不一致。
- 策略切换后 capacity 快照未按 `strategy_id` 隔离。
- 默认 source 的 provider/model 策略匹配不完整。
- stale dispatched intent 终态失败后未刷新 batch 汇总。
- parent 缺失 `external_job_id` 恢复时误注册到 SWE callback。
- 新广播勾选批调度只影响 child、不更新 parent。
- 外部平台无法传 header 时 Scheduler callback 鉴权不可达，因此当前设计不做 Scheduler 入站 token 校验。
