# Cron 排查与提交脉络

本文汇总 cron 常见问题的第一排查入口、相关提交脉络和维护建议。排查时建议先按问题类型定位到对应章节，再回到源码确认当前实现。

返回 [Cron 定时任务模块索引](README.md)。

## 常见排查入口

### 创建后没有到点执行

优先检查：

1. 是否配置了 `SWE_CRON_SCHEDULER_BASE_URL`。未配置时是 Noop，不会外部到点触发。
2. `jobs.json` 里 job 的 `meta.external_job_id` 是否存在。
3. 外部平台的 `jobParam` 是否包含正确 `tenant_id/source_id/agent_id/task_type/job_id`。
4. `SWE_SERVER_DOMAIN` 拼出的回调地址是否外部平台可访问。
5. `/api/internal/cron/callback` 是否通过 `SWE_INTERNAL_TOKEN` 校验。

### 回调到了但找不到任务

优先检查：

1. `jobParam.source_id` 是否缺失或错误。
2. `resolve_runtime_tenant_id(tenant_id, source_id)` 对应的 workspace 是否存在。
3. 该 workspace 的 `jobs.json` 是否包含对应 `job_id`。
4. 旧任务是否缺少 `scope_id/source_id`，需要依赖回调 source 补齐。

### 任务执行报 cron auth 过期

优先检查：

1. 当前 runtime tenant 下是否存在 `cron_auth.json`。
2. `user_info_expires_at` 是否过期。
3. 是否通过 `/api/auth/cron-auth` 重新提交包含 `com.cmb.dw.rtl.sso.token` 的 cookie。
4. 任务执行时 `scope_id` 是否和写入授权时的 workspace 运行 scope 一致。

### 成功执行但没有完成通知

优先检查：

1. Monitor 的 `swe_cron_executions.notification_status` 是否是 `pending`。
2. `notification_due_at` 是否已经到期。
3. SWE 进程的 `CronNotificationWorker` 是否启动。
4. `SWE_CRON_NOTIFICATION_SOURCE_IDS` 是否过滤掉了该 job 的 `source_id`。
5. `monitor/src/monitor/app/services/cron/notification_service.py` 领取 SQL 是否能查到这条 execution。
6. `CronManager.send_task_success_notification()` 是否能找到 job、task chat 和 zhaohu 通道。

### 手动运行后通知时间不对

手动运行走 `is_manual=True`。当前代码要求手动运行不套广播的 `broadcast_offset_minutes` 通知延迟。相关修复是 `9f4362f1 fix(cron): skip manual broadcast notification delay`。

如果再次出现手动运行继承自动广播延迟，优先检查 `CronManager._sync_execution_to_monitor()` 里 `not is_manual` 的判断。

### 工作日 cron 到外部平台后变成每天执行

内部 cron 的 day-of-week 会先归一化为英文缩写，外部平台需要数字格式。优先检查：

- `src/swe/app/crons/models.py` 的 `_crontab_dow_to_name()`。
- `src/swe/app/crons/scheduler_adapter.py` 的 `_normalize_scheduler_dow()`。
- 相关提交：`cc8c5863 fix(cron): preserve weekday schedule for external scheduler`、`80d3a315 fix(cron): convert weekdays for external scheduler`。

### 结果出来了但状态是 cancelled

优先检查：

- `src/swe/app/crons/executor.py` 的 `AgentStreamState`。
- `_has_agent_completed_output()` 是否正确识别 completed message。
- `_end_trace_on_success()` 是否在取消期间成功完成。
- `src/swe/app/crons/manager.py` 的 `_handle_cancelled_after_success()`。

相关提交：`a258e8e4 修复定时任务cancelled异常`、`79445bc6 解决定时任务cancelled问题`。

### Agent 执行链式 swe cron 命令时参数注入到错误位置

Agent 通过 shell 工具执行 `echo ready && swe cron list` 或 `swe cron list && echo done` 时，shell 拦截器需要只给真正的 `swe cron` 命令段注入 `--tenant-id`、`--source-id`，不能把参数追加到整条命令末尾。

优先检查：

- `src/swe/agents/tools/shell_interceptor.py` 的 `_split_by_shell_and()`。
- `_intercept_command_segment()` 是否只处理单个命令段。
- `tests/unit/agents/tools/test_shell_interceptor.py` 里的链式命令回归用例。

相关提交：`f0ed1c9e fix(cron): handle chained swe cron commands`。

## 相关提交脉络

下面只列和当前 wiki 内容直接相关的提交，不是完整历史。

