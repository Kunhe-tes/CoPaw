# SubAgent 与 Plan Mode 实现审阅记录

## 审阅范围

- 基线提交：`81af1106 feat(subagents): add runtime mvp`
- 审阅范围：`81af1106..HEAD`
- 当前 HEAD：`a5bae043 add .gitignore`
- 审阅日期：2026-05-30

本次审阅通过 4 个只读子代理并行拆分：

- 后端 SubAgent runtime：`src/swe/app/subagents/`、`src/swe/agents/tools/delegate_to_subagent.py`、`ToolGuardMixin`、相关测试。
- 后端 Plan Mode：`src/swe/app/plans/`、`src/swe/agents/tools/planning.py`、runner、console router、相关测试。
- Console 前端交互：Plan Mode 入口、composer 菜单、计划卡片、stream/patch 处理。
- OpenSpec/文档/测试契约：`openspec/`、`docs/superpowers/`、`analysis/playbook/` 与测试覆盖。

## 总体结论

SubAgent runtime 已从 runtime MVP 继续收紧为“同步、只读、fresh context、主 Agent 显式委派”的实现形态。核心边界包括内置 definition、有效权限交集、只读 shell allowlist、子 Agent 禁止技能/MCP/内存、结构化 `AgentResult` 返回、run store 记录，主干测试覆盖较完整。

Plan Mode 已实现为“主 Agent 的显式计划模式”，不是自动调用 `plan-researcher` 的模式。状态保存在 `ChatSpec.meta.plan_mode_enabled`，请求显式携带 `mode=plan|normal`，计划通过后端生成的 `plan_id` 和工作区 JSON 记录成为执行事实来源。`execute` 后进入正常模式，并把后端回读的 accepted plan 注入主 Agent 系统提示词。

当前主要风险集中在本地 JSON 存储并发、前端计划决策失败后的不可重试、以及少数 spec 与实现偏差。整体是可用的 MVP，但还不是高并发/跨 pod 稳态方案。

## SubAgent Runtime 现状

### 运行链路

1. 主 Agent 在 `SWEAgent._create_toolkit` 中按 `request_context.enable_subagents` 注册 `delegate_to_subagent`，且 `agent_role=subagent` 时不会注册该工具。
2. `delegate_to_subagent` 构造 `DelegationSpec`，从父 Agent 工具配置推导只读 `parent_policy`，再调用 `DelegationManager.delegate`。
3. `DelegationManager` 禁止 nested delegation，使用 `AgentRegistry.resolve` 解析内置或注入的 definition，并通过 `compose_effective_policy(parent, definition, runtime, workspace)` 计算有效权限。
4. run 记录通过 `SubAgentRunStore` 创建，默认落到租户 app state 的 `workspaces/<agent_id>/subagent_runs.json`，避免写入被分析的 repo checkout。
5. `SubAgentRuntime.run` 创建 fresh `SWEAgent`：关闭 memory manager、MCP clients、workspace skills，复用父 Agent config/model，注入 `agent_role=subagent`、`subagent_policy`、`subagent_budget`。
6. 子 Agent 只接收 definition prompt、安全约束、workspace、有效工具摘要和 `DelegationSpec` JSON，不加载父会话历史或主 Agent scratchpad。
7. 输出通过 `AgentResult` 校验；无效 JSON 会尝试一次 repair，仍失败则返回结构化 `partial`，超时和异常返回 `failed`。

### 权限边界

- Definition 校验拒绝 MCP、技能、memory、worktree、nested delegation、自定义 model routing、未知工具和 mutating 工具。
- 有效策略取多方 allow 交集，deny 优先。
- `ToolGuardMixin._acting` 会在 hook 和审批前先执行 SubAgent hard policy，并在 hook 改写 input 后二次校验。
- Shell 只允许保守读取命令：`pwd`、`ls`、`rg`、`grep`、`sed`、`git status/diff/grep/log/show` 等；拒绝管道、重定向、后台、复合语法、`--output`、`--pre`、`--ext-diff`、`sed -i/-f`、`sed w/e`、测试、部署、迁移等。

### 已补强点

- registry 使用语义化版本排序，禁止用户定义遮蔽 builtin。
- permission 配置侧也加入防扩权校验，不只校验 `tools.allow`。
- run store 默认目录移出 repo checkout。
- runtime 增加预算取 min、剩余 timeout、fenced JSON 提取、结构化失败和 runtime-owned metrics。
- 子 Agent 工具调用预算在 hard policy 中计数。

## Plan Mode 后端现状

### 状态模型

Plan domain 位于 `src/swe/app/plans/`：

- `PlanStatus`: `proposed`、`revision_requested`、`accepted`、`exited`
- `PlanReviewDecisionType`: `revise`、`execute`、`exit_plan`
- `ProposedPlan` 由后端生成 `plan_id`，保存 `chat_id/session_id/turn_id/created_by/status/decisions`
- 所有 plan 模型 `extra="forbid"`，避免前端注入未声明字段

