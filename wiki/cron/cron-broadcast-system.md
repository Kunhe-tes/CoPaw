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
6. 如果目标租户已有同一个 `broadcast_source_job_id` 的子任务，跳过重复创建并返回 warning。
7. 尝试复制源任务的 `model_slot`；目标租户缺 provider/model 时回退默认模型，并写 fallback meta。
8. 创建子任务，子任务 `meta.broadcast_source_job_id` 指向源任务。
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
