# Cron 执行上下文

本文说明单次 cron 执行如何恢复 tenant/source/model/auth 上下文，如何运行 text / agent 任务，以及如何判定取消、成功和授权状态。

返回 [Cron 定时任务模块索引](README.md)。

## 单次执行流程

`CronManager.run_job()` 是 fire-and-forget：

- 先从 repo 读取 job。
- job 不存在抛 `KeyError`。
- job disabled 时直接跳过。
- 标记内存态 `last_status = "running"`。
- 在 `LLM_WORKLOAD_CRON` workload 下创建后台 task。
- 后台 task 的异常由 `_task_done_cb()` 记录，并推送到 console push store。

真正执行发生在 `CronManager._execute_once()`：

1. 按 job 的 `runtime.max_concurrency` 创建或复用 `asyncio.Semaphore`。
2. 记录 `actual_time`，默认 `exec_status = "success"`。
3. 按 Scheduled Run Boundary 解析最新 Source System Configuration。
4. 通过 `_bind_scheduled_run_source_system_config()` 绑定 source 配置；没有 source 时显式清掉继承上下文。
5. 调用 `CronExecutor.execute(job)`。
6. 成功后更新任务卡片、未读计数和自动暂停状态。
7. 无论成功、失败还是取消，finally 中都会调用 `_finalize_execution_state()`；普通 execution 同步 Monitor，带完整 dispatch 身份的 execution 同步独立 Scheduler。

`CronExecutor.execute()` 会：

1. 从 job 构造 `_ExecutionContext`，包含 target user/session、workspace_dir、tenant/source/scope。
2. 解析执行模型，必要时通过 `bind_model_slot_override()` 临时覆盖模型选择。
3. 通过 `bind_tenant_context()` 绑定 tenant/user/workspace/source/scope。
4. 通过 `bind_llm_workload(LLM_WORKLOAD_CRON)` 标记这是 cron workload。
5. 按 `task_type` 分发：
   - `text` -> `_execute_text_job()`
   - `agent` -> `_execute_agent_job()`

Agent 任务会额外做这些事：

- 构造 runner request，并设置 `skip_history = True`。
- 透传 `source_id`、`scope_id`、`bbk_id`、`user_name`。
- 调用 `_apply_auth_token()` 从 `cron_auth.json` 解析 auth token 和 cookie。
- 创建 trace，并把 `trace_id` 放入 request。
- 用 `asyncio.timeout()` 或 `asyncio.wait_for()` 套住整段 `runner.stream_query()`。
- 每个流式 event 都发送到目标 channel。
- 收集文本输出，生成最多 100 字符的 `output_preview` 给 Monitor。
- 成功、错误、超时、取消都会尽量结束 trace。

## 批调度执行身份

Scheduler 回调 SWE 时会携带完整 dispatch 身份：

| 字段 | 含义 |
| --- | --- |
| `callback_source=dispatch_service` | 表明本次自动执行来自独立 Scheduler |
| `dispatch_intent_id` | 本次待派发记录 ID |
| `dispatch_batch_id` | 父任务计划触发对应的批次 ID |
| `dispatch_attempt` | 当前尝试次数 |
| `provider_id` / `model_id` | Scheduler 使用的模型作用域 |
| `parent_scheduled_fire_at` | 父任务原计划触发时间，用于通知时间对齐 |

`internal_cron_callback()` 把这些字段整理为 `dispatch_meta` 传给 `CronManager.run_job()`，execution meta 中以 `cron_dispatch` 保存。只有 intent ID、batch ID 和 attempt 都有效时，`MonitorSyncClient.record_execution()` 才把结果同步到 `/api/scheduler/cron/execution`；否则仍走原来的 Monitor `/monitor/sync/execution`。

这一判断刻意不使用 B3 trace header。普通外部回调即使带 B3 也不是 Scheduler dispatch；批调度回调会转发 B3 headers，仅用于链路追踪。

Scheduler 回执路径会同步重试最多 3 次。成功或最终失败回执用于释放模型作用域容量并立即补位，因此不能把它当成普通的异步 Monitor 写入。

## 取消与成功状态

Cron 执行里有一类特殊问题：Agent 已经产出并发送了 completed message，但外层任务在结束 trace 或 finally 阶段收到 `CancelledError`。

当前代码在 `CronExecutor` 和 `CronManager` 两层都做了保护：

- `AgentStreamState` 记录是否看到 completed message、是否已发送、stream 是否返回。
- 如果取消发生在完成输出之后，会尽量按 success 处理，而不是把成功任务误记为 cancelled。
- `_end_trace_on_success()` 使用 shield / 等待逻辑保护 trace 结束。
- `CronManager._handle_cancelled_after_success()` 在 `last_status == "success"` 时保留 success 状态。

