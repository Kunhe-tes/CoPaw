# Scheduler 整批触发接口

## 请求

```http
POST /api/scheduler/external/cron/batch/run
Content-Type: application/json
```

调用方使用现有认证凭据请求网关。网关将请求转发给 Scheduler，并在认证后注入 `X-User-Id` 和 `X-Source-Id`。按实际任务归属注入 `X-Tenant-Id` 和 `X-Agent-Id`，默认分别为当前用户和 `default`。网关须覆盖或移除调用方自填的身份和角色头。父任务创建者或经网关授权的 `manager`、`admin` 可以操作对应租户、来源和 Agent 下的父任务。

```json
{"jobId": "<新版批调度父任务 ID>"}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `jobId` | string | 必填，Scheduler 中的父任务 ID，1–128 字符。请求体只接受这个字段。 |

## 受理结果

HTTP `202 Accepted` 表示 Scheduler 已将符合批模式、任务启停和北京时间可执行日期条件的父任务及关联子任务写入同一个批次。手动触发以收到请求的时刻为触发时间，免除自动排程的工作日判断。后续派发遵循现有批调度优先级和并发规则。

```json
{
  "batch_id": "<新批次 ID>",
  "parent_job_id": "<父任务 ID>",
  "accepted": true,
  "reused": false,
  "enqueued_intents": 3,
  "status": "queued",
  "trigger_time_basis": "manual"
}
```

`enqueued_intents` 是本轮实际入队的任务数。调用方可以通过「批调度看板（新）」用 `batch_id` 跟踪执行进度和结果。

## 已有批次

同一父任务只要存在一个未结束的新版批次，接口就返回 HTTP `409 Conflict` 和现有批次 ID。排队、执行中、等待派发重试、主执行成功但异步结果还未收敛，都计入未结束。平台回调创建的批次也计入。

```json
{
  "detail": {
    "code": "cron_batch_already_active",
    "batch_id": "<现有批次 ID>"
  }
}
```

调用方可跟踪返回的批次，待该父任务的所有批次结束后再发起新一轮。请求超时后先核对批次记录。服务端按当前批次状态判断是否受理，上一批已结束时，重发会创建新批次。

## 其他错误

| HTTP 状态 | `detail` 示例 | 含义 |
| --- | --- | --- |
| `400` | `invalid_cron_identity` | 网关注入的身份缺失或无效 |
| `404` | `cron_job_not_found` | 任务不存在、已删除或超出权限范围 |
| `409` | `cron_batch_run_requires_parent` | 传入了分发子任务 ID |
| `409` | `job_not_in_batch_mode` / `batch_paused` | 批模式关闭或批入口暂停 |
| `409` | `job_outside_date_range` / `job_not_eligible` / `job_not_ready` | 日期超出范围、没有可执行成员或任务尚未就绪 |
| `422` | 请求校验错误列表 | 缺少 `jobId`、字段非法或存在额外字段 |
| `503` | `cron_managed_runtime_not_ready` / `cron_batch_run_unavailable` | Scheduler 后台或存储暂不可用 |

## 部署

更新 Scheduler，并在认证网关将该路径转发至 Scheduler。该接口复用现有新版批次表和成员表。Scheduler 服务端口由内网访问策略保护。
