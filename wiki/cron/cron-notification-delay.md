# Cron 通知延迟

本文说明定时任务完成通知的可配置延迟，包括存储字段、自动执行和手动执行的差异、广播任务叠加规则，以及 Console / CLI 的创建入口。

返回 [Cron 定时任务模块索引](README.md)。

## 一句话理解

定时任务可以在 `CronJobSpec.meta.notification_delay_minutes` 中保存通知延迟分钟数。自动成功执行时，SWE 在写 Monitor execution 前计算具体 `notification_due_at`；Monitor claim 逻辑不需要新增字段。

## 存储字段

字段位置：

```json
{
  "meta": {
    "notification_delay_minutes": 120
  }
}
```

规则：

- 单位固定为分钟。
- 缺失、空值、非数字和负数在执行边界按 `0` 处理。
- 运行时最多应用 7 天，也就是 `10080` 分钟。
- 旧任务没有这个字段时行为不变。

归一化入口在 `src/swe/app/crons/manager.py`：

```text
_notification_delay_minutes(job)
```

## 自动执行和手动执行

通知延迟只对自动成功执行生效：

| 场景 | 行为 |
| --- | --- |
| 自动普通任务成功 | `notification_due_at = end_time + notification_delay_minutes`；如果没有 `end_time`，使用 `actual_time` |
| 手动运行普通任务成功 | 不设置自定义 delayed due time，沿用手动执行的即时/已读语义 |
| 自动广播子任务成功 | 沿用广播原始时间对齐，`notification_due_at = actual_time + broadcast_offset_minutes + notification_delay_minutes` |
| 手动广播子任务成功 | 不叠加广播 offset，也不叠加通知延迟 |

核心边界在：

```text
CronManager._sync_execution_to_monitor()
```

这里已经能同时看到 `is_manual`、execution status、job meta 和 `MonitorSyncClient.record_execution()` 参数，所以延迟必须在这里算成具体 `notification_due_at`，不要下沉到 Monitor claim 服务。

## 广播任务叠加规则

广播子任务本来会携带：

```json
{
  "broadcast_offset_minutes": 20,
  "broadcast_notification_policy": "original_schedule"
}
```

新增通知延迟后，子任务继续继承源任务的 `notification_delay_minutes`。自动执行时总延迟为：

```text
broadcast_offset_minutes + notification_delay_minutes
```

例如：

- 源任务设置 `notification_delay_minutes = 120`
- 目标租户广播错峰 `broadcast_offset_minutes = 20`
- 子任务自动成功执行后，通知 due time 是 `actual_time + 140 minutes`

广播构造入口是 `src/swe/app/crons/api.py` 的 `_build_broadcast_job()`。它会复制源任务 meta 后覆盖广播相关字段，因此 `notification_delay_minutes` 会随源任务继承到子任务。

## CLI 创建

`swe cron create` 支持：

```bash
swe cron create \
  --type agent \
  --name daily-report \
  --cron "0 9 * * *" \
  --channel console \
  --target-user alice \
  --target-session default \
  --text "生成日报" \
  --notification-delay-minutes 120
```

说明：

- 参数默认值是 `0`。
- 参数范围是 `0..10080`。
- inline create 会把默认值也写入 `meta.notification_delay_minutes`。
- `-f/--file` JSON 创建仍尊重文件里的 payload；文件里没有该字段时，运行时仍按 `0` 处理。

实现入口：

```text
src/swe/cli/cron_cmd.py
```

## Console 创建和编辑

Console 提供两种单位：

- `minutes`
- `hours`

前端表单以“数值 + 单位”收集，提交前统一转成分钟保存到 `meta.notification_delay_minutes`。

关键文件：

| 文件 | 职责 |
| --- | --- |
| `console/src/utils/cron.ts` | 延迟归一化、分钟/小时转换、列表展示格式化 |
| `console/src/components/ScheduledTaskPopup/index.tsx` | 快捷创建定时任务时填写通知延迟 |
| `console/src/components/agentscope-chat/CaseDetailDrawer/index.tsx` | 把快捷弹窗的延迟分钟数传给 `buildCronJobSpec()` |
| `console/src/pages/Control/CronJobs/helpers.ts` | Cron Jobs 抽屉编辑时从分钟回显为小时或分钟，并在提交时写回 meta |
| `console/src/pages/Control/CronJobs/components/JobDrawer.tsx` | 新建/编辑表单字段 |
| `console/src/pages/Control/CronJobs/components/columns.tsx` | 列表展示 `NotificationDelay` |

回显规则：

- `0` 显示为 `Immediate`。
- 能被 60 整除且大于 0 的分钟数回显为小时，例如 `120 -> 2 hours`。
- 其他值回显为分钟，例如 `45 -> 45 minutes`。

## 排查入口

如果通知没有按预期延迟，按下面顺序查：

1. job 的 `meta.notification_delay_minutes` 是否存在，单位是否是分钟。
2. 当前执行是否是手动运行；手动运行不会应用通知延迟。
3. execution status 是否是 `success`；失败或取消不会进入成功通知延迟逻辑。
4. 广播子任务是否带 `broadcast_notification_policy = "original_schedule"` 和 `broadcast_offset_minutes`。
5. `MonitorSyncClient.record_execution()` 收到的 `notification_due_at` 是否符合预期。
6. Monitor claim 侧是否已经到 due time；claim 条件仍是 pending + due time 到期 + 锁可领取。

## 覆盖测试

重点测试文件：

- `tests/unit/app/test_cron_manager_completed_cancellation.py`
- `tests/unit/app/test_tenant_cron_api.py`
- `tests/unit/cli/test_cli_cron_tenant.py`
- `console/src/utils/cron.test.ts`
- `console/src/components/ScheduledTaskPopup/index.test.tsx`
- `console/src/pages/Control/CronJobs/helpers.test.ts`
- `console/src/pages/Control/CronJobs/components/columns.test.tsx`