排查“结果已经出来但 Monitor 里是 cancelled”时，优先看 `src/swe/app/crons/executor.py` 里的 completed-output 判定和 trace 结束日志。

## Source 与租户隔离

Cron 任务有三层身份：

| 身份 | 来源 | 用途 |
| --- | --- | --- |
| `tenant_id` | 请求头或 jobParam | 逻辑租户或用户身份 |
| `source_id` | `X-Source-Id` 或 jobParam | 来源系统，参与配置和通知隔离 |
| `scope_id` | tenant + source 解析结果 | runtime 目录、Provider、auth、memory 等隔离键 |

关键设计在 `docs/adr/0002-scheduled-runs-resolve-source-system-config-at-execution-time.md`：

- 定时任务执行时没有 HTTP 请求 middleware，因此不能依赖请求态 source 配置。
- 每次定时执行都在 Scheduled Run Boundary 重新解析最新 Source System Configuration。
- `CronManager` 负责绑定这个配置，`CronExecutor` 和 runner 只消费已绑定上下文。
- 有显式 source 时优先用 source，没有 source 时尝试从 scope 解码；都没有时按 legacy source-less 任务处理，不发明默认 source。

这能保证系统功能页上的 source 配置变更，会在已有定时任务下一次运行时生效。

## 执行模型 model_slot

`model_slot` 用于给某个 cron agent 任务指定执行模型，而不是修改租户默认模型。

关键规则：

- API 创建/更新时校验 provider 和 model 是否存在。
- `text` 任务不保留 `model_slot`。
- 执行时优先使用 job 的 `model_slot`。
- 如果 provider 或 model 不存在，回退到当前租户默认模型，并把 fallback 原因记录进 execution meta。
- 广播任务如果目标租户没有源任务使用的模型，也会回退到目标租户默认模型，并在 meta 中保存原始模型和 fallback 原因。
- 批调度会把最终 provider/model 纳入 `source_id + provider_id + model_id` 派发作用域；这里的 worker capacity 是并行槽位，不会改变租户默认模型。

设计依据在 `docs/adr/0001-cron-model-overrides-use-request-context.md`：

- 模型覆盖通过请求作用域上下文传递。
- 不修改 `ProviderManager.active_model`。
- 并发 cron 和普通 chat 请求之间不会互相污染模型选择。

## 任务关联技能 skill_ids

`CronJobSpec.skill_ids` 用于把 cron job 和技能就绪度治理关联起来。服务端会按逗号或空白拆分、去重，只允许字母数字及 `_ . : -`，归一化后的总长度最多 200 字符。

这个字段供技能绑定和治理查询使用，不是执行器的技能加载指令：`CronExecutor` 不会因为 job 带 `skill_ids` 就自动注入或加载对应技能。排查“任务关联了技能但执行时没有自动使用”时，先确认调用方是否误解了字段责任边界。

## Cron 授权状态

Cron agent 任务运行时可能需要用户身份。授权状态由下面接口写入：

```http
POST /api/auth/cron-auth
```

请求体：

```json
{
  "cookie": "com.cmb.dw.rtl.sso.token=<access_token>; ..."
}
```

处理流程：

1. `configure_cron_auth()` 从 cookie 中提取 `com.cmb.dw.rtl.sso.token`。
2. 通过 `get_agent_for_request()` 找到当前 workspace。
3. `ensure_user_info_from_access_token()` 调 `get_user_info()` 获取或刷新 user_info。
4. 写入当前 runtime tenant 的 `cron_auth.json`。

`CronAuthState` 主要字段：

| 字段 | 含义 |
| --- | --- |
| `user_info` | 用 access token 换到的用户信息 |
| `user_info_expires_at` | user_info 过期时间，默认 TTL 7 天 |
| `user_info_refreshed_at` | 最近刷新时间 |
| `auth_token` | 用 user_info 换到的短期 token |
| `auth_token_expires_at` | auth token 过期时间，默认 TTL 2 小时 |
| `cookie_header` | 原 cookie，运行时会把新的 auth token 合并进去 |
| `last_prefetch_at` | 最近预热 token 时间 |
| `last_error` | 最近授权错误 |

执行时，`CronExecutor._apply_auth_token()` 调 `resolve_auth_token_for_execution()`：

- 如果 `user_info` 过期，抛出 `cron auth user_info is expired; please refresh cron auth configuration`。
- 如果已有 auth token 剩余时间足够，复用。
- 否则重新用 user_info 签发 auth token。
- 最后把 `auth_token` 和 `cookie` 放进 runner request。

手动清理授权状态走：

```http
POST /api/auth/cron-auth/cleanup
```

它会按 source 保留或删除租户目录下的 `cron_auth.json`，适合清理错误 source 下的旧状态。
