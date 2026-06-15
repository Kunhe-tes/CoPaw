# API 创建每日 Agent 任务

这个示例演示用 `POST /api/cron/jobs` 创建一个每日 Agent 定时任务，然后查询、手动运行和标记已读。

返回 [Cron 示例索引](../README.md)。

## 创建任务

先复制同目录下的 [spec.json](spec.json)，按环境替换：

- `dispatch.target.user_id`
- `dispatch.target.session_id`
- `request.session_id`
- `schedule.cron`
- `schedule.timezone`
- `request.input[0].content[0].text`

然后发送请求：

```powershell
$baseUrl = "http://127.0.0.1:8088"

curl.exe -X POST "$baseUrl/api/cron/jobs" `
  -H "Content-Type: application/json" `
  -H "X-Tenant-Id: tenant-a" `
  -H "X-Source-Id: RMASSIST" `
  -H "X-Agent-Id: default" `
  -H "X-User-Id: user-001" `
  --data-binary "@wiki/cron/examples/api-agent-daily/spec.json"
```

服务端会忽略 `spec.json` 里的 `id`，返回真实 `id`：

```json
{
  "id": "0f6f7c62-4c51-4c5c-93b1-6a8dd2d9a0c1",
  "name": "每日经营摘要",
  "enabled": true,
  "tenant_id": "tenant-a",
  "source_id": "RMASSIST",
  "scope_id": "tenant-a-RMASSIST",
  "task_type": "agent"
}
```

实际返回还会包含完整 `schedule`、`request`、`dispatch`、`runtime`、`meta` 等字段。

## 查询任务

```powershell
$jobId = "0f6f7c62-4c51-4c5c-93b1-6a8dd2d9a0c1"

curl.exe "$baseUrl/api/cron/jobs/$jobId" `
  -H "X-Tenant-Id: tenant-a" `
  -H "X-Source-Id: RMASSIST" `
  -H "X-Agent-Id: default" `
  -H "X-User-Id: user-001"
```

重点看三组字段：

- `spec.schedule.cron`：5 字段 cron，星期会被标准化成 `mon` / `tue` 等英文缩写。
- `state.next_run_at`：由 `CronManager.refresh_next_run_at()` 计算。
- `task.unread_execution_count`：任务卡片上是否还有未读执行结果。

## 手动运行一次

```powershell
curl.exe -X POST "$baseUrl/api/cron/jobs/$jobId/run" `
  -H "X-Tenant-Id: tenant-a" `
  -H "X-Source-Id: RMASSIST" `
  -H "X-Agent-Id: default"
```

手动运行会走 `CronManager.run_job(is_manual=True)`，不会修改外部调度平台配置。执行完成后，Monitor execution 会记录为手动执行。

## 标记任务结果已读

```powershell
curl.exe -X POST "$baseUrl/api/cron/jobs/$jobId/task/mark-read" `
  -H "X-Tenant-Id: tenant-a" `
  -H "X-Source-Id: RMASSIST" `
  -H "X-Agent-Id: default" `
  -H "X-User-Id: user-001"
```

如果返回：

```json
{"marked_read": true}
```

说明 SWE 侧任务卡片已读状态已经更新，并会继续同步 Monitor 的已读状态。
