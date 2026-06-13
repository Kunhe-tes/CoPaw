# Cron 定时任务模块索引

本文档面向 Swe / CoPaw 的普通使用者、接入方和维护者，说明 cron 定时任务模块在当前 `v1.0.0` 代码里的真实边界、运行链路、关键接口、数据字段、通知机制和排查入口。

本文按 `v1.0.0` worktree 当前基线核对：`f0ed1c9e fix(cron): handle chained swe cron commands`。相关说明已参考 `src/swe/app/crons/`、Console、Monitor、ADR、playbook 和 cron 相关提交。

## 新人推荐阅读顺序

如果是第一次接触 cron，建议按下面顺序读：

1. 先看 [Cron 总览与代码入口](cron-overview.md)，理解 cron 不是本地 APScheduler，而是 SWE + 外部调度平台 + Monitor + 通知 worker 的链路。
2. 再看 [Cron 存储、调度与入口](cron-scheduler.md)，确认任务从 Console / CLI 创建后如何落盘、同步平台、再被回调触发。
3. 然后看 [Cron 执行上下文](cron-execution-context.md)，理解 scheduled run 如何恢复 tenant、source、model、cookie 和 runner 上下文。
4. 如果问题和任务列表、未读、完成提醒或 Monitor 数据有关，看 [Cron Monitor 与通知](cron-monitor-notification.md)。
5. 如果问题涉及可配置完成通知延迟、广播通知延迟叠加、CLI / Console 延迟配置，看 [Cron 通知延迟](cron-notification-delay.md)。
6. 如果问题涉及多租户广播、heartbeat、dream 或多实例部署，看 [Cron 广播与系统任务](cron-broadcast-system.md)。
7. 如果问题涉及查看分发给哪些用户、批量删除或重跑分发子任务，看 [Cron 分发子任务管理](cron-distribution-management.md)。
8. 最后用 [Cron 排查与提交脉络](cron-troubleshooting-history.md) 定位常见问题和相关提交。

## 文档目录

| 文档 | 适合回答的问题 |
| --- | --- |
| [Cron 总览与代码入口](cron-overview.md) | cron 是什么、覆盖哪些场景、主链路是什么、核心代码在哪、任务模型字段含义 |
| [Cron 存储、调度与入口](cron-scheduler.md) | jobs.json 如何保存、外部平台如何同步、Console / CLI / 回调分别怎么进入 |
| [Cron 执行上下文](cron-execution-context.md) | 单次执行流程、成功/取消判定、source 隔离、model_slot、cron_auth.json 和 cookie 来源 |
| [Cron Monitor 与通知](cron-monitor-notification.md) | 任务卡片、未读计数、自动暂停、Monitor 同步、完成通知领取和推送 |
| [Cron 通知延迟](cron-notification-delay.md) | `meta.notification_delay_minutes`、自动/手动执行差异、广播 offset 叠加、CLI 和 Console 配置 |
| [Cron 广播与系统任务](cron-broadcast-system.md) | 广播任务如何派生子任务、heartbeat / dream 怎么跑、多实例 coordination 当前边界 |
| [Cron 分发子任务管理](cron-distribution-management.md) | 反查分发子任务、批量删除、批量重跑、重新分发覆盖配置的字段边界 |
| [Cron 排查与提交脉络](cron-troubleshooting-history.md) | pending approval、source 串租户、Monitor 取消态、通知缺失、星期转换等问题怎么查 |

## 示例目录

如果需要直接照着跑，先看 [Cron 示例索引](examples/README.md)。示例按当前代码里的真实接口和字段写：

| 示例 | 用途 |
| --- | --- |
| [API 创建 Agent 任务](examples/api-agent-daily/README.md) | 用 `POST /api/cron/jobs` 创建每日 Agent 定时任务，并手动触发一次 |
| [CLI 创建固定文本任务](examples/cli-text-weekly/README.md) | 用 `swe cron create/list/update/run/pause/resume/delete` 管理一个固定文本任务 |
| [外部调度回调](examples/callback-jobparam/README.md) | 说明 `jobParam` 解码格式和直接回调格式 |
| [广播到多个租户](examples/broadcast-to-tenants/README.md) | 把一个源任务复制到多个租户，并理解错峰和 warning |
| [Cron 授权状态](examples/cron-auth/README.md) | 写入 `cron_auth.json`、刷新 cookie/auth token、清理非目标 source 授权 |
| [Monitor 与通知排查](examples/monitor-notification-debug/README.md) | 查询 job/execution、标记已读、定位通知未发送 |

