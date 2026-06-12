# Cron 存储、调度与入口

本文说明 cron 任务如何落盘、如何同步外部调度平台、创建更新时写入哪些派生字段，以及 Console、CLI、外部回调分别如何进入同一套生命周期。

返回 [Cron 定时任务模块索引](README.md)。

## 存储与初始化

每个 Workspace 都有自己的 `jobs.json`：

```text
<workspace_dir>/jobs.json
```

创建入口在 `src/swe/app/workspace/workspace.py`：

- `Workspace._register_services()` 注册 `CronManager`。
- `CronManager` 的 repo 是 `JsonJobRepository(str(ws.workspace_dir / "jobs.json"))`。
- `CronManager.initialize()` 会加载系统任务 ID、恢复外部任务 ID、启动 auth token 预热循环，并注册 heartbeat / dream。

外部调度平台的系统任务 ID 单独保存在：

```text
<workspace_dir>/system_jobs.json
```

`JsonJobRepository` 使用单文件 JSON 存储，保存时先写临时文件再替换。它没有跨进程文件锁，所以多实例环境下不应把它当成强一致共享数据库。

## 调度平台适配

本地或测试环境没有 `SWE_CRON_SCHEDULER_BASE_URL` 时，使用 `NoopSchedulerAdapter`。这种模式只保存任务、支持手动运行和展示 next run，不会真正注册外部到点触发。

配置了 `SWE_CRON_SCHEDULER_BASE_URL` 时，`Workspace._build_scheduler_adapter()` 会创建 `RealSchedulerAdapter`。

常用环境变量：

| 环境变量 | 用途 |
| --- | --- |
| `SWE_CRON_SCHEDULER_BASE_URL` | 外部调度平台地址 |
| `SWE_CRON_SCHEDULER_JOB_GROUP` | 外部平台 jobGroup |
| `SWE_CRON_SCHEDULER_AUTHOR` | 外部平台 author |
| `SWE_CRON_SCHEDULER_ALARM_EMAIL` | 外部平台 alarmEmail |
| `SWE_CRON_SCHEDULER_CLIENT_NO` | 外部平台 clientNo |
| `SWE_CRON_SCHEDULER_CLIENT_KEY` | 外部平台 clientKey |
| `SWE_CRON_SCHEDULER_CLIENT_REMARK` | 外部平台 clientRemark |
| `SWE_SERVER_DOMAIN` | 拼接回调地址，默认 `http://localhost:8000` |
| `SWE_INTERNAL_TOKEN` | `/api/internal/*` 可选内部调用 token |

外部平台注册时，`RealSchedulerAdapter` 会调用：

| 操作 | 外部接口 |
| --- | --- |
| 新增任务 | `/job-admin/v2/add-job` |
| 更新任务 | `/job-admin/v2/update-job` |
| 启停任务 | `/job-admin/v2/update-job-run-states` |

写入外部平台的 `jobParam` 是 base64 JSON，包含：

```json
{
  "tenant_id": "<tenant_id>",
  "source_id": "<source_id>",
  "scopeId": "<tenant_id>-<source_id>",
  "agent_id": "<agent_id>",
  "task_type": "job|heartbeat|dream",
  "job_id": "<job_id>",
  "fromId": "<tenant_id>"
}
```

外部平台到点后把 `jobParam` 原样带回 `/api/internal/cron/callback`。SWE 用它恢复租户、来源、Agent 和任务类型。

## 创建与更新流程

创建任务走：

```http
POST /api/cron/jobs
```

更新任务走：

```http
PUT /api/cron/jobs/{job_id}
```

核心步骤：

1. API 层调用 `_inject_request_tenant()`，把 `request.state.tenant_id/source_id/scope_id/bbk_id/user_name` 写入任务。
2. API 层调用 `_inject_creator_user()`，保存 `meta.creator_user_id`。
3. 如果是 `agent` 且带 `model_slot`，API 层调用 `_validate_cron_job_model_slot()` 校验 provider 和 model 是否存在。
4. `CronManager.create_or_replace_job()` 调用 `_ensure_task_binding()`，为任务绑定或复用 task chat。
5. `CronManager._sync_job_to_external_scheduler()` 先注册或更新外部调度平台，并把 `external_job_id` 写入 `meta`。
6. `JsonJobRepository` 写入 `jobs.json`。
7. `CronManager.refresh_next_run_at()` 用 `croniter` 计算后续 3 次运行时间，仅用于界面展示。
8. `MonitorSyncClient.sync_job()` 异步同步任务定义到 Monitor。

