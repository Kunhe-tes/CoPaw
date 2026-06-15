# Cron 广播与系统任务

本文说明 cron 广播任务、heartbeat / dream 系统任务，以及当前代码中 Redis coordination 原语与实际装配状态之间的边界。

返回 [Cron 定时任务模块索引](README.md)。

## 广播任务

广播接口：

```http
POST /api/cron/jobs/{job_id}/broadcast
```

请求体：

```json
{
  "targets": [
    {
      "tenant_id": "tenant-a",
      "tenant_name": "Alice",
      "bbk_id": "1001"
    },
    {
      "tenant_id": "tenant-b",
      "tenant_name": "Bob",
      "bbk_id": "2002"
    }
  ],
  "target_tenant_ids": ["tenant-a", "tenant-b"]
}
```

`targets` 是当前推荐格式，用于把目标租户展示身份一起传给 SWE；`target_tenant_ids` 仍保留兼容旧调用方。如果两者都传，后端以 `targets` 为准。

广播会做这些事：

1. 校验目标租户 ID，去重。
2. 根据目标数量用 `compute_broadcast_offsets()` 在 4 小时窗口内均匀计算错峰分钟数。
3. 用 `shift_cron_expression()` 尝试把 cron 向前平移 offset。
4. 如果 cron 无法安全平移，保留原 cron，并返回 fallback warning。
5. 为每个目标租户找对应 runtime workspace 和 `CronManager`。
6. 如果目标租户已有同一个 `broadcast_source_job_id` 的子任务，刷新已有子任务的任务定义配置，不重复创建。
7. 尝试复制源任务的 `model_slot`；目标租户缺 provider/model 时回退默认模型，并写 fallback meta。
8. 创建或刷新子任务，子任务 `meta.broadcast_source_job_id` 指向源任务。
9. 如果请求体带 `targets`，把目标租户的 `tenant_name`、`bbk_id` 写入子任务顶层字段；`tenant_id`、`request.user_id`、`dispatch.target.user_id` 都切到目标租户。

广播相关 meta：

| meta 字段 | 含义 |
| --- | --- |
| `broadcast_source_job_id` | 源任务 ID |
| `broadcast_original_cron` | 源任务原 cron |
| `broadcast_original_timezone` | 源任务原时区 |
| `broadcast_offset_minutes` | 目标租户错峰分钟数 |
| `broadcast_notification_policy` | 当前为 `original_schedule` |
| `broadcast_original_model_slot` | 目标租户模型不可用时保存源模型 |
| `broadcast_model_slot_fallback_reason` | 模型回退原因 |

当前 `v1.0.0` 基线已包含 `0732cdea fix(cron): reduce broadcast API complexity`、`f24ad72a fix(cron): skip duplicate broadcast child jobs` 和 `51febe0a fix(cron): persist broadcast target identity`。如果排查广播子任务展示身份丢失，优先看 `CronBroadcastTarget`、`_normalize_broadcast_targets()` 和 `_build_broadcast_job()`。

当前本地修改改变了重复分发语义：重新分发到已有子任务时，后端会覆盖执行内容、执行类型、cron、时区、runtime、model slot、通知延迟和广播 meta 等用户无关配置，同时保留子任务 ID、目标用户身份、任务卡片绑定和暂停/启停状态。分发后的子任务可以在定时任务菜单中用“查看分发用户”反查、批量删除或批量重跑，详细见 [Cron 分发子任务管理](cron-distribution-management.md)。

## Source 级会话历史清理系统任务

定时任务会话历史清理不是普通 tenant workspace 下的业务 cron。当前实现把它收敛为 source 级系统任务：同一个 `source_id` 只注册一条外部调度任务，执行时覆盖该 source 下所有已初始化的 tenant/runtime scope。

配置仍然放在 source 系统特性配置中：

```text
swe_source_system_config.config_text
└── cron_task_session_cleanup
    ├── enabled
    ├── retention_days
    └── cron
```

外部调度任务 ID 不再写回每个 tenant 的 `system_jobs.json`，而是通过 `swe_source_system_task_binding` 按 source 维度持久化：

| 字段 | 含义 |
| --- | --- |
| `source_id` | 当前 source |
| `task_type` | 当前固定为 `task_session_cleanup` |
| `external_job_id` | 外部调度平台返回的任务 ID |
| `cron` | 当前 source 配置里的清理 cron |
| `enabled` | 当前任务是否启用 |
| `scheduler_tenant_id` | 最后修改该配置时用于注册调度平台的 tenant 身份 |
| `scheduler_from_id` | 最后修改该配置时用于注册调度平台的 fromId |
| `updated_by` | 最后修改配置的用户 |

