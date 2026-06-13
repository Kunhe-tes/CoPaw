# Cron 分发子任务管理

本文说明定时任务菜单里的分发子任务反查、批量删除、批量重跑，以及重新分发覆盖配置的边界。

返回 [Cron 定时任务模块索引](README.md)。

## 一句话理解

任意定时任务都可以打开“查看分发用户”。后端按 `meta.broadcast_source_job_id` 反查当前 source job 派生出的子任务；没有分发过时返回空列表，不报错。

## API

| 接口 | 用途 |
| --- | --- |
| `GET /api/cron/jobs/{job_id}/broadcast/children` | 列出当前 source job 的分发子任务 |
| `POST /api/cron/jobs/{job_id}/broadcast/children/delete` | 批量删除选中的子任务 |
| `POST /api/cron/jobs/{job_id}/broadcast/children/run` | 批量重跑选中的子任务 |

批量请求体使用子任务所属租户和子任务 ID：

```json
{
  "items": [
    {
      "tenant_id": "tenant-a",
      "job_id": "child-job-id"
    }
  ]
}
```

后端会逐条校验子任务的 `meta.broadcast_source_job_id` 是否等于当前 source job ID。校验失败的条目不会删除或运行，并在结果里返回失败原因。

## Console 行为

入口位于定时任务列表每行的管理菜单：

- 没有分发过的任务也能打开反查弹窗，显示“当前任务尚未分发给任何用户”。
- 已分发的子任务展示目标用户、机构、子任务 ID、cron、时区、启停状态、错峰分钟和通知延迟。
- 批量删除只删除选中的子任务，不删除源任务。
- 批量重跑逐条返回结果；如果子任务已暂停或禁用，结果展示为“已暂停，未执行”。

前端入口：

| 文件 | 职责 |
| --- | --- |
| `console/src/pages/Control/CronJobs/components/columns.tsx` | 每行管理菜单新增“查看分发用户” |
| `console/src/pages/Control/CronJobs/components/BroadcastChildrenModal.tsx` | 子任务反查、选择、批量删除和批量重跑 |
| `console/src/api/modules/cronjob.ts` | 子任务列表和批量操作 API |

## 重新分发覆盖规则

重新分发到已经有子任务的租户时，不再跳过该租户。后端会刷新已有子任务，但只覆盖和用户身份无关的任务定义字段：

- 执行内容和请求 payload
- `task_type`
- 文本任务内容
- cron 表达式、时区和 schedule
- runtime / model slot
- 通知延迟 `meta.notification_delay_minutes`
- 广播元数据，例如 `broadcast_original_cron`、`broadcast_offset_minutes`

这些目标用户侧字段会保留：

- 子任务 `job_id`
- `tenant_id`、`tenant_name`、`bbk_id`
- request / dispatch target 里的用户身份
- 任务绑定的 chat/session 相关 meta
- 当前启停状态和暂停原因

因此管理员可以用重新分发修正任务内容和时间配置，同时不会把目标用户身份、当前暂停状态或任务卡片关联覆盖掉。

## 后端入口

核心实现位于 `src/swe/app/crons/api.py`：

| 函数 | 职责 |
| --- | --- |
| `_build_broadcast_job()` | 从源任务构造目标子任务定义 |
| `_refresh_existing_broadcast_child_job()` | 重新分发时刷新已有子任务 |
| `list_broadcast_children()` | 反查 source job 的当前子任务 |
| `delete_broadcast_children()` | 批量删除子任务 |
| `run_broadcast_children()` | 批量重跑子任务并跳过暂停项 |

覆盖测试位于 `tests/unit/app/test_tenant_cron_api.py`，重点覆盖空列表、子任务列表、批量删除、暂停跳过和重新分发刷新。
