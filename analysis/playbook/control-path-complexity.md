# 控制路径复杂度回归

## 适用场景

工具策略、审批恢复、Console 请求解析、专家准入及 Stop append 的单函数复杂度超过 15 时，优先按职责提取局部 helper，保持原有分支顺序、副作用、异常和清理边界。

## 本次拆分入口

| 入口 | 提取职责 |
|------|----------|
| `ToolGuardMixin._acting_policy_denial` | SubAgent 有效权限校验与工具次数预算消耗 |
| `ToolGuardMixin._build_approval_extra` | 保留审批重放所需的 thinking blocks |
| `console._extract_session_and_payload` | 专家选择与绑定版本元数据 |
| `AgentRunner._resolve_pending_approval` | 外部审批冲突消息与专家执行释放 |
| `AgentRunner._prepare_query_agent_context` | 专家主执行上下文、记忆及已批准工具调用 |
| `admit_expert_main` | 绑定版本校验与注册前重新校验 |
| `normalize_stop_append_output` | appendText 类型、非空与 UTF-8 字节上限校验 |
| `HookRuntime.emit_stop_append` | 取消状态、异常与截止时间的完成任务过滤 |

审批超时应先释放专家执行再记录超时，主动拒绝仍先记录决定再释放。专家准入的注册前复查必须留在 `try/finally` 内，保证失败或取消时释放已准备资源。追加文本不得被 strip 改写，任务过滤不得对已取消任务读取异常或结果。

## 校验口径

`tests/unit/agents/test_complexity_budget.py` 同时约束以上八个入口与提取出的 helper，避免将超标分支整体搬入另一个超标函数。断言失败时输出各函数计数。

该测试使用仓库现有的 AST 决策节点计数；它与 Sonar、McCabe 的布尔表达式、推导式和嵌套计数口径不同，不能把本地测试分数当成 Sonar 扫描结果。交付前运行相关行为测试，并由 CI 的实际 Sonar 扫描确认扫描器门禁。

```bash
venv/bin/python -m pytest tests/unit/agents/test_complexity_budget.py -q
venv/bin/python -m pytest tests/unit/agents/hook_runtime/test_stop_append.py tests/unit/agents/test_tool_guard_hook_runtime.py tests/unit/routers/test_console_chat_expert_main.py tests/unit/app/test_expert_main_runtime.py tests/unit/app/test_external_approvals.py tests/unit/app/test_daemon_approval_messages.py tests/unit/app/test_runner_auth_token_passthrough.py tests/unit/app/test_console_chat_file_url_network.py tests/unit/app/test_console_chat_system_prompt_injections.py -q
venv/bin/python -m pytest tests/unit/subagents/test_react_agent_and_guard_integration.py -k 'tool_call_budget or hard_policy or mcp_policy' -q
```

2026-10-27 修改生产代码前，完整 SubAgent 集成测试中的 `test_subagent_toolkit_filters_builtins_and_excludes_delegate` 已失败：实际工具列表比断言多 `emit_wplus_sop_event`。本次只处理复杂度，不修改工具注册或该断言；报告验证结果时应单独列出该基线失败。
