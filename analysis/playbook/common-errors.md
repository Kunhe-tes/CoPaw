# 常见报错

本文档只收录仓库中已经出现过、且有明确入口可追的高频报错。

## Console 复制工具输入时触发 Clipboard 权限策略报错

### 症状

- 聊天回答里的工具调用卡片点击“复制输入”或“复制输出”
- 浏览器控制台出现：
  - `[Violation] Permissions policy violation: The Clipboard API has been blocked because of a permissions policy applied to the current document`
- 常见于 Console 被嵌入 iframe，且父页面未授予 `clipboard-write` 权限的场景

### 典型原因

- 前端直接调用 `navigator.clipboard.writeText()`
- 当前文档的 `Permissions-Policy` 或 iframe `allow` 未允许 Clipboard API
- 浏览器会在调用被拦截 API 时输出 violation，即使后续业务代码捕获异常也可能留下控制台报错

### 第一落点

- [console/src/utils/clipboard.ts](../../console/src/utils/clipboard.ts)
- 重点看是否通过 `document.permissionsPolicy` / `document.featurePolicy` 先判断 `clipboard-write`
- [console/src/components/agentscope-chat/Util/copy.ts](../../console/src/components/agentscope-chat/Util/copy.ts)
- 重点看聊天内复制入口是否复用通用复制工具

### 第一阶段处理

- 权限策略明确禁止 `clipboard-write` 时，不要调用 `navigator.clipboard.writeText()`
- 直接降级到 textarea + `document.execCommand("copy")`
- Clipboard API 运行时失败时，也要降级复制；所有方式失败时返回失败状态，由调用方提示“复制失败”

## 长 MCP 调用期间 console SSE 被静默断开

### 症状

- MCP 工具调用耗时 10 秒以上时，前端 console 会话中断
- `streamable_http` MCP 本身还在执行，但 `/console/chat` 长时间没有任何 SSE 输出
- 日志可见运行被取消，例如：
  - `query_handler: <session_id> cancelled!`
  - `Runner finally block executing for session <session_id>`

### 典型原因

- 外层 `/console/chat` SSE 在长时间无事件期间没有发送心跳帧
- 代理、Ingress 或客户端对 10 到 15 秒静默连接执行 idle timeout
- 即使后端任务未失败，HTTP 流也会先被外层网络链路掐断
- `streamable_http` MCP 如果走到默认 `httpx` timeout，可能在读阶段约 5 秒无新字节时先超时或触发中断链路

### 第一落点

- [src/swe/app/routers/console.py](/Users/shixiangyi/code/Swe/src/swe/app/routers/console.py)
- 重点看 `post_console_chat()` 和 `_stream_with_keepalive()`
- [src/swe/app/runner/runner.py](/Users/shixiangyi/code/Swe/src/swe/app/runner/runner.py)
- 重点看 `_create_mcp_client_with_headers()` 是否给 `streamable_http` MCP 显式配置 `httpx.Timeout`

### 第一阶段处理

- 在 `/console/chat` 的 SSE 输出层补 comment 心跳，例如 `: keep-alive\n\n`
- 心跳周期要小于最短代理 idle timeout，当前实现默认 5 秒
- 响应头显式加 `X-Accel-Buffering: no`，避免代理缓冲导致心跳帧无法及时刷出

### 边界说明

- 这一阶段只解决“外层 SSE 静默断连”
- 不包含 MCP 内部执行进度透传；如果希望前端看到“工具执行中”，需要后续把 MCP progress/event 映射进 `TaskTracker` 或 SSE 事件流

## Console SSE 只返回 keep-alive 没有 data

### 症状

- `/api/console/chat` 返回 `200 text/event-stream`
- 响应头包含 `X-Accel-Buffering: no`，且首帧能收到 `: keep-alive`
- 随后连接结束或长期没有任何 `data:` 模型事件

### 典型原因

- Console 请求经 `_resolve_raw_console_request_data()` 回读原始 JSON 后，`content_parts` 仍是 dict
- `BaseChannel._apply_no_text_debounce()` 如果只按对象属性读取 `type/text`，会把 `{"type":"text","text":"..."}` 误判为无文本消息
- 误判后消息被缓存到 `_pending_content_by_session`，`ConsoleChannel.stream_one()` 直接返回，`TaskTracker` producer 不会调用模型