表里不保存 `scheduler_scope_id`。注册外部调度时也不显式传 `scope_id`，而是复用普通定时任务的默认规则，由 `RealSchedulerAdapter._build_job_param()` 生成：

```text
scopeId = tenant_id-source_id
fromId = from_id or tenant_id
```

这里的 `tenant_id` 和 `fromId` 只用于满足调度平台回调、审计和兼容参数要求；任务唯一性和清理范围只由 `source_id + task_type` 决定。

注册和刷新入口：

1. `_app.py` 初始化 `SourceSystemTaskScheduler`，只要求 DB 可用；本地 Noop 调度适配器也会走同一套 source scheduler 装配。
2. source 系统特性配置保存、命名 source 更新或删除后，`source_system_config/router.py` 调用 `_refresh_cleanup_source_task()`。
3. `SourceSystemTaskScheduler.refresh_task_session_cleanup()` 读取 effective `cron_task_session_cleanup` 配置。
4. 如果 `enabled=false` 且已有外部任务，暂停同一条外部任务并更新 binding。
5. 如果 `enabled=true` 且已有 `external_job_id`，更新并恢复同一条外部任务。
6. 如果 `enabled=true` 且没有 `external_job_id`，创建一条 source 级外部任务，并把返回 ID 写入 binding。

外部调度平台上的清理任务名称使用 source 维度，不拼接 `agentId` 或 `tenant_id`：

```text
[SWE] <source_id>/task_session_cleanup
```

回调执行入口仍是统一的：

```http
POST /api/internal/cron/callback
```

当 `jobParam.task_type == "cleanup"` 时，`internal_cron_callback()` 不再按单个 tenant workspace 找 `CronManager`，而是调用 `app.state.source_system_task_scheduler.run_task_session_cleanup(source_id=...)`。执行器会通过 tenant 初始化来源表查询该 source 下的 tenant/scope，逐个构造 runtime tenant id，再调用各 workspace 的 `CronManager.run_task_session_cleanup()` 复用原有清理逻辑。

这意味着：

- 改配置的人是谁，payload 里的 `tenant_id` / `fromId` 就是谁的 tenant 身份。
- payload 里的 `scopeId` 是调度平台注册参数，默认形如 `tenant_id-source_id`，不参与 source 级清理范围判断。
- 多个 tenant 属于同一个 source 时，不会因为各自 workspace 初始化而各注册一条清理任务。
- `CronManager.initialize()` 不再负责注册任务会话历史清理；它仍然负责 heartbeat / dream 等 tenant workspace 系统任务。
- 如果环境曾经创建过带 `scheduler_scope_id` 的旧 binding 表结构，执行 `scripts/sql/migrate_source_system_task_binding_drop_scope.sql` 删除不再使用的列。

## Heartbeat 与 Dream

CronManager 还会注册两个系统任务：

| 系统任务 | job_id | 执行入口 | 用途 |
| --- | --- | --- | --- |
| heartbeat | `_heartbeat` | `CronManager.run_heartbeat()` | 按 `HEARTBEAT.md` 发起心跳 query |
| dream | `_dream` | `CronManager.run_dream()` | 调用 memory manager 的 dream memory |

heartbeat 的具体执行在 `src/swe/app/crons/heartbeat.py`：

- 读取 workspace 下的 `HEARTBEAT.md`。
- 检查 heartbeat config 的 active hours。
- 如果 target 是 `last`，把流式结果分发到最近一次 dispatch channel。
- 否则只运行 agent，不向用户通道分发。
- 默认也使用 cron workload 和 7200 秒超时。

dream 会在 tenant/source 上下文内调用：

```python
self._runner.memory_manager.dream_memory(
    tenant_id=runtime_tenant_id,
    trigger="cron",
)
```

## 多实例与 Redis coordination

当前代码里有 `src/swe/app/crons/coordination.py`，它提供 Redis lease、definition lock、reload pub/sub 和 scheduler preflight 等原语。

但按当前 `v1.0.0` 代码检索，`CronCoordination` 没有接入 `Workspace` 的 `CronManager` 构造路径。当前主运行合同仍然是：

```text
外部调度平台到点回调 -> /api/internal/cron/callback -> runtime tenant workspace -> CronManager
```

因此，多实例部署时实际要重点保证：

- 外部调度平台回调里的 `tenant_id/source_id/agent_id/job_id` 正确。
- `resolve_runtime_tenant_id(tenant_id, source_id)` 能找到正确 workspace。
- 通知 worker 用 `SWE_CRON_NOTIFICATION_SOURCE_IDS` 限制领取范围。
- `jobs.json` 不要被多个无协调实例当成同一个强一致共享文件并发写。
