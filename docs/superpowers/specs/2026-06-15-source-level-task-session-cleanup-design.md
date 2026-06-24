# Source 级定时任务会话历史清理设计

## 背景

当前定时任务会话历史清理配置已经存放在
`swe_source_system_config.config_text` 的
`cron_task_session_cleanup` 节点下，配置天然属于 `source_id`。
但是外部调度平台注册动作仍由每个 tenant workspace 内的
`CronManager` 在初始化时触发。多个 tenant 属于同一个 source 时，
并发初始化会同时发现 source 级 external id 不存在，从而向调度平台
创建多条清理任务。

目标是把清理系统任务收敛为真正的 source 级任务：同一个 `source_id`
只能有一条清理任务，清理范围覆盖该 source 下所有 tenant/scope 的
定时任务会话历史。

## 目标

- 清理任务按 `source_id + task_type` 唯一，不再按 tenant 或 scope 创建。
- 清理配置继续使用 `swe_source_system_config` 表中的
  `cron_task_session_cleanup`。
- 配置保存后注册或更新当前 source 的唯一外部调度任务。
- 外部调度平台参数仍包含 `tenant_id`、`scopeId`、`fromId`，取最后一次
  修改该 source 配置的请求身份。
- 调度平台上的清理任务展示名不包含 `agentId` 或 `tenant_id`，只体现
  source 级清理任务本身。
- 回调执行时按 `source_id` 读取配置并清理该 source 下所有
  tenant/scope 的定时任务会话历史。

## 非目标

- 不保留 tenant 级清理任务注册兼容路径。
- 不再让 `CronManager.initialize()` 注册清理系统任务。
- 不把清理任务拆成每个 tenant 一条。
- 不改普通业务定时任务、heartbeat、dream 的现有注册语义。

## 数据模型

新增 source 级系统任务绑定存储，建议使用数据库表：

```text
swe_source_system_task_binding
- source_id
- task_type
- external_job_id
- cron
- enabled
- scheduler_tenant_id
- scheduler_from_id
- updated_by
- updated_at
```

唯一键为：

```text
(source_id, task_type)
```

`scheduler_tenant_id`、`scheduler_from_id` 只记录最近
一次修改配置时用于注册调度平台的身份字段，不参与任务唯一性。
`scopeId` 不持久化；注册外部调度任务时按普通任务规则由
`tenant_id-source_id` 生成。
如果环境已经创建过旧表结构，执行
`scripts/sql/migrate_source_system_task_binding_drop_scope.sql`
删除不再使用的 `scheduler_scope_id` 列。

## 注册流程

新增 source 级注册器，例如 `SourceSystemTaskScheduler`：

1. 接收 `source_id`、当前请求身份和 effective source 配置。
2. 读取 `cron_task_session_cleanup`。
3. 用 `(source_id, "task_session_cleanup")` 获取或创建绑定记录。
4. `enabled=true` 且无 `external_job_id` 时创建外部任务。
5. `enabled=true` 且已有 `external_job_id` 时更新同一外部任务。
6. `enabled=false` 且已有 `external_job_id` 时暂停同一外部任务。
7. 写回 binding 表中的 cron、enabled、external_job_id 和最近修改身份。

创建/更新必须在 source 级互斥下完成。数据库层应通过唯一键、事务或
条件更新避免多实例并发创建两条外部任务。

## 调度平台 payload

清理系统任务的外部调度 payload 仍传调度平台需要的身份字段：

```json
{
  "tenant_id": "last-updater-tenant",
  "source_id": "source-a",
  "scopeId": "last-updater-tenant-source-a",
  "fromId": "last-updater-tenant",
  "agent_id": "",
  "task_type": "task_session_cleanup"
}
```

这些字段只用于调度平台回调、审计和兼容调度平台参数要求。任务唯一性
只由 `source_id + task_type` 决定。

清理任务的调度平台展示名不拼接 `agentId` 和 `tenant_id`。建议名称：

```text
[SWE] source-a/task_session_cleanup
```

如果平台区分任务描述和任务名称，两者都应避免包含 `agentId` 和
`tenant_id`。

## 回调与执行

新增或复用内部 callback 分支处理 source 级系统任务：

1. 从 jobParam 中读取 `source_id` 和 `task_type`。
2. 当 `task_type` 为 `task_session_cleanup` 时进入 source 级清理服务。
3. 清理服务通过 `SourceSystemConfigService.resolve_config(source_id)`
   读取 retention days 和 enabled 状态。
4. 如果配置已关闭，记录日志并跳过执行。
5. 枚举该 source 下所有 runtime scope / tenant workspace。
6. 对每个 scope 执行现有会话历史清理逻辑。

回调中的 `tenant_id`、`scopeId`、`fromId` 不用于决定清理范围。

## 旧路径移除

- 删除或停用 `CronManager.register_task_session_cleanup()` 的外部任务创建逻辑。
- `CronManager._register_system_jobs()` 不再调用清理任务注册。
- 删除 tenant workspace 下用于清理任务的 source external id 文件复用逻辑。
- 已存在的 tenant 级外部清理任务不在本设计中自动迁移；上线前由运维或
  单独脚本清理旧任务，避免误删仍需人工确认的调度平台记录。

## 错误处理

- 数据库不可用时，配置保存接口应返回明确错误，不应假装注册成功。
- 外部调度平台注册失败时，配置保存可以成功，但 response/log 需要暴露
  注册失败信息，便于管理员重试。
- 回调执行时如果某个 tenant/scope 清理失败，不应中断其他 scope；最终
  记录成功、失败和跳过数量。

## 测试计划

- source 配置保存后只创建一条清理外部任务。
- 同一 source 由不同 tenant 先后修改配置时，只 update 同一条任务，
  payload 身份更新为最后修改者。
- 同一 source 多 tenant 并发触发注册时，只出现一条 add-job。
- 调度平台清理任务名称不包含 `agentId` 和 `tenant_id`。
- `enabled=false` 时暂停 source 级清理任务。
- 回调只根据 `source_id` 清理该 source 下所有 tenant/scope 的会话历史。
- `CronManager.initialize()` 不再注册清理系统任务。
