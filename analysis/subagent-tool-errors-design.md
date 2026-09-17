# SubAgent 工具报错分析与处理方案

## 背景

本次问题集中在 Background SubAgent 工具链：

- `start_subagent` 在临时构造 `SubAgentDefinition` 时抛出 description 长度校验错误。
- `wait_subagent` 返回的后台 run 失败，失败原因是 worker 进程内没有拿到租户模型配置。
- `start_subagent` / `wait_subagent` 返回给主 Agent 的工具结果包含过多内部字段。

关键代码路径：

- 工具定义：`src/swe/agents/tools/subagent_background.py`
- Definition 模型与 worker launch spec：`src/swe/app/subagents/models.py`
- Definition 构造：`src/swe/app/subagents/definition_service.py`
- Background supervisor：`src/swe/app/subagents/supervisor.py`
- Worker 入口：`src/swe/app/subagents/worker.py`
- Runtime 执行：`src/swe/app/subagents/runtime.py`
- 租户上下文绑定：`src/swe/app/tenant_context.py`
- 模型解析：`src/swe/agents/model_factory.py`

## 问题一：description exceeds 1024 bytes

### 现象

调用 `start_subagent` 时返回：

```text
1 validation error for SubAgentDefinition
description
  Value error, description exceeds 1024 bytes
```

### 根因

`start_subagent` 会先将入参解析成 `SubAgentStartRequest`，然后尝试匹配已有 definition。无匹配时走 run-scoped definition：

```python
definition = definition_service.build_run_scoped_definition(...)
```

`build_run_scoped_definition()` 当前将：

```python
"description": request.objective[:1024]
```

传入 `SubAgentDefinition`。但 `SubAgentDefinition._description_size()` 按 UTF-8 字节数限制 1024 bytes。中文字符通常 3 bytes，`[:1024]` 是按字符截断，不是按字节截断，所以仍可能超过 1024 bytes。

另一个问题是 `build_run_scoped_definition()` 在 `start_subagent` 的 try/except 外部执行，校验异常会直接冒泡成工具调用错误，而不是返回结构化 `invalid_request`。

### 处理方案

1. 增加 UTF-8 字节安全截断 helper，例如 `_truncate_utf8(value, max_bytes)`，保证不会截断到半个字符。
2. `build_run_scoped_definition()` 使用该 helper 构造 description，而不是 `request.objective[:1024]`。
3. `description` 是从 `objective` 派生出的审计/兼容字段，超长时自动截断并继续启动；`instruction` 仍按 worker contract 硬拒绝超过 8192 bytes。
4. 将 definition 构造和 `supervisor.start()` 包进 `start_subagent` 的结构化错误处理，避免 Pydantic 异常直接暴露给主 Agent。
5. 为 `SubAgentStartRequest.objective/background` 增加明确 size validator，避免 start 请求把超长背景塞入 launch spec：

   - `objective`: 4096 bytes
   - `background`: 16384 bytes

### 验证点

- 中文 objective 超过 1024 bytes 时，run-scoped definition 能成功构造，description 字节数不超过 1024。
- `objective` 超过 4096 bytes 或 `background` 超过 16384 bytes 时，`start_subagent` 返回结构化 `invalid_request`。
- `start_subagent` 不再抛 raw Pydantic validation error，而是返回结构化失败或成功启动结果。

## 问题二：worker 找不到租户模型配置

### 现象

`wait_subagent` 看到后台 run failed：

```text
No tenant model configuration found. Please configure a model for this tenant...
```

### 根因

worker 进程由 `BackgroundSubAgentSupervisor.start()` 通过 `python -m swe.app.subagents.worker` 拉起。`WorkerLaunchSpec` 会保留安全 request context 字段，包括：

```python
session_id, chat_id, turn_id, user_id, channel, source_id, trace_id, tenant_id, agent_id
```

但 `run_worker()` 只是把 `launch_spec.request_context` 传入 `SubAgentRuntime.run()`。`SubAgentRuntime` 再把它传给 `SWEAgent(request_context=...)`。