### 第一落点

- [src/swe/app/routers/console.py](/Users/shixiangyi/code/Swe/src/swe/app/routers/console.py)
- 重点看 `_extract_session_and_payload()` 是否把前端 JSON content 传入 `native_payload["content_parts"]`
- [src/swe/app/channels/base.py](/Users/shixiangyi/code/Swe/src/swe/app/channels/base.py)
- 重点看 `_content_has_text()`、`_content_has_audio()` 和 `_apply_no_text_debounce()` 是否同时兼容 runtime Content 对象与 dict
- [src/swe/app/channels/console/channel.py](/Users/shixiangyi/code/Swe/src/swe/app/channels/console/channel.py)
- 重点看 `stream_one()` 是否在 debounce 后继续构造 `AgentRequest`

### 第一阶段处理

- 用 `curl --no-buffer -N` 先确认是否至少收到首个 `: keep-alive`
- 如果只有 keep-alive，没有 `data:`，检查 `content_parts` 的实际类型
- dict 文本块应被识别为完整用户输入，再交给 `AgentRequest` 做 runtime content 类型转换
- 若已能收到 `response created/in_progress/failed`，说明 SSE 和 producer 已通，后续错误应转向模型 Provider、工具或 Runner 配置

## Console 第二轮提问报 System message must be at the beginning

### 症状

- `/api/console/chat` 首轮请求正常，沿用同一个 `session_id` 第二轮提问失败
- SSE 返回 `Unknown agent error: BadRequestError: Error code: 400`
- 模型后端错误内容包含：
  - `System message must be at the beginning.`
- query error dump 栈一般落在 `agentscope/model/_openai_model.py` 调用 OpenAI-compatible `chat.completions.create`

### 典型原因

- 首轮结束后的 hook additionalContext 被追加进 `agent.memory`
- 如果追加消息使用 `role=system`，第二轮历史会变成 `system/user/assistant/system/user`
- hook 附加上下文统一使用 `developer` 角色；AgentScope `Msg` 构造器不直接支持该角色，需通过 hook message helper 构造
- 严格 OpenAI-compatible 后端只允许第一条消息是 `system`，会拒绝非首位 system
- 已经落盘的旧 session 即使源头修复，也可能继续携带历史尾部 system

### 第一落点

- [src/swe/app/runner/runner.py](/Users/shixiangyi/code/Swe/src/swe/app/runner/runner.py)
- 重点看 `_emit_stop_hook_if_needed()` 写入 STOP hook additionalContext 时是否使用 developer hook message helper
- [src/swe/agents/model_factory.py](/Users/shixiangyi/code/Swe/src/swe/agents/model_factory.py)
- 重点看 OpenAI formatter 最终清洗是否把历史 hook `system` 转为 `developer`
- [src/swe/agents/tool_guard_mixin.py](/Users/shixiangyi/code/Swe/src/swe/agents/tool_guard_mixin.py)
- 重点看 `_record_tool_hook_result()` 是否同样使用 developer hook message helper
- 对应测试：
  - [tests/unit/app/test_runner_hook_runtime.py](/Users/shixiangyi/code/Swe/tests/unit/app/test_runner_hook_runtime.py)
  - [tests/unit/agents/test_model_factory_tenant.py](/Users/shixiangyi/code/Swe/tests/unit/agents/test_model_factory_tenant.py)

### 第一阶段处理

- 新增 hook 附加上下文不要追加为尾部 `system` 或 `user`，应统一写为 `developer`
- formatter 侧保留兜底：只有第 0 条消息允许继续保持 `role="system"`，历史 hook system 转为 developer，其他非首位 system 转为 user
- 如果仍报错，检查当前 session 落盘 JSON 中 `agent.memory.content` 的 role 顺序，确认是否还有非首位 system 绕过了 formatter

## 会话恢复时报 Msg.from_dict 断言失败

### 症状

