## Why

运行时目前使用 OpenAI 新增的 `developer` 角色保存 hook 上下文，并为不支持该角色的模型、会话和 API 增加了多层兼容逻辑。这既扩大了消息格式差异，也让 hook 与 accepted plan 的指令来源语义不清晰，需要收敛到 AgentScope 和各 Provider 普遍支持的标准角色。

## What Changes

- **BREAKING**：运行时不再创建、持久化、恢复、展示或向模型发送 `developer` 角色消息。
- hook `additionalContext` 统一使用 `system` 角色，不再转换为 `developer` 或在 Provider 拒绝时降级为 `user`。
- accepted plan 执行上下文不再拼接到主 system prompt，改为以 `tool` 角色消息注入执行轮次。
- 清理仅为 `developer` 角色存在的 session、runtime API、OpenAI formatter 和 Provider 重试兼容逻辑。
- 更新角色相关回归测试和排障文档，明确 hook 使用 `system`、plan 使用 `tool` 的规则。

## Capabilities

### New Capabilities

- `runtime-message-role-policy`: 定义运行时允许的消息角色，以及 hook system 上下文、accepted plan tool 上下文和历史消息兼容边界。

### Modified Capabilities

无。

## Impact

- 受影响后端主要包括 `src/swe/agents/hook_runtime/messages.py`、`src/swe/agents/model_factory.py`、`src/swe/providers/openai_chat_model_compat.py`、`src/swe/agents/react_agent.py`、`src/swe/app/runner/session.py`、`src/swe/app/runner/utils.py` 和相关 runner 路径。
- 已落盘的旧 `developer` 会话需要在加载边界迁移为 `system`，迁移后不得重新恢复为 `developer`。
- accepted plan 的模型输入顺序和角色发生变化，但计划持久化、审核卡片和执行决策 API 保持不变。
- 需要更新 hook、session、chat API、formatter、Provider 和 Plan Mode 相关单元测试，以及 `analysis/playbook/` 中的角色排障说明。