任务卡片相关的 `meta` 字段主要有：

| meta 字段 | 含义 |
| --- | --- |
| `creator_user_id` | 谁创建或拥有这个任务卡片 |
| `task_session_id` | 任务 chat 的 session ID，默认 `cron-task:{job_id}` |
| `task_chat_id` | chat 存储里的 chat ID |
| `task_has_scheduled_result` | 是否已有定时执行结果 |
| `task_last_scheduled_preview` | 最近一次结果预览，当前只保存很短片段 |
| `task_unread_execution_count` | 未读成功执行次数 |
| `task_last_scheduled_run_at` | 最近一次定时执行完成时间 |
| `pause_reason` | `manual` 或 `auto_unread_threshold` |
| `auto_paused_at` | 自动暂停时间 |
| `external_job_id` | 外部调度平台任务 ID |

## Console 与 CLI

Console 前端接口集中在 `console/src/api/modules/cronjob.ts`：

| 前端方法 | 后端接口 |
| --- | --- |
| `listCronJobs()` | `GET /api/cron/jobs` |
| `createCronJob()` | `POST /api/cron/jobs` |
| `replaceCronJob()` | `PUT /api/cron/jobs/{job_id}` |
| `deleteCronJob()` | `DELETE /api/cron/jobs/{job_id}` |
| `pauseCronJob()` | `POST /api/cron/jobs/{job_id}/pause` |
| `resumeCronJob()` | `POST /api/cron/jobs/{job_id}/resume` |
| `runCronJob()` | `POST /api/cron/jobs/{job_id}/run` |
| `markTaskRead()` | `POST /api/cron/jobs/{job_id}/task/mark-read` |
| `broadcastCronJob()` | `POST /api/cron/jobs/{job_id}/broadcast` |

`console/src/pages/Control/CronJobs/helpers.ts` 负责把表单上的 daily / weekly / custom cron、执行模型选择项和 `CronJobSpec` 互相转换。

CLI 入口是 `src/swe/cli/cron_cmd.py`。它会通过请求头传：

```http
X-Agent-Id: <agent_id>
X-Tenant-Id: <tenant_id>
X-Source-Id: <source_id>
```

如果没有显式 `--source-id`，CLI 会优先使用当前 source context，而不是随便发一个 `default` source。

CLI 支持通过：

```text
--model-provider <provider_id>
--model <model>
```

生成和 Console 一致的 `model_slot`。

## 外部回调与自动执行

外部调度平台统一回调：

```http
POST /api/internal/cron/callback
```

`src/swe/app/routers/internal.py` 的 `internal_cron_callback()` 会：

1. 校验 `X-Internal-Token`，如果配置了 `SWE_INTERNAL_TOKEN`。
2. 优先读取 `jobParam` 或 `job_param`，按 base64 JSON 解码。
3. 如果没有 `jobParam`，直接读取 body 顶层字段。
4. 提取 `tenant_id`、`source_id`、`agent_id`、`task_type`、`job_id`。
5. 调用 `resolve_runtime_tenant_id(tenant_id, source_id)` 找到 runtime tenant。
6. 通过 `MultiAgentManager` 找到对应 workspace 的 `CronManager`。
7. 按 `task_type` 分发：
   - `heartbeat` -> `CronManager.run_heartbeat()`
   - `dream` -> `CronManager.run_dream()`
   - 其他 -> `CronManager.run_job(job_id, is_manual=False, source_id=source_id)`

这里的 `source_id` 很重要。旧任务可能没有持久化 source，`CronManager._with_execution_source_identity()` 会在执行前用回调里的 source 补齐 legacy job 的执行身份。