- 发起已有 `session_id` 的会话时，Runner 在加载 session state 阶段直接报错
- 常见堆栈包含：
  - `SafeJSONSession.load_session_state()`
  - `ReMeInMemoryMemory.load_state_dict()`
  - `Msg.from_dict(...)`
  - `assert role in ["user", "assistant", "system"]`
- 落盘的 session JSON 里可以看到 hook additionalContext 消息使用 `role="developer"`

### 典型原因

- hook additionalContext 为了兼容 OpenAI-compatible 后端，会在 memory / session 中保留 `developer` 语义
- AgentScope `Msg` 运行态允许先构造 `system` 再改写为 `developer`，但 `Msg.from_dict()` 反序列化时仍只接受 `user/assistant/system`
- 会话恢复如果直接把落盘 JSON 交给底层 memory `load_state_dict()`，就会在反序列化阶段触发断言

### 第一落点

- [src/swe/app/runner/session.py](/Users/shixiangyi/code/Swe/src/swe/app/runner/session.py)
- 重点看 `load_session_state()` 是否在调用底层 `load_state_dict()` 前做消息 role 兼容迁移，并在内存态恢复原始 role
- [src/swe/agents/hook_runtime/messages.py](/Users/shixiangyi/code/Swe/src/swe/agents/hook_runtime/messages.py)
- 重点看 hook 附加上下文是否仍通过 helper 生成 `developer` 消息
- 对应回归测试：
  - [tests/unit/app/test_session.py](/Users/shixiangyi/code/Swe/tests/unit/app/test_session.py)
  - [tests/unit/app/test_runner_hook_runtime.py](/Users/shixiangyi/code/Swe/tests/unit/app/test_runner_hook_runtime.py)

### 第一阶段处理

- 不要把落盘里的 `developer` role 直接改成普通 `user`，否则会丢失 hook 语义
- 在 session 加载边界先把不被 AgentScope 接受的 role 临时降级成 `system`，待 `Msg` 实例化成功后再恢复原始 role
- 如果用户已经产生坏 session 文件，修复代码后重新发起同一 `session_id` 即可触发兼容恢复，不需要先手工删历史

## Console 切换运行中会话时 reconnect 返回 404

### 症状

- 两个 console 会话同时流式输出，前端在会话间快速切换
- 前端发起 `/api/console/chat` reconnect 请求，body 里 `session_id` 可能是本地时间戳格式
- 后端返回 404，detail 为 `No running chat for this session`

### 典型原因

- Console 前端先创建本地时间戳 session，再等待后端创建真实 `chat.id`
- 切换会话会断开当前 SSE，并用 `reconnect=true` 重新附着到后端 `TaskTracker`
- reconnect 请求可能早于后端完成 `session_id -> chat.id -> run_key` 注册，第一次查询映射或 active run 时会查不到

### 第一落点

- [src/swe/app/routers/console.py](/Users/shixiangyi/code/Swe/src/swe/app/routers/console.py)
- 重点看 `_attach_reconnect_queue()` 对 `session_id`、`chat.id` 和 `TaskTracker.attach()` 的处理
- [src/swe/app/runner/task_tracker.py](/Users/shixiangyi/code/Swe/src/swe/app/runner/task_tracker.py)
- 重点看 run_key 是否使用 `ChatSpec.id`
- [console/src/pages/Chat/sessionApi/index.ts](/Users/shixiangyi/code/Swe/console/src/pages/Chat/sessionApi/index.ts)
- 重点看本地时间戳 session 与真实 `chat.id` 的映射

### 第一阶段处理

- reconnect 不要只查一次；在短窗口内重试解析 `session_id -> chat.id` 并附着 active run
- 保持 run_key 统一为 `ChatSpec.id`，不要把前端本地时间戳直接当作 `TaskTracker` key
- 如果问题仍出现，抓取同一请求的 `session_id`、解析出的 `chat_id`、`TaskTracker.list_active_tasks()` 三项证据

## 长 Tool 执行后会话出现用户中断且 Chat 状态卡在 running

### 症状

- Tool 执行时间较长时，前端会话出现类似 `The tool call has been interrupted by the user` 的中断提示
- 查询 `GET /api/chats/{chat_id}` 或 `/api/chats/{chat_id}` 时，返回 `status=running`
- 实际上用户未主动点击停止，或停止已经发出但后端仍在清理资源