### 计划创建与审核

1. 主 Agent 调用 `submit_proposed_plan`。
2. `PlanService.create_plan` 通过 `JsonProposedPlanStore` 写入 `<workspace_dir>/plans/<chat_id>/<plan_id>.json`。
3. 工具返回 `metadata.plan_interaction_card`，类型为 `plan_review`。
4. 前端提交 `plan_interaction_response`，console router 调用 `_record_plan_review_decision`。
5. `revise`：记录 decision，计划进入 `revision_requested`，chat 继续 `plan_mode_enabled=true`。
6. `execute`：记录 decision，计划进入 `accepted`，后端回读持久化 plan，构造 `accepted_plan` 并标记 `accepted_plan_source=server_plan_store`。
7. `exit_plan`：记录 decision，计划进入 `exited`，关闭 Plan Mode，不启动主 Agent run，直接返回短路 SSE 完成事件。

### 执行防护

- Console 请求清洗 `accepted_plan`、`accepted_plan_source` 等 backend-only meta，前端伪造会被移除。
- Runner 仅在 `accepted_plan_source == "server_plan_store"` 时把 accepted plan 注入 `request_context`。
- `SWEAgent._build_sys_prompt` 只在 normal mode 且 accepted plan 来源可信时追加 `[Accepted Plan Execution Context]`。
- Plan Mode 下不会注入 `update_task_progress` 强制提示，避免提示和工具集不一致。

### Plan Mode 权限

Plan Mode 是主 Agent 的只读规划态：

- Toolkit 仅保留读文件、搜索、时间、只读 shell、规划交互工具；启用 SubAgent 时保留只读 `delegate_to_subagent`。
- `write_file`、`edit_file`、`copy_file_to_static`、`update_task_progress`、`set_user_timezone`、`get_token_usage` 等不会注册。
- `ToolGuardMixin` 对 Plan Mode 的 shell 进行独立只读校验，并在 hook 改写后重新校验。

## Console 前端现状

### 入口与请求

- `PlanModeMenuItem` 放入 composer quick menu 和 welcome 输入区。
- `/plan <text>` 会持久化 Plan Mode，然后发送去掉 `/plan` 后的正文，并附带 `mode=plan`。
- 普通提交会根据当前状态补 `mode=plan|normal`。
- `customFetch` 把 `mode` 和 `plan_interaction_response` 展开到请求顶层，后端再归入 `native_payload.meta`。

### 计划卡片

- `messageMeta.extractPlanInteractionCard` 只从 `plan_interaction_card` metadata 中识别卡片，不解析自由文本。
- 历史消息通过 `sessionApi.buildResponseCard` 注入 `PlanInteraction` 卡。
- 流式消息通过 `useChatRequest` 每帧识别 `plan_interaction_card` 并追加卡片。
- `PlanClarificationCard` 支持单选、多选、文本输入，并把用户回答作为下一轮 `plan_interaction_response`。
- `PlanReviewCard` 支持 `revise`、`execute`、`exit_plan`，分别提交 `mode=plan|normal` 和决策 payload。

## 测试与契约覆盖

### 已覆盖

- SubAgent definition、registry、policy、run store、runtime、delegate tool：
  - `tests/unit/subagents/test_models_registry_policy.py`
  - `tests/unit/subagents/test_runtime_and_delegation.py`
  - `tests/unit/subagents/test_react_agent_and_guard_integration.py`
- Plan domain、JSON store、service 幂等和冲突：
  - `tests/unit/app/plans/test_models.py`
  - `tests/unit/app/plans/test_store.py`
- Planning tools：
  - `tests/unit/agents/tools/test_planning.py`
- Runner 状态迁移和 accepted plan 注入：
  - `tests/unit/app/test_runner_plan_mode_state.py`
  - `tests/unit/app/test_task_progress_switch.py`
- Console stream、metadata 清洗、execute/revise/exit/duplicate：
  - `tests/unit/routers/test_console_chat_stream.py`
- Chat API partial patch：
  - `tests/unit/app/test_chat_api_update.py`
- 前端 Plan Mode 与卡片：
  - `console/src/pages/Chat/planMode.test.tsx`
  - `console/src/pages/Chat/components/PlanInteractionCards.test.tsx`
  - `console/src/pages/Chat/messageMeta.test.ts`
  - `console/src/components/agentscope-chat/ComposerQuickMenu/index.test.tsx`

### 部分覆盖