问题在于 `SWEAgent.__init__()` 调用 `create_model_and_formatter()` 时，模型选择不是从 `request_context` 读 tenant，而是从 `swe.config.context` 的 ContextVar 读：

```python
tenant_id = get_current_effective_tenant_id()
ProviderManager.get_instance(tenant_id)
```

worker 子进程没有调用 `bind_tenant_context()`，所以 ContextVar 没有被恢复。结果模型解析落到默认或空租户，找不到该租户 active model。

### 处理方案

1. 在 worker entrypoint `run_worker()` 中，在调用 `runtime.run()` 前根据 launch spec 恢复 **Background SubAgent Launch Identity**；`SubAgentRuntime.run()` 不负责绑定 ContextVar。

   - `tenant_id`: 原始逻辑 tenant，空值回退 `default`。
   - `source_id`: 原始 source。
   - `user_id`: 原始 user。
   - `workspace_dir`: 使用 launch spec 的 workspace dir。
   - `scope_id`: 若 Main Agent 已解析出 runtime scope，则随 launch spec 一起传递并优先恢复。

2. 在 `BackgroundSubAgentSupervisor.start()` 生成 launch spec 前，补齐/规范化 worker request context：

   - `tenant_id = scope.tenant_id`
   - `agent_id = scope.agent_id`
   - 保留原 `source_id/user_id/session_id/chat_id/turn_id/trace_id`

3. 避免把 provider secret 放进 launch spec。当前 `_drop_secret_like_fields()` 与 safe key 白名单应继续保留。
4. `SAFE_WORKER_REQUEST_CONTEXT_KEYS` 增加 `scope_id`，确保 worker 可以恢复父 Main Agent 已解析出的 runtime scope。

### 验证点

- worker 测试中传入逻辑 `tenant_id`、`source_id` 与可选 `scope_id` 时，运行时 `get_current_effective_tenant_id()` 应与父 Main Agent 的运行时身份一致；测试不应在 worker 里重新断言手写拼接规则。
- worker 创建 `SWEAgent` 时不再走空租户/错误租户 ProviderManager。
- launch spec JSON 不包含 API key、secret、password 等字段。

## 问题三：工具返回给主 Agent 的信息过多

### 现象

`wait_subagent` 的工具输出里包含：

- 完整 `result`
- 完整 `errors`
- `worker` 进程信息和 stderr 路径
- `definition_match` 全量对象
- created/started/finished 时间
- `manageable`

失败时这些字段会把 Provider 错误、worker 元数据、AgentResult 全部返回给主 Agent。外层还会再包一层 AgentScope `ToolResponse` / `TextBlock`，可读性更差。

### 根因

`wait_subagent` 调用：

```python
_compact_record(record, include_details=False)
```

但 `_compact_record(..., include_details=False)` 仍然输出了调试和持久化字段：

```python
definition_match, result, errors, worker, manageable
```

这不是持久化层问题，而是 parent-facing 工具结果没有和 debug/API monitor 结果分层。

### 处理方案

定义三类输出投影，不复用同一个 `_compact_record` 处理所有场景：

1. `start_subagent` 默认返回 run handle。顶层 `status` 表示真实 **Background SubAgent Run Status**；`accepted` 表示 start 请求是否创建了 run：

```json
{
  "accepted": true,
  "run_id": "...",
  "status": "running",
  "agent_name": "...",
  "nickname": "...",
  "objective": "..."
}
```

当并发限制阻止启动时：

```json
{
  "accepted": false,
  "status": "blocked",
  "reason": "background_subagent_concurrency_limit",
  "limit": 2,
  "active_run_ids": ["subagent-..."]
}
```

   `definition_match` 不返回给主 Agent，只保留在 per-run JSON 运行记录、应用结构化日志或诊断读取面。启动时记录一条结构化日志，至少包含 `run_id`、`tenant_id`、`agent_id`、`requested_name`、`definition_name`、`definition_source`、`definition_matched` 与匹配原因。

