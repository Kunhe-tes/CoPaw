# Monitor 与通知排查示例

这个示例演示从 Monitor 侧确认任务定义、执行记录、已读状态和完成通知。适合排查“任务执行了但列表没数据”“成功了但没通知”“任务一直未读”等问题。

返回 [Cron 示例索引](../README.md)。

## 查询 Monitor 任务列表

```powershell
$monitorUrl = "http://127.0.0.1:8090"

curl.exe "$monitorUrl/monitor/cron/jobs?tenant_id=tenant-a&page=1&page_size=20" `
  -H "X-Source-Id: RMASSIST"
```

Monitor 查询接口会按 `X-Source-Id` 过滤数据。如果 SWE 侧创建任务时 `source_id` 为空，而 Monitor 查询时带了 `RMASSIST`，就可能查不到。

## 查询执行记录

```powershell
curl.exe "$monitorUrl/monitor/cron/executions?job_id=<job-id>&page=1&page_size=20" `
  -H "X-Source-Id: RMASSIST"
```

重点看：

- `status`：`success` / `error` / `running` / `cancelled`
- `manual` 或手动执行标记：确认是不是从 `/run` 触发
- `trace_id`：回到 SWE trace 或日志继续查
- `output_preview`：判断 Agent 是否真的产出结果
- `notification_status`：是否进入 pending / sent / failed

## 标记 Monitor 已读

```powershell
curl.exe -X POST "$monitorUrl/monitor/cron/jobs/<job-id>/mark-read" `
  -H "X-Source-Id: RMASSIST"
```

如果只调用 SWE 侧 `/api/cron/jobs/{job_id}/task/mark-read`，SWE 会尝试继续同步 Monitor；如果同步失败，Monitor 未读数仍可能没变。

## 成功但没有通知时

按这个顺序查：

1. SWE 侧 `CronExecutor` 是否返回 `status=success`。
2. `CronManager._record_task_execution_success()` 是否记录成功任务卡片。
3. `MonitorSyncClient.record_execution()` 是否把 execution 写入 Monitor。
4. `monitor/src/monitor/app/services/cron/notification_service.py` 是否能 claim 到 pending execution。
5. `CronNotificationWorker` 是否成功调用 `send_task_success_notification()`。
6. zhaohu 通道是否接受该 `target.user_id` 和 `target.session_id`。

## 状态是 cancelled 但有输出时

这种情况优先看 SWE 侧执行尾部：

- `src/swe/app/crons/executor.py` 的 completed-output 判定。
- `src/swe/app/crons/manager.py` 的 `_handle_cancelled_after_success()`。
- trace 结束日志是否晚于 Monitor execution 的第一次写入。

如果 output 已经生成，但最终状态被覆盖成 `cancelled`，通常要沿着 execution 同步时序查，而不是先看外部调度平台。
