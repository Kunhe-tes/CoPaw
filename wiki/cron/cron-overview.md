# Cron 总览与代码入口

本文说明 cron 定时任务模块的整体定位、适用场景、主链路、核心代码入口和任务数据模型。读完这一页，应该能判断一个 cron 问题属于 API、调度、执行、隔离、通知还是 Monitor 范围。

返回 [Cron 定时任务模块索引](README.md)。

## 一句话理解

Cron 模块不是“在本进程里用 APScheduler 到点执行”的小功能，而是一套跨 SWE、外部调度平台、Monitor、Console、招呼通知和租户 source 隔离的定时任务运行链路。

可以先记住四句话：

- SWE 保存任务定义、执行业务逻辑，并把任务定义和执行记录同步给 Monitor。
- 外部调度平台只负责到点回调 `/api/internal/cron/callback`，不直接执行 Agent。
- `CronManager` 管任务生命周期、外部平台同步、任务卡片、Monitor 同步和 source 配置绑定。
- `CronExecutor` 管单次执行，负责绑定 tenant/source/model/auth 上下文，再调用 runner 或发送固定文本。

## 适用场景

Cron 模块覆盖下面这些场景：

- 在控制台创建、编辑、暂停、恢复、删除定时任务。
- 通过 CLI `swe cron` 创建、查询、更新、触发任务。
- 到点自动运行 Agent prompt，或发送固定文本。
- 手动点击“运行一次”，立即触发后台执行。
- 将一个定时任务广播到多个租户，并按时间错峰执行。
- 记录执行结果、trace、输入快照、输出预览到 Monitor。
- 对成功的 Agent 定时任务生成待通知记录，再由 SWE 后台 worker 领取并推送招呼通知。
- 支持 heartbeat 和 dream 这类系统定时任务。

## 先看整体链路

普通定时任务从创建到执行，大致是下面这条链路：

```text
Console / CLI / 外部接入方
  -> /api/cron/jobs
  -> Cron API 注入 tenant/source/creator/model 信息
  -> CronManager.create_or_replace_job()
  -> 绑定任务 chat、同步外部调度平台、写 jobs.json、同步 Monitor
  -> 外部调度平台按 cron 到点回调
  -> /api/internal/cron/callback
  -> 解析 jobParam，恢复 tenant/source/agent/job
  -> CronManager.run_job(is_manual=False)
  -> CronExecutor.execute()
  -> runner.stream_query() 或 channel_manager.send_text()
  -> CronManager 记录状态、更新任务卡片、同步 Monitor execution
  -> CronNotificationWorker 从 Monitor 领取 pending 通知
  -> CronManager.send_task_success_notification()
  -> zhaohu 通道推送完成提醒
```

手动运行少了外部调度平台这一段：

```text
POST /api/cron/jobs/{job_id}/run
  -> CronManager.run_job(is_manual=True)
  -> CronExecutor.execute()
  -> Monitor execution 标记为手动执行；成功时默认已读
```

## 核心代码入口

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
| 授权 API | `src/swe/app/routers/auth.py` | `/api/auth/cron-auth` 写入 cron 授权，`/api/auth/cron-auth/cleanup` 清理状态 |
| Monitor 同步客户端 | `src/swe/app/crons/monitor_sync_client.py` | SWE 调用 Monitor 同步 job、execution、通知领取状态 |
| 完成通知 worker | `src/swe/app/crons/notification_worker.py` | 后台扫描 Monitor pending 通知并推送完成提醒 |
| Monitor 同步服务 | `monitor/src/monitor/app/services/cron/sync_service.py` | 写入 `swe_cron_jobs`、`swe_cron_executions` |
| Monitor 通知服务 | `monitor/src/monitor/app/services/cron/notification_service.py` | 原子领取待通知 execution，回写 sent / failed |
| Console API | `console/src/api/modules/cronjob.ts` | 前端调用 `/cron/jobs`、广播、运行、已读等接口 |
| Console 表单 | `console/src/pages/Control/CronJobs/helpers.ts` | 表单值和 `CronJobSpec` 互转，处理 cron 表达式和 `model_slot` |
| CLI | `src/swe/cli/cron_cmd.py` | `swe cron list/get/state/create/update/delete/pause/resume/run` |

## 任务数据模型

定时任务的核心对象是 `CronJobSpec`。

| 字段 | 含义 | 关键规则 |
| --- | --- | --- |
| `id` | SWE 内部任务 ID | 创建时服务端重新生成，更新时必须和 URL 的 `job_id` 一致 |
| `name` | 任务名称 | 同步给外部调度平台和 Monitor |
| `enabled` | 是否启用 | 影响外部平台 resume / pause，也影响自动执行是否跳过 |
| `tenant_id` | 逻辑租户或用户 | API 会从请求上下文注入，不信任客户端原值 |
| `source_id` | 来源标识 | 来自 `X-Source-Id`，参与 runtime scope 和通知 source 过滤 |
| `scope_id` | 运行时 scope | 通常是 tenant + source 的 canonical 结果 |
| `bbk_id` | 分行号 | 来自请求头，后续同步到 Monitor |
| `tenant_name` | 用户名或租户名 | 来自请求头，后续同步到 Monitor |
| `schedule` | cron 表达式和时区 | 只支持 5 字段 cron；3/4 字段会补齐；不支持秒字段 |
| `task_type` | `agent` 或 `text` | `agent` 必须有 `request`，`text` 必须有 `text` |
| `request` | Agent 请求体 | `extra="allow"`，最终传给 `runner.stream_query()` |
| `model_slot` | 指定执行模型 | 只对 `agent` 生效；`text` 任务会清空 |
| `dispatch` | 输出目标 | 包含 channel、user_id、session_id、mode、meta |
| `runtime` | 执行限制 | 默认超时 7200 秒，最大并发 1，misfire grace 300 秒 |
| `meta` | 扩展状态 | 保存 task chat、未读数、external_job_id、广播来源等运行态字段 |

### cron 表达式规则

`ScheduleSpec` 接受的是 5 字段 cron：

```text
minute hour day_of_month month day_of_week
```

注意点：

- 6 字段 cron 会被拒绝，因为秒字段不受支持。
- 4 字段会被当成 `hour day_of_month month day_of_week`，自动补 minute 为 `0`。
- 3 字段会被当成 `day_of_month month day_of_week`，自动补 `0 0`。
- day-of-week 的数字会转成英文缩写，避免 APScheduler / crontab 对周日编号理解不一致。
- `src/swe/app/crons/scheduler_adapter.py` 再把内部 5 字段 cron 转为外部调度平台的 6 字段格式。
