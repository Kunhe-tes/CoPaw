# 定时任务通知领取 source 范围

多实例部署时，如果不同 SWE 实例负责不同 `source_id` 的租户，通知 worker 领取任务必须限制在当前实例允许处理的 source 范围内。

## 配置入口

- `SWE_CRON_NOTIFICATION_SOURCE_IDS`：当前 SWE 实例允许领取通知的 source 列表。
- 支持逗号、空格或换行分隔，例如：`SWE_CRON_NOTIFICATION_SOURCE_IDS=source-a,source-b`。
- 未配置时保持历史行为，不向 Monitor claim 请求传 `source_ids`，Monitor 侧也不会追加 source 过滤条件。
- 已配置 source 列表时，`source_id` 为空字符串或 `NULL` 的通知记录仍会被所有实例竞争领取。

## 代码入口

- SWE 通知 worker：[`src/swe/app/crons/notification_worker.py`](../../src/swe/app/crons/notification_worker.py)
- SWE 调用 Monitor 领取通知：[`src/swe/app/crons/monitor_sync_client.py`](../../src/swe/app/crons/monitor_sync_client.py)
- Monitor 领取接口：[`monitor/src/monitor/app/routers/sync.py`](../../monitor/src/monitor/app/routers/sync.py)
- Monitor 领取 SQL：[`monitor/src/monitor/app/services/cron/notification_service.py`](../../monitor/src/monitor/app/services/cron/notification_service.py)

## 排查顺序

1. 确认 SWE 实例环境变量是否包含预期 `source_id`。
2. 查看 SWE 请求 Monitor 的 `/monitor/sync/notifications/claim` 请求体是否带 `source_ids`。
3. 查看 Monitor 领取 SQL 是否 join `swe_cron_jobs` 并追加 `j.source_id IN (...) OR j.source_id IS NULL OR j.source_id = ''`。
4. 如果某条成功执行记录未被领取，先确认对应 `swe_cron_jobs.source_id` 是否属于当前实例配置范围。
