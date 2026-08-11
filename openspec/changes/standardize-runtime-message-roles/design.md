## Context

当前 hook `additionalContext` 先通过 AgentScope 支持的 `system` 构造消息，再把运行态角色改成 `developer`。这一选择导致 session 加载、聊天详情 API、OpenAI formatter 和 OpenAI-compatible Provider 都需要识别或降级非标准角色。与此同时，accepted plan 在执行轮次被拼接进主 system prompt，导致基础系统指令与某次计划执行数据耦合。

本变更要求运行时不再使用 `developer`，hook 统一使用 `system`，accepted plan 使用 `tool` 角色。实现必须兼顾 AgentScope 的消息模型、OpenAI tool 消息必须关联 tool call 的协议约束，以及旧会话中已落盘的 `developer` 数据。

## Goals / Non-Goals

**Goals:**

- 将运行时消息角色收敛为 `system`、`user`、`assistant` 和 `tool`。
- 保持 hook `additionalContext` 的系统级指令语义，同时删除 `developer` 兼容链路。
- 将 accepted plan 从主 system prompt 中分离，并以协议有效的 tool result 传给模型。
- 在加载边界一次性兼容旧 `developer` 会话，并确保后续保存不再产生该角色。
- 保持计划来源校验、长度限制、Plan Mode 状态和计划审核流程不变。

**Non-Goals:**

- 不改变 hook 事件、matcher、decision 或 `additionalContext` 合并规则。
- 不改变 Proposed Plan 的持久化格式、审核卡片或 execute/revise/exit 决策。
- 不为拒绝非首位 `system` 消息的旧 Provider 保留隐式 user 降级。
- 不允许客户端直接提供 accepted plan 或伪造内部 tool result。

## Decisions

### Decision: hook 上下文始终保留 system 角色

`build_hook_additional_context_msg()` 直接返回 `role="system"` 的消息。OpenAI formatter 清理 `name` 等不兼容字段时，必须保留带 hook 前缀的 system 消息；不得把它转换为 `developer` 或 `user`。

这样能让 hook 指令来源在内存、session、API 和模型输入中保持一致，也能删除开发者角色的反序列化和 Provider 重试分支。代价是只接受首条 system 消息的 Provider 会直接失败，而不是静默改变 hook 指令优先级。

备选方案是继续把非首位 hook system 降级为 user。该方案兼容面更广，但违背 hook 统一使用 system 的要求，并改变指令语义，因此不采用。

### Decision: accepted plan 注入为完整的内部 tool exchange

accepted plan 不再由 `_build_sys_prompt()` 拼接。Agent 初始化执行轮次时，根据经过服务端来源校验的 `accepted_plan` 构造一个内部 assistant tool-call 与对应 tool-result 消息；计划正文只出现在对应的 `tool` 结果中，并使用稳定的内部工具名和本轮唯一 call id。

OpenAI 协议不接受没有关联 `tool_call_id` 的孤立 tool 消息，因此必须注入完整配对。内部 exchange 只用于当前 execute 轮次的模型输入，不伪装成真实用户调用，不触发 ToolGuard、hook、工具执行、前端卡片或计划持久化。

备选方案是创建裸 `role="tool"` 文本消息。该方案在部分 formatter 中可能工作，但会被严格 OpenAI-compatible Provider 拒绝，因此不采用。

### Decision: 旧 developer 历史只在加载边界迁移为 system

`SafeJSONSession` 加载旧会话时，将 `developer` 归一为 `system`，不再在内存态恢复原角色。聊天详情 API 同样以 system 暴露旧消息，并可在 metadata 中保留迁移来源用于诊断；下一次保存后，持久化内容只包含标准角色。

其他未知角色继续按现有安全默认值处理，但不得恢复或生成 `developer`。这样迁移逻辑是单向的，不会持续传播旧角色。

### Decision: 删除 developer 专用 Provider 兼容重试

OpenAI-compatible Provider 不再捕获 `Unexpected message role` 后把 `developer` 降级为 user 重试。formatter 和消息构造边界负责保证运行时不会产生 `developer`；Provider 错误应保留原始失败，避免隐藏协议不匹配。

### Decision: 角色规则由跨边界回归测试和 playbook 共同约束

测试覆盖 hook 构造、tool hook、STOP hook、session 迁移、chat API、OpenAI formatter、Provider 调用以及 accepted plan 注入。`analysis/playbook/common-errors.md` 与 `location-paths.md` 同步删除 developer 处理建议，记录新的 system/tool 定位路径。

## Risks / Trade-offs

- [部分 Provider 拒绝非首位 system] → 不做静默角色降级；通过 Provider 集成测试和明确错误定位暴露兼容性要求。
- [内部 accepted plan tool exchange 被误当成真实工具执行] → 在模型输入装配边界直接构造配对消息，不进入 Toolkit、ToolGuard、hook 或前端事件流。
- [旧 developer 会话迁移改变历史显示角色] → 单向迁移为 system，并保留可选来源 metadata 便于诊断。
- [accepted plan 注入顺序错误导致 tool call/result 不配对] → 使用单一 helper 构造完整 exchange，并在 formatter 层验证 call id 和顺序。
- [移除 Provider 重试暴露原先被隐藏的后端差异] → 将失败视为显式兼容性问题，不再以 user 角色降低指令优先级。

## Migration Plan

1. 先增加角色策略和 accepted plan tool exchange 的测试，锁定新的模型输入结构。
2. 将 hook 消息 helper 改为 system，并更新 runner、ToolGuard、formatter 与 API 断言。
3. 将旧 developer session 加载改为单向 system 迁移，删除恢复逻辑。
4. 将 accepted plan 从 system prompt 移到当前执行轮次的内部 tool exchange。
5. 删除 OpenAI-compatible Provider 的 developer 检测、降级和重试代码。
6. 更新 playbook，并运行角色、hook、session、Provider 和 Plan Mode 的针对性测试。

回滚时可恢复旧实现代码，但迁移后已保存为 system 的历史消息不会自动恢复为 developer；这符合本变更的单向迁移目标。

## Open Questions

- 是否需要在 Provider capability 配置中显式声明支持非首位 system 消息，还是统一依赖调用失败暴露不兼容。
- 内部 accepted plan tool exchange 是否需要在 tracing 中标记为 `internal_context=true`，以便与真实工具调用区分。
