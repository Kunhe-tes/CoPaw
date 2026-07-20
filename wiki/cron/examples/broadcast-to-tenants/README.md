# 广播任务到多个租户

这个示例演示把一个源租户的 cron 任务异步广播到多个目标租户。POST 只创建或复用后台任务；调用方需要轮询任务状态，完成后才能把 `results` 当成最终结果。

返回 [Cron 示例索引](../README.md)。

## 查询可广播租户

```powershell
$baseUrl = "http://127.0.0.1:8088"

curl.exe "$baseUrl/api/cron/broadcast/tenants" `
  -H "X-Tenant-Id: tenant-a" `
  -H "X-Source-Id: RMASSIST" `
  -H "X-Agent-Id: default"
```

返回示例：

```json
{
  "tenant_ids": ["tenant-b", "tenant-c", "tenant-d"]
}
```

## 广播源任务

```powershell
$jobId = "0f6f7c62-4c51-4c5c-93b1-6a8dd2d9a0c1"

$body = @{
  targets = @(
    @{
      tenant_id = "tenant-b"
      tenant_name = "Bob"
      bbk_id = "2002"
    },
    @{
      tenant_id = "tenant-c"
      tenant_name = "Carol"
      bbk_id = "3003"
    }
  )
  target_tenant_ids = @("tenant-b", "tenant-c")
  enable_offset = $true
  offset_window_hours = 4
} | ConvertTo-Json -Depth 5

curl.exe -X POST "$baseUrl/api/cron/jobs/$jobId/broadcast" `
  -H "Content-Type: application/json" `
  -H "X-Tenant-Id: tenant-a" `
  -H "X-Source-Id: RMASSIST" `
  -H "X-Agent-Id: default" `
  -d $body
```

`targets` 是推荐字段，能让后端把目标租户展示身份持久化到子任务；`target_tenant_ids` 仍保留兼容旧调用方。`enable_offset` 默认开启，设为 `$false` 时所有目标沿用原 cron；`offset_window_hours` 默认 4，取值 1-24。

首次返回示例：

```json
{
  "task_id": "broadcast-task-id",
  "status": "running",
  "tenant_count": 2,
  "completed_count": 0,
  "failed_count": 0,
  "results": [],
  "reused": false
}
```

轮询指定任务：

```powershell
$taskId = "broadcast-task-id"

curl.exe "$baseUrl/api/cron/jobs/$jobId/broadcast/tasks/$taskId" `
  -H "X-Tenant-Id: tenant-a" `
  -H "X-Source-Id: RMASSIST" `
  -H "X-Agent-Id: default"
```

也可以查询该源任务当前运行中或最近一次广播任务：

```powershell
curl.exe "$baseUrl/api/cron/jobs/$jobId/broadcast/tasks/current" `
  -H "X-Tenant-Id: tenant-a" `
  -H "X-Source-Id: RMASSIST" `
  -H "X-Agent-Id: default"
```

完成后的响应才会包含最终结果，例如：

```json
{
  "task_id": "broadcast-task-id",
  "status": "completed",
  "tenant_count": 2,
  "completed_count": 2,
  "failed_count": 0,
  "results": [
    {
      "tenant_id": "tenant-b",
      "success": true,
      "job_id": "broadcast-child-job-id-1",
      "cron": "30 9 * * mon-fri",
      "timezone": "Asia/Shanghai",
      "offset_minutes": 0,
      "notification_timezone": "Asia/Shanghai",
      "error": "",
      "warning": ""
    },
    {
      "tenant_id": "tenant-c",
      "success": true,
      "job_id": "broadcast-child-job-id-2",
      "cron": "35 9 * * mon-fri",
      "timezone": "Asia/Shanghai",
      "offset_minutes": 5,
      "notification_timezone": "Asia/Shanghai",
      "error": "",
      "warning": ""
    }
  ],
  "reused": false
}
```

## 子任务会带上的 meta

目标任务会在 `meta` 里记录广播来源，便于后续排查：

```json
{
  "broadcast_source_job_id": "0f6f7c62-4c51-4c5c-93b1-6a8dd2d9a0c1",
  "broadcast_original_cron": "30 9 * * mon-fri",
  "broadcast_original_timezone": "Asia/Shanghai",
  "broadcast_offset_minutes": 5,
  "broadcast_notification_policy": "original_schedule"
}
```

目标任务顶层字段还会保存请求里的目标身份：

```json
{
  "tenant_id": "tenant-c",
  "tenant_name": "Carol",
  "bbk_id": "3003",
  "source_id": "RMASSIST",
  "scope_id": "tenant-c-RMASSIST"
}
```

如果源任务绑定了 `model_slot`，目标租户也必须存在同名 provider 和 model；否则广播会 fallback 到目标租户默认模型，并在 `warning` 和 `meta` 中记录原因。

## 排查重点

- 如果目标租户已经有同源子任务，API 会刷新已有子任务，不重复创建。
- 如果首次 POST 的 `results` 为空，这是异步任务正常状态；先按 `task_id` 轮询，不要立即判断广播失败。
- 如果已有广播或模式同步任务运行，响应可能带 `reused=true`；不要并发重复提交。
- 如果错峰时间看起来不对，先看返回的 `offset_minutes` 和子任务 `meta.broadcast_original_cron`。
- 如果子任务展示身份缺失，先确认请求体是否传了 `targets[].tenant_name` 和 `targets[].bbk_id`，再看 `src/swe/app/crons/api.py` 的 `_normalize_broadcast_targets()` 与 `_build_broadcast_job()`。