### 典型原因

- 前端流式请求存在客户端侧绝对超时，超时后 abort fetch，外层 agent 可能把它解释为用户中断
- 前端 abort 没有区分 `detach`、`stop` 和 `timeout`，切换会话等纯断流动作可能与停止任务混淆
- `TaskTracker.get_status()` 只看 producer task 是否 `done()`，当 stop/timeout 已发出但 producer 仍在 `finally` 清理时会继续返回 `running`
- 旧 producer 的 `finally` 如果无条件删除 `_runs[chat_id]`，可能误删同一 chat 后续新 run 的状态

### 第一落点

- [console/src/pages/Chat/index.tsx](/Users/shixiangyi/code/Swe/console/src/pages/Chat/index.tsx)
- 重点看 `/console/chat` fetch、`createTimedAbortSignal()` 和 stop 调用
- [console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/hooks/useChatRequest.tsx](/Users/shixiangyi/code/Swe/console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/hooks/useChatRequest.tsx)
- 重点看 `cancelActiveRequest()` 是否传递真实 `chat_id`
- [src/swe/app/runner/task_tracker.py](/Users/shixiangyi/code/Swe/src/swe/app/runner/task_tracker.py)
- 重点看 `request_stop()`、`mark_stopping()`、`get_status()` 和 producer `finally`
- [src/swe/app/runner/runner.py](/Users/shixiangyi/code/Swe/src/swe/app/runner/runner.py)
- 重点看 `_enforce_query_timeout()` 是否在 interrupt 前把 run 标为 `stopping`

### 第一阶段处理

- 默认不要给 chat stream 设置前端绝对超时；只在用户显式 stop 时调用 `/console/chat/stop`
- 用 abort reason 区分：
  - `detach`：切换会话或断开 SSE，只断前端流，不停止后端任务
  - `stop`：用户主动停止，调用后端 stop
  - `timeout`：显式配置的客户端超时，按配置决定是否 stop
- 后端状态使用 `idle/running/stopping`；stop 或 query timeout 发出后先返回 `stopping`，清理完成后再变 `idle`
- producer 清理 `_runs` 时必须确认当前 `_runs[chat_id]` 仍是自己，避免旧 run 清理误删新 run

### 边界说明

- 这只能避免“前端默认超时或断流误杀任务”
- 后端仍可能被配置型超时中止，例如 `SWE_QUERY_TIMEOUT_SECONDS`、`SWE_MCP_PER_NOTIFICATION_TIMEOUT`、`SWE_LOCAL_TOOL_EXECUTION_HARD_TIMEOUT` 或 shell tool 的 `timeout` 参数
- 若要允许超长 MCP tool，MCP server 应定期发送 progress notification，或调大 per-notification timeout

## BeforeStop 预算耗尽提示流出但历史缺失

### 症状

- `BeforeStop` 持续返回 `block` 后，前端能看到“任务未完成”提示
- 刷新或重新加载会话后，历史最后一条仍是上一轮模型回复，看不到预算耗尽提示
- Trace 或 Monitor 里最终输出也可能只记录模型回复，缺少用户实际看到的未完成状态

### 典型原因

- Runner 手动构造并 `yield` 预算耗尽提示，但没有写入 `agent.memory`
- `finally` 阶段保存 session state 时只保存 memory 内容，stream-only 消息会丢失

### 第一落点

- [src/swe/app/runner/runner.py](/Users/shixiangyi/code/Swe/src/swe/app/runner/runner.py)
- 重点看 `_stream_completion_lifecycle()` 的 BeforeStop 预算耗尽分支，以及 `_save_regular_session_state()` 保存前 memory 中是否包含同一条提示

### 第一阶段处理

- 对用户可见、需要进入历史的 runner 合成消息，先写入 `runtime.agent.memory`，再 `yield`
- 测试同时断言 stream 输出和 session state 末尾内容，避免只验证前端当次可见

## 当前 Source 系统配置页返回 403 或保存后步骤条行为未变化

### 症状

- 打开 `system-config-page` 直接显示 403，或页面入口在菜单中不可见
- 页面能打开，但保存 `任务进度步骤条` 开关后，聊天页仍继续展示步骤条
- 后端 current-source API 返回 `Manager role required`