2. `wait_subagent` 默认返回 parent-facing summary：基础 SubAgent run 信息、状态，以及 terminal run 的结果；不返回 `definition_match`、`worker`、`stderr_tail`、`effective_policy`、`delegation_spec` 等路由/worker 诊断字段。
   `terminal_runs` 只包含本次 bounded wait 新观察到的结束 run；已经被之前 `wait_subagent` 返回过的历史结束 run 不会每次重复返回，也不新增额外字段标注该语义。
   `wait_subagent` 参数保持 `timeout_ms`，不新增 `run_id` 过滤参数；主 Agent 需要精确读取时使用 `get_subagent(run_id)`。

```json
{
  "timed_out": false,
  "active_runs": [
    {
      "run_id": "...",
      "status": "running",
      "agent_name": "...",
      "nickname": "...",
      "objective": "..."
    }
  ],
  "terminal_runs": [
    {
      "run_id": "...",
      "status": "failed",
      "agent_name": "...",
      "nickname": "...",
      "objective": "...",
      "result": {
        "status": "failed",
        "summary": "...",
        "findings": [],
        "relevant_files": [],
        "risks": [],
        "recommendations": [],
        "open_questions": [],
        "suggested_next_steps": []
      }
    }
  ]
}
```

`wait_subagent.result` 使用精简 `AgentResult` 投影。保留：

- `status`
- `summary`
- `findings`
- `relevant_files`
- `risks`
- `recommendations`
- `open_questions`
- `suggested_next_steps`

不返回：

- `task_id`
- `agent_run_id`
- `agent_name`
- `metrics`
- `artifacts`
- `errors`

3. `get_subagent` 默认返回与 `wait_subagent` 单个 run 一致的 parent-facing 投影：基础 run 信息、状态，以及 terminal run 的精简 `result`。用于主 Agent 错过某次 `wait_subagent` terminal result 后按 `run_id` 补取。

4. `get_subagent(include_details=True)` 返回受控诊断字段，而不是 raw run record dump。该入口只按明确 `run_id` 读取，不扩展到 `wait_subagent`。

- `result`
- `errors`
- `worker`
- `stderr_tail`
- `effective_policy`
- `delegation_spec`

`include_details=False` 时只返回与 `wait_subagent` 一致的摘要。

诊断模式也不应暴露本地 `stderr_log_path`；worker 信息最多保留 pid、exit code 与时间字段，stderr 只通过 bounded `stderr_tail` 暴露。

### 验证点

- `wait_subagent` 的 terminal run 可包含 `result`，但不包含 `definition_match/worker/stderr_tail/effective_policy/delegation_spec`。
- 失败摘要仍保留足够决策信息：run `status` 与 result `summary`。
- `get_subagent(..., include_details=True)` 仍可用于排查，避免丢失可观测性。

## 建议实施顺序

1. 修复 `build_run_scoped_definition()` 的字节安全截断，并给 `start_subagent` 加结构化异常边界。
2. 修复 worker tenant context 绑定，优先解决实际执行失败。
3. 拆分 SubAgent 工具输出投影，降低主 Agent 上下文噪声。
4. 补齐单元测试：
   - `test_service_builds_run_scoped_definition_truncates_description_by_utf8_bytes`
   - `test_start_subagent_returns_structured_error_for_definition_validation`
   - `test_worker_binds_tenant_context_from_launch_spec`
   - `test_wait_subagent_omits_debug_fields_by_default`
   - `test_get_subagent_include_details_keeps_debug_fields`

## 影响面

GitNexus 当前未识别这些 subAgent 符号，impact 查询返回 `not found`，因此图谱风险为 UNKNOWN。基于源码搜索，直接影响面主要限定在：

- `src/swe/agents/tools/subagent_background.py`
- `src/swe/app/subagents/definition_service.py`
- `src/swe/app/subagents/worker.py`
- `src/swe/app/subagents/runtime.py`
- `tests/unit/subagents/*`
- Console 侧监控 API 不应受默认工具输出投影影响，因为它走 `src/swe/app/subagents/monitor.py` 的独立 snapshot contract。

整体风险评估：中等。风险点不是业务主链路，而是 Background SubAgent 的工具契约与 worker 上下文恢复；需要重点防止泄漏 secret、破坏 Console monitor snapshot，以及让主 Agent 失去必要的失败摘要。