| 提交 | 日期 | 关注点 |
| --- | --- | --- |
| `c9f87bcb` | 2026-04-30 | 增加 text 类型 cron 任务 |
| `7b93cc31` | 2026-05-09 | 增加 `SchedulerAdapter` 与 `NoopSchedulerAdapter` |
| `1f7a2391` | 2026-05-09 | 增加 `RealSchedulerAdapter`，接入外部调度平台 |
| `3f1620e5` | 2026-05-09 | 用 `jobParam` 缩短回调 URL，并把回调上下文编码进参数 |
| `28da199e` | 2026-05-11 | 收敛外部调度集成，处理 cron 格式、生命周期、持久化 |
| `16e0de08` | 2026-05-11 | 启动时自动迁移旧任务到外部调度平台 |
| `ffc2d049` | 2026-05-14 | 将定时任务 trace_id 和结果写入数据库 |
| `2d5711ec` | 2026-05-17 | 增加 source-scoped runtime isolation |
| `bc4af234` | 2026-05-21 | 支持 scope-aware cron 广播与刷新 |
| `573a3582` | 2026-05-25 | 增加任务完成通知队列 |
| `967c1c47` | 2026-05-25 | cron Monitor 查询从 query param 改为 `X-Source-Id` header |
| `cc8c5863` | 2026-05-25 | 保留外部调度平台的 weekday schedule |
| `450b8136` | 2026-05-28 | 增加 cron `model_slot` 合约校验与 ADR |
| `ea17fb89` | 2026-05-28 | 执行时绑定 cron `model_slot` |
| `5c3d2c56` | 2026-05-29 | 定时运行时绑定 Source System Configuration |
| `1a0039ec` | 2026-06-01 | 外部回调触发的 scheduled run 也绑定 source config |
| `f776f648` | 2026-06-02 | CLI 增加 cron 模型参数，复用 `model_slot` |
| `06b202b7` | 2026-06-03 | 通知领取按 source 范围过滤，并补充 playbook |
| `80d3a315` | 2026-06-05 | 外部调度平台 weekday 数字转换修复 |
| `5370c18c` | 2026-06-05 | 未读自动暂停改为 source 可配置 |
| `f24ad72a` | 2026-06-08 | 广播时跳过重复 child job |
| `0732cdea` | 2026-06-09 | 降低广播 API 复杂度 |
| `51febe0a` | 2026-06-10 | 广播时持久化目标租户 `tenant_name`、`bbk_id` 等展示身份 |
| `f0ed1c9e` | 2026-06-10 | shell 拦截器支持链式 `swe cron` 命令，只对命中段注入租户参数 |

## 维护建议

改 cron 相关代码时，建议按下面顺序自查：

1. 先判断改动属于任务定义、外部调度、执行上下文、Monitor 同步、通知、广播、授权还是 Console/CLI。
2. 如果改动影响 `CronJobSpec` 字段，必须同步 Console types、Monitor sync request 和测试 fixture。
3. 如果改动影响 source/tenant/scope，必须同时看 `internal_cron_callback()`、`CronManager._with_execution_source_identity()` 和 `CronExecutor._prepare_execution_context()`。
4. 如果改动影响模型选择，必须保持 `model_slot` 只通过上下文覆盖，不修改租户默认模型。
5. 如果改动影响成功/取消状态，必须同时检查 trace 结束、Monitor execution status 和任务卡片 meta。
6. 如果改动影响通知，必须同时检查 SWE `MonitorSyncClient`、SWE `CronNotificationWorker` 和 Monitor `CronNotificationService`。
7. 如果改动影响广播，必须验证 cron 平移失败 fallback、模型 fallback、重复 child job 和通知 due time。
8. 如果改动影响 Agent shell 中的 `swe cron` 命令，必须验证单条命令和 `&&` 链式命令的参数注入位置。

推荐测试入口：

```bash
venv/bin/python -m pytest tests/unit/app/test_tenant_cron_api.py
venv/bin/python -m pytest tests/unit/app/test_tenant_cron_execution.py
venv/bin/python -m pytest tests/unit/app/test_cron_notification_worker.py
venv/bin/python -m pytest tests/unit/app/test_scheduler_cron_normalization.py
venv/bin/python -m pytest tests/unit/cli/test_cli_cron_tenant.py
venv/bin/python -m pytest tests/unit/monitor/test_cron_notification_service.py
venv/bin/python -m pytest tests/unit/agents/tools/test_shell_interceptor.py
```