- “Plan card 不从自由文本 JSON 解析”：代码路径正确，但缺少明确的负例测试。
- “SubAgent 继承父模型”：runtime 复制父 `AgentProfileConfig`，但缺少明确断言 provider/model 不被 definition 改写。
- “Plan Mode 不自动调用 `plan-researcher` / 不新增 async subagent API”：代码上未发现自动调用或异步 API，但缺少防回归测试。
- Console 对 `plan_id` 缺失、跨 chat、not found 的错误码分支有实现，测试覆盖不完整。

## 风险与缺口

### 高风险

1. **SubAgent run store 并发覆盖**
   - `DelegationManager.delegate` 默认每次创建 `LocalJsonSubAgentRunStore`。
   - `LocalJsonSubAgentRunStore` 是无锁读改写 JSON 文件。
   - 并发委派可能丢 run 记录或状态回退。

2. **Plan Review 前端提交失败后不可重试**
   - `PlanReviewCard.handleDecision` 在请求发出前写入 `sessionStorage` 并禁用按钮。
   - 后端 409、404 或网络失败后，当前浏览器会继续认为该 plan 已提交。

### 中风险

1. **Plan decision JSON store 并发竞态**
   - `PlanService.record_decision` 与 `JsonProposedPlanStore.record_decision` 都是读改写。
   - 并发 `execute` / `revise` 可能同时读到 `proposed`，后写覆盖前写，破坏终态不可改语义。

2. **`DelegationSpec` 的业务约束多为软约束**
   - `constraints`、`allowed_actions`、`forbidden_actions`、`return_policy` 主要作为 JSON 输入给模型。
   - runtime 没有按 `return_policy` 做结果裁剪、限长或字段强制。

3. **Plan Mode 短路事件前端反馈弱**
   - 后端会发 `type=exit_plan|plan_*_duplicate` 的完成事件。
   - 前端当前主要按 terminal response 收口，没有针对这些 type 展示明确状态。

4. **i18n 不完整**
   - `chat.commands.plan`、`chat.planMode.*`、计划卡片标题和按钮存在 fallback 或英文硬编码。

5. **`/chats/{chat_id}` partial patch 面偏宽**
   - 当前 patch 仍可合并 `session_id/user_id/channel/status` 等字段。
   - 对 Plan Mode 只 patch meta 的语义来说，接口面较宽。

### 低到中风险

1. **`/plan` 无文本与 OpenSpec 存在偏差**
   - OpenSpec 要求 `/plan` 只进入 Plan Mode 且持久化。
   - 当前实现只 `setPlanModeEnabled(true)`，不调用 `persistPlanMode`，刷新或跨端可能丢状态。

2. **`max_turns` 与 repair 回合语义不完全一致**
   - runtime 首轮输出无效后会额外进行一次 repair。
   - 该 repair 受总 timeout 控制，但没有直接按 `max_turns` 拦截。

## 后续建议

1. 优先给 `LocalJsonSubAgentRunStore` 和 `JsonProposedPlanStore.record_decision` 增加进程内锁或原子 compare-and-write 语义，并补并发测试。
2. 调整 Plan Review 前端提交策略：只在后端确认成功或收到明确终态事件后写入 submitted 状态；失败时恢复按钮并提示可重试。
3. 让前端识别 `exit_plan`、`plan_execute_duplicate`、`plan_revise_duplicate`、`plan_exit_duplicate`，展示明确的轻量状态消息。
4. 修正 `/plan` 无文本逻辑，使其也调用 `persistPlanMode(true)`；保留不发模型请求的行为。
5. 为 `accepted_plan`、Plan card metadata、SubAgent model inheritance、no automatic subagent、async API 缺失场景增加防回归测试。
6. 补全 Plan Mode 与计划卡片 i18n，避免生产 UI 中英文混杂。
7. 若进入多实例 Kubernetes 稳态，评估将 Proposed Plan store 和 SubAgent run store 替换为 Redis/MySQL 或其他跨 pod 一致存储。

## 相关入口

- SubAgent runtime：`src/swe/app/subagents/`
- 委派工具：`src/swe/agents/tools/delegate_to_subagent.py`
- Plan domain：`src/swe/app/plans/`
- Planning tools：`src/swe/agents/tools/planning.py`
- Runner 状态注入：`src/swe/app/runner/runner.py`
- Console route：`src/swe/app/routers/console.py`
- 主 Agent 工具与 prompt：`src/swe/agents/react_agent.py`
- hard policy：`src/swe/agents/tool_guard_mixin.py`
- 前端 Plan Mode：`console/src/pages/Chat/planMode.tsx`
- 前端计划卡片：`console/src/pages/Chat/components/PlanInteractionCards.tsx`
- 卡片 metadata：`console/src/pages/Chat/messageMeta.ts`
- OpenSpec：
  - `openspec/specs/subagent-runtime/spec.md`
  - `openspec/changes/archive/2026-05-26-subagent-runtime-mvp/`
  - `openspec/changes/plan-mode-main-agent-planning/`
