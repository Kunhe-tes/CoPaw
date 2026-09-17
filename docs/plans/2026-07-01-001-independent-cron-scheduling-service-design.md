---
title: Physical Cron Scheduler Service Design
status: active
created: 2026-07-01
updated: 2026-07-02
adr: docs/adr/0010-independent-cron-scheduling-service-owns-batch-dispatch.md
---

# 独立定时调度服务详细设计

## 1. 背景和边界修正

上一版把调度 loop 放在 Monitor 进程里，虽然逻辑上已经脱离 SWE，但物理边界仍然不够清晰。当前边界调整为：

- `scheduler` 是新的顶层服务，拥有调度 loop、intent claim、callback 分发、失败重试、capacity 调整和调度事件。
- `monitor` 只保留 cron 定义、execution 记录、dispatch 表的数据库连接和观测查询能力，不再启动调度 loop。
- `swe` 只负责执行已有任务，入口仍是 `POST /api/internal/cron/callback`。
- 外部调度平台 callback 不触发 batch-managed parent/child；只有 `callback_source=dispatch_service` 的 Scheduler 请求可以触发。

## 2. 当前实现范围

本次只迁移 batch-managed 广播任务的调度骨架，不迁移所有普通定时任务。

已实现：

- 新增顶层 `scheduler` Python 包和 FastAPI app。
- `CronSchedulingService` 和 `CronDispatchIntentService` 从 Monitor 移到 Scheduler。
- Scheduler lifespan 负责启动 `cron-scheduler-service` loop。
- Monitor lifespan 不再导入或启动调度 loop。
- SWE dispatch-managed execution feedback 发送到 Scheduler `/api/scheduler/cron/execution`。
- Scheduler 收到 execution feedback 后，先调用 Monitor `SyncService.record_execution()` 持久化 execution row，再更新 intent 并立即尝试补发下一条任务。
- 普通非 dispatch execution 仍然走 Monitor fire-and-forget 双写。

未实现：

- 不把所有普通定时任务迁入 Scheduler。
- 不替换现有外部调度平台对普通任务的触发。
- 不实现 Scheduler 多实例 leader lease。
- 不新增完整运维 UI。

## 3. 运行流程

### 3.1 外部 callback 兼容

1. 外部调度平台调用 SWE `/api/internal/cron/callback`，请求没有 `callback_source=dispatch_service`。
2. SWE 识别 batch-managed parent/child。
3. SWE 返回 skip，不执行任务，也不创建 dispatch intent。

### 3.2 Scheduler 分发 child job

1. Scheduler 扫描 Monitor 同步的 cron job 表，找到 due 的 batch parent。
2. Scheduler 创建 parent intent，并根据 parent payload 或 child job 查询创建 child intents。
3. Scheduler `dispatch_ready_once()` claim due intents。
4. 对 child intent，Scheduler 调用 SWE `/api/internal/cron/callback`，body 带：
   - `callback_source=dispatch_service`
   - `tenant_id`
   - `source_id`
   - `agent_id`
   - `task_type=job`
   - `job_id`
   - `dispatch_intent_id`
   - `dispatch_batch_id`
5. SWE 只在来源为 `dispatch_service` 时允许 batch-managed child 执行。
6. SWE execution meta 写入 `cron_dispatch`。
7. SWE 把 dispatch-managed execution feedback 发给 Scheduler。
8. Scheduler 持久化 execution row，更新 intent 为 completed/retry/failed，并立即尝试补发下一条任务。

## 4. 分发和容量调整

分发路径只做：

- stale dispatched 回收；
- claim due intent；
- 扩展 parent 或 callback 到 SWE；
- 写 intent/event 状态。

容量调整只由 `adjust_worker_capacity_if_due()` 触发：

- 未到 `capacity_adjust_interval_seconds` 直接返回；
- 到间隔后读取近期完成状态；
- 有失败、超时、限流时快速降 worker；
- 连续成功且有 backlog 时缓慢升 worker；
- 每次决策写 `swe_cron_dispatch_worker_capacity`。

因此“完成后立即补发”和“按时间窗口调整 worker”互不阻塞。

## 5. 失败重试和落库

失败分两类：

- callback 前失败：Scheduler 未成功把任务交给 SWE，`fail_intent()` 按 `retry_delay_seconds` 回到 pending，超过 `max_attempts` 后 failed。
- execution 失败：SWE 已启动任务，但最终 execution record 非 success。Scheduler 根据 `cron_dispatch` 找到 intent，未超过 `max_attempts` 则 pending retry，超过后 failed。

日志落库：

- `swe_cron_dispatch_intents`：intent 当前状态、attempt、due_at、lock、error。
- `swe_cron_dispatch_events`：parent queued、child queued、callback dispatched、execution completed、retry scheduled、failed。
- `swe_cron_dispatch_worker_capacity`：worker 决策的 baseline、max、effective、pending/running、失败/限流/延迟信号和 reason。

## 6. 后续迁移所有定时任务

后续如果把定时任务全部迁入 Scheduler，建议分阶段做：

1. Scheduler 接管普通 due-time 计算。
2. 普通 scheduled job 也进入 dispatch intent。
3. 外部 scheduler 降级为兼容层或回滚层。
4. 增加 Scheduler leader lease，支持多实例部署。
5. 补充运维 API/UI，查看 lease、pending/running/completed intents、capacity 历史和失败重试。

本次不实现这些迁移，避免一次性改变普通定时任务的触发语义。

## 7. 验收标准

- Monitor 不启动调度 loop。
- Scheduler 是独立 FastAPI app。
- 外部调度平台 callback 不触发 batch-managed parent/child。
- Scheduler callback 可以触发 batch-managed child。
- Scheduler callback 成功后 intent 进入 `dispatched`，不是直接 `completed`。
- SWE execution meta 携带 intent/batch 信息。
- dispatch-managed execution feedback 发到 Scheduler，并由 Scheduler 更新 intent 后立即补发下一条任务。
- worker capacity 只按可配置间隔调整。
- callback 失败和 execution 失败都能重试并落库。