## 先看结论

- SWE 保存任务定义、执行业务逻辑，并把任务定义和执行记录同步给 Monitor。
- 外部调度平台只负责到点回调 `/api/internal/cron/callback`，不直接执行 Agent。
- `CronManager` 管任务生命周期、外部平台同步、任务卡片、Monitor 同步和 source 配置绑定。
- `CronExecutor` 管单次执行，负责绑定 tenant/source/model/auth 上下文，再调用 runner 或发送固定文本。
- 当前 `v1.0.0` 基线里已有 `src/swe/app/crons/coordination.py`，但它没有接入 `Workspace` / `CronManager` 的实际装配链路；不要把它误当成当前生产执行入口。

## 关键源码入口

| 入口 | 文件 | 主要职责 |
| --- | --- | --- |
| Workspace 装配 | `src/swe/app/workspace/workspace.py` | 每个 Workspace 注册一个 `CronManager`，repo 使用 `workspace_dir / "jobs.json"` |
| 数据模型 | `src/swe/app/crons/models.py` | `CronJobSpec`、`ScheduleSpec`、`CronJobState`、`CronTaskView` |
| SWE Cron API | `src/swe/app/crons/api.py` | `/api/cron/*` 任务 CRUD、手动运行、广播、任务已读 |
| 生命周期中心 | `src/swe/app/crons/manager.py` | 创建/更新/删除/暂停/恢复/执行、任务卡片、Monitor 同步、source 配置绑定 |
| 单次执行 | `src/swe/app/crons/executor.py` | 绑定 tenant/source/model/auth，上下文内执行 text 或 agent 任务 |
| 外部调度适配 | `src/swe/app/crons/scheduler_adapter.py` | `NoopSchedulerAdapter` 与 `RealSchedulerAdapter`，对接外部 job-admin API |
| 外部回调 | `src/swe/app/routers/internal.py` | `/api/internal/cron/callback` 解码 `jobParam` 并分发 job / heartbeat / dream |
| 授权状态 | `src/swe/app/crons/auth_state.py` | 保存 `cron_auth.json`，刷新 user_info/auth_token/cookie |
| Monitor 同步客户端 | `src/swe/app/crons/monitor_sync_client.py` | SWE 调用 Monitor 同步 job、execution、通知领取状态 |
| 完成通知 worker | `src/swe/app/crons/notification_worker.py` | 后台扫描 Monitor pending 通知并推送完成提醒 |
| Monitor 同步服务 | `monitor/src/monitor/app/services/cron/sync_service.py` | 写入 `swe_cron_jobs`、`swe_cron_executions` |
| Monitor 通知服务 | `monitor/src/monitor/app/services/cron/notification_service.py` | 原子领取待通知 execution，回写 sent / failed |
| Console API | `console/src/api/modules/cronjob.ts` | 前端调用 `/cron/jobs`、广播、运行、已读等接口 |
| CLI | `src/swe/cli/cron_cmd.py` | `swe cron list/get/state/create/update/delete/pause/resume/run` |

## 版本边界

- 当前 wiki 以 `v1.0.0` 的 `f0ed1c9e` 为事实来源。
- 当前基线已包含 `51febe0a fix(cron): persist broadcast target identity`，广播目标的 `tenant_name`、`bbk_id` 会随 `targets` 请求体写入子任务。
- 当前基线已包含 `f0ed1c9e fix(cron): handle chained swe cron commands`，Agent shell 拦截器可以处理 `echo ready && swe cron list` 这类链式命令。
- 当前本地修改补充了 `meta.notification_delay_minutes`，自动成功执行的完成通知可以按任务配置延迟，广播子任务会在原有错峰通知 offset 上继续叠加这个延迟。
- 当前本地修改补充了分发子任务管理：任意任务都能反查子任务，已分发子任务支持批量删除和批量重跑，重新分发会覆盖任务定义配置但保留目标用户身份和暂停状态。
- 这里记录的是当前代码真实行为，不把尚未装配的 coordination 原语描述成已经生效的运行路径。