### 典型原因

- iframe 上下文没有透传 `isSuperManager` / `manager`，导致前端未发送 `X-User-Role`
- 前端误以为只隐藏 UI 就够了，但没有刷新 effective source config store
- 后端 raw current-source 配置虽然写入成功，但仍被旧的 effective config 缓存命中，或者下一轮请求前没有重新读取

### 第一落点

- [console/src/api/authHeaders.ts](/Users/shixiangyi/code/Swe/console/src/api/authHeaders.ts)
- 重点看 `isSuperManager -> admin`、`manager -> manager` 的头映射是否存在
- [console/src/pages/SystemConfigPage/index.tsx](/Users/shixiangyi/code/Swe/console/src/pages/SystemConfigPage/index.tsx)
- 重点看保存/删除成功后是否调用 `loadEffectiveConfig(activeSourceId)`
- [src/swe/app/source_system_config/router.py](/Users/shixiangyi/code/Swe/src/swe/app/source_system_config/router.py)
- 重点看 `/api/source-system-config/current` 是否只从 `request.state.source_id` 取目标 source，且仍要求 manager/admin
- [src/swe/agents/react_agent.py](/Users/shixiangyi/code/Swe/src/swe/agents/react_agent.py)
- [src/swe/agents/tools/update_task_progress.py](/Users/shixiangyi/code/Swe/src/swe/agents/tools/update_task_progress.py)
- [src/swe/app/runner/runner.py](/Users/shixiangyi/code/Swe/src/swe/app/runner/runner.py)
- 重点看 prompt、tool、stream 三段是否都走了 `chat_task_progress_enabled` 判定

### 第一阶段处理

- 先确认请求头里已经带上 `X-User-Role: admin|manager`
- 再确认保存或删除后，前端已经刷新 effective config store，而不是只刷新当前页面表单
- 如果聊天页行为没变化，抓下一轮请求的 effective config，再核对 prompt、tool、stream 三处是否都已关闭

## Tenant bootstrap 时报 default workspace 缺少 agent.json

### 症状

- 首次访问租户、`ensure_bootstrap()` 自愈，或 `TenantInitializer.initialize()` 期间直接失败
- 常见异常为：
  - `FileNotFoundError: Agent config not found: <tenant>/workspaces/default/agent.json`
- 伴随日志里可能先看到：
  - `Config file not found, copying from md_files templates...`
  - `Source file not found: .../src/swe/agents/md_files/config.json`

### 典型原因

- `ensure_default_agent_exists()` 只保证 root `config.json`、`chats.json` 和 `jobs.json`，不会直接生成 default workspace 的 `agent.json`
- `ensure_default_workspace_scaffold()` 在没有模板 `agent.json` 时，如果先 `load_agent_config()`，就会在 fallback 生成之前触发异常
- cached tenant 自愈场景下，`config.json` 或 `agent.json` 被删除后再次 bootstrap，也会走到同一条缺口

### 第一落点

- [src/swe/app/workspace/tenant_initializer.py](/Users/shixiangyi/code/Swe/src/swe/app/workspace/tenant_initializer.py)
- 重点看 `ensure_default_workspace_scaffold()` 是否遵循“优先复制模板，没有模板再按 tenant root config 合成 fallback agent.json”
- [src/swe/app/migration.py](/Users/shixiangyi/code/Swe/src/swe/app/migration.py)
- 重点看 `ensure_default_agent_exists()` / `_do_ensure_default_agent()` 只负责最小 bootstrap，不要误以为它会补齐 workspace 级 `agent.json`

### 第一阶段处理

- 先确认 default 模板租户是否存在 `workspaces/default/agent.json`
- 有模板时，优先检查模板复制路径和 `workspace_dir` 重写是否正确
- 没模板时，检查 fallback `AgentProfileConfig` 是否从 tenant root `config.json` 正确构造并落盘
- 回归至少覆盖三类路径：
  - 首次初始化
  - 从 default 模板复制 agent 配置
  - cached tenant 删除 `agent.json` 后再次 `ensure_bootstrap()` 自愈
