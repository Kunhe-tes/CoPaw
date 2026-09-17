# 批调度模式示例

这个示例演示把广播源任务切换到独立 Scheduler 批调度，并从 Monitor 查询批次和模型作用域 worker 状态。

返回 [Cron 示例索引](../README.md)。

## 前置条件

- SWE 与 Scheduler 都配置 `SWE_CRON_DISPATCH_INTENTS_ENABLED=true`。
- SWE 已配置外部调度平台和可达的 `SWE_SERVER_DOMAIN`。
- 独立 Scheduler 默认监听 `http://127.0.0.1:9100`，并已连上 cron 数据库。
- 当前 job 是广播源任务，不是带 `meta.broadcast_source_job_id` 的子任务。

## 启用批调度

```powershell
$baseUrl = "http://127.0.0.1:8088"
$jobId = "0f6f7c62-4c51-4c5c-93b1-6a8dd2d9a0c1"

$body = @{
  offset_window_hours = 4
} | ConvertTo-Json

curl.exe -X POST "$baseUrl/api/cron/jobs/$jobId/batch-dispatch/enable" `
  -H "Content-Type: application/json" `
  -H "X-Tenant-Id: tenant-a" `
  -H "X-Source-Id: RMASSIST" `
  -H "X-Agent-Id: default" `
  -d $body
```

切换成功后重点核对源任务 meta：

```json
{
  "broadcast_dispatch_intents_enabled": true,
  "batch_dispatch_external_job_id": "<external-job-id>",
  "batch_dispatch_offset_window_hours": 4,
  "batch_dispatch_offset_minutes": 240,
  "batch_dispatch_parent_cron": "0 9 * * *",
  "batch_dispatch_cron": "0 5 * * *"
}
```

模式同步在后台执行。源任务已有广播/刷新/模式任务时可能返回 409；先查询广播任务状态，不要并发重试覆盖。

## 查询批次

外部物理 timer 回调 Scheduler 并创建 batch 后，通过 Monitor 查询：

```powershell
$monitorUrl = "http://127.0.0.1:9090"

curl.exe "$monitorUrl/api/monitor/cron/dispatch/batches?page=1&page_size=20" `
  -H "X-Source-Id: RMASSIST"
```

拿到 `batch_id` 后查询 intents 和 events：

```powershell
$batchId = "cron:0123456789abcdef0123456789abcdef"

curl.exe "$monitorUrl/api/monitor/cron/dispatch/batches/$batchId?intent_limit=200&event_limit=500" `
  -H "X-Source-Id: RMASSIST"
```

## 查询 worker 容量

```powershell
curl.exe "$monitorUrl/api/monitor/cron/dispatch/workers" `
  -H "X-Source-Id: RMASSIST"
```

`effective_workers` 是 `source_id + provider_id + model_id` 作用域的并行容量槽位，不是 Scheduler 进程数。intent 卡住时还要结合 scope lease、due_at、attempt 和 event 判断。

## 关闭批调度

```powershell
curl.exe -X POST "$baseUrl/api/cron/jobs/$jobId/batch-dispatch/disable" `
  -H "X-Tenant-Id: tenant-a" `
  -H "X-Source-Id: RMASSIST" `
  -H "X-Agent-Id: default"
```

关闭后批调度物理 timer 暂停，源任务和已知广播子任务恢复普通 timer。`batch_dispatch_external_job_id` 会保留，下一次启用时复用同一外部任务。

## 排查重点

- 没有 batch：先查外部物理 timer 是否 active、回调是否为 Scheduler `/api/scheduler/cron/callback`。
- 有 batch 没有 intents：查父任务是否 active 且 `broadcast_dispatch_intents_enabled=true`，子任务是否同 source 且未删除。
- intent pending：查模型作用域 capacity、lease、due_at 和排序。
- intent dispatched 不结束：查 SWE callback、内部 token、execution meta 和 `/api/scheduler/cron/execution` 回执。
- 不要等待 Scheduler 扫描父任务；只有物理 timer callback 会创建批次。
