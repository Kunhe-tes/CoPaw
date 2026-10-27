# Expert-as-Main 测试覆盖与验证边界

日期：2026-10-27。适用工作区：`.worktrees/expert-as-main`。本报告将已确认的 Q1–Q26、Q16a/Q16b 对应到实际测试；不把计划勾选、源码检查、组件测试等同于真实模型或浏览器验收。结果以各次执行时的代码为准，后续新增测试需另记结果。浏览器首消息 409 可见草稿恢复曾失败，修复后已按浏览器报告复验通过，见末节。

## 阅读约定

下表 `别名::测试名` 是可展开的实际 pytest node；Vitest 使用 `别名 > it 名称`。参数化节点省略参数后缀，测试文件内列明全部参数。

| 别名 | 测试文件 |
| --- | --- |
| S | `tests/unit/app/test_source_system_config.py` |
| B | `tests/unit/app/test_expert_main_binding.py` |
| P | `tests/unit/app/test_expert_main_preparation.py` |
| R | `tests/unit/app/test_expert_main_runtime.py` |
| C | `tests/unit/app/test_expert_main_commands.py` |
| A | `tests/unit/routers/test_console_chat_expert_main.py` |
| D | `tests/unit/subagents/test_expert_main_dependency_versions.py` |
| M | `tests/unit/agents/test_expert_main_memory.py` |
| H | `console/src/pages/Chat/useExpertBinding.test.tsx` |
| F | `console/src/pages/Chat/index.test.tsx` |
| E | `console/src/pages/Chat/ExpertSelector/index.test.tsx` |
| I | `console/src/pages/Chat/components/runtimeMessageHeader.test.tsx` |
| W | `console/src/components/agentscope-chat/WelcomeCenterLayout/index.test.tsx` |

验证层级：**单元**验证策略/快照/配置；**集成**使用真实仓储、Agent 装配或 FastAPI TestClient，但模型及外部服务由替身代替；**组件**为 Vitest/jsdom；**本地多进程**为两个独立 Python 进程竞争同一本地 JSON 仓储。未标浏览器的行均不能据此宣称真实浏览器通过。

## 决策覆盖矩阵

| 决策 | 实际测试节点 | 验证层级与覆盖边界 |
| --- | --- | --- |
| Q1 Source 权限 | `S::test_expert_main_source_isolation_and_restore_default`；`B::test_binding_api_checks_all_chat_scope_dimensions` | 配置/HTTP 集成；用户、Source、Profile 维度隔离。另跑 `S::TestSourceSystemConfigApi::test_non_manager_cannot_update_source_config`、`test_non_manager_cannot_access_current_source_config`、`test_manager_updates_source_config_with_audit_metadata` 三项现有权限节点全部通过。 |
| Q2 结构化选择 | `B::test_generic_api_cannot_inject_binding`；`B::test_binding_update_requires_revision_and_explicit_identity`；`H > saves immediately, retains saved selection while pending, and ignores duplicate clicks` | 单元/HTTP/组件；绑定仅经专用结构化 API。`A::test_body_mention_without_binding_never_prepares_an_expert` 实跑正文同名不建立绑定。 |
| Q3 持续接管 | `F > restores persistent binding and submits its revision without clearing selection`；`A::test_valid_message_registers_one_snapshot_before_start` | 组件/准入集成；选择保留且请求携带修订。未使用真实模型连续对话。 |
| Q4 专家能力边界 | `P::test_preparation_captures_identity_policy_and_strict_per_message_budget`；`P::test_undeclared_parent_mcp_is_not_inherited_by_expert_main`；`R::test_expert_main_toolkit_has_only_effectively_allowed_builtins`；`P::test_private_skill_runtime_snapshot_is_built_from_copied_private_root` | 单元/真实 Agent 装配；工具、私有 Skill/MCP、父策略交集。 |
| Q5 仅普通聊天 | `B::test_plan_transition_atomically_releases_binding_and_rejects_rebind`；`A::test_goal_resume_without_mode_flag_releases_binding`；`E > disables inline expert options while Goal Mode is enabled` | 仓储/准入/组件；Plan、Goal 排斥专家绑定。 |
| Q6 切换/默认退出 | `E > offers default Agent in persistent mode and keeps the selected expert on repeat click`；`H > saves immediately, retains saved selection while pending, and ignores duplicate clicks`；`B::test_release_revision_prevents_aba_and_stale_generic_updates` | 组件/仓储；选择和解除均使用修订控制。 |
| Q7 持久恢复 | `B::test_binding_compare_and_set_serializes_two_repository_instances`；`F > restores persistent binding and submits its revision without clearing selection` | 本地仓储重建/组件恢复；不等同真实服务重启、数据库或 NAS 验收。 |
| Q8 Chat 历史与压缩 | `R::test_expert_main_history_load_preserves_current_expert_prompt`；`C::test_compact_preserves_summary_and_respects_expert_memory_boundary`；`M::test_expert_chat_memory_restores_summary_and_commits_checkpoint`；`M::test_expert_automatic_compaction_archives_without_profile_summary` | 真实 ReMe Chat memory/checkpoint/MemoryCompactionHook 集成 + 模型替身；历史 summary 恢复、archive candidate commit、自动压缩且不排入 Profile summary。 |
| Q9 无 Profile 长期记忆 | `R::test_real_expert_agent_has_no_profile_role_memory_or_bootstrap`；`R::test_expert_main_finalize_never_prepares_profile_long_term_memory`；`C::test_expert_commands_do_not_read_profile_long_term_memory` | 真实 Agent 装配/命令集成；不调用外部模型。 |
| Q10 模型优先级 | `P::test_usable_expert_model_wins_without_provider_credentials`；`P::test_unresolvable_expert_model_keeps_current_chat_model` | 单元；可解析专家 slot 优先，否则聊天 slot；未验证真实 Provider 可用性。 |
| Q11 不得继续委派 | `P::test_preparation_inherited_policy_still_denies_delegation`；`R::test_expert_main_cannot_reenable_delegation_from_user_or_skill_intent`；`R::test_expert_main_tool_budget_and_policy_apply_to_main_identity` | 单元/守卫集成；专家 main 身份、Skill/user 意图均不能重新开启委派。 |
| Q12 严格预算交集 | `P::test_preparation_captures_identity_policy_and_strict_per_message_budget`；`P::test_admission_preparation_snapshots_global_timeout_limit`；`R::test_expert_main_hard_timeout_stops_a_silent_model` | 单元/异步运行时；turn/tool/timeout 取严，静默流也被超时中断。 |
| Q13 缺省关闭 | `S::test_expert_main_defaults_off`；`S::test_expert_main_normalizes_boolean_values`；`H > keeps legacy mode as a single-turn choice without a binding write` | 配置/组件；旧单条选择不写持久绑定。 |
| Q14 立即保存/下一条生效/失败不伪装 | `H > keeps the saved view when saving fails`；`H > does not let a late refresh replace a newer saved binding`；`H > isolates late saves when switching chats`；`A::test_approval_resumes_original_identity_after_selection_changed` | 组件/准入；CAS 保存、异步隔离、原审批身份不随新选择改变。`A::test_binding_switch_only_changes_the_next_message_lease` 验证运行中 A 不变且下一消息为 B。 |
| Q15 Plan/Goal 退出 | `F > releases the persistent binding atomically with entering %s`；`F > keeps the binding when entering %s fails`；`B::test_update_chat_returns_authoritative_released_binding` | 组件参数化 Plan/Goal + 仓储；同一更新解除绑定，失败保留状态。 |
| Q16 Source 关闭失效 | `B::test_disabled_binding_get_releases_binding_after_stale_unbound_read`；`B::test_binding_put_clears_delayed_save_after_source_disables`；`A::test_source_disabled_during_preparation_releases_and_cleans` | HTTP/准入竞态集成；进入、延迟保存、准备中关闭均覆盖。 |
| Q16a 重新打开不恢复旧绑定 | `A::test_disabled_mode_releases_without_executing_or_restoring` | 准入集成；关闭清 null 后重新开启仍为空。 |
| Q16b 关闭时拒绝并保留待发消息 | `A::test_http_rejection_publishes_no_user_turn_or_queue`；`H > synchronizes %s without losing the retained identity`；`F > restores text and attachment references on a send conflict and synchronizes the binding`；`W > restores rejected expert draft text and attachment references in the welcome composer` | HTTP/组件；409 不启动 turn，恢复文本/附件。未做真实上传服务或真实双页面浏览器验收。 |
| Q17 不可用阻止执行 | `P::test_invalid_current_definition_blocks_then_same_identity_can_recover[disabled/deleted/broken]`；`A::test_unavailable_expert_retains_binding_and_blocks`；`D::test_withdrawal_or_broken_mcp_never_reuses_existing_view` | 单元/准入；禁用、删除、损坏、撤回及坏私有依赖均有覆盖。 |
| Q18 最新本地版本/在途冻结 | `P::test_main_preparation_freezes_v1_and_next_message_uses_complete_v2`；`D::test_update_in_progress_cannot_mix_definition_and_new_dependencies`；`D::test_cross_version_race_rejects_old_copy_and_keeps_new_winner`；`D::test_mutated_cached_skill_is_not_used_with_original_definition` | 本地文件/并发单元；不向社区自动拉取更新。未验证真实分发服务/NAS。 |
| Q19 失败/停止后保留绑定并给原因 | `R::test_expert_main_hard_timeout_stops_a_silent_model`；`R::test_expert_main_query_cancellation_waits_for_snapshot_cleanup`；`R::test_expert_main_tags_terminal_output_before_history_save` | 异步运行时；超时终止原因、取消清理与终态身份。没有真实模型停止后再发消息的端到端测试；绑定保留还依赖准入与仓储无解除操作。 |
| Q20 直接流式/实际身份/无 SubAgent 记录 | `R::test_expert_main_agent_assembly_has_no_forced_subagent_or_profile_memory`；`R::test_expert_main_tags_terminal_output_before_history_save`；`I > shows persisted expert execution identity instead of the current agent label`；`I > shows direct response execution identity` | 装配/流式替身/组件；不强制 SubAgent，不由默认 Agent 再总结。真实浏览器停止/流式行为由浏览器报告单列。 |
| Q21 指令替换/公共规则保留 | `R::test_expert_main_replaces_profile_role_and_keeps_source_rules`；`R::test_real_expert_agent_has_no_profile_role_memory_or_bootstrap`；`P::test_parent_approval_and_network_constraints_are_retained` | 单元/真实 Agent 装配；角色文件不进入专家 prompt，Source/平台约束保留。 |
| Q22 每消息预算/重试共享 | `P::test_private_mcps_are_independent_and_cleanup_keeps_other_message`；`R::test_expert_main_reasoning_budget_cannot_reset_across_retry`；`R::test_expert_main_low_budget_approval_replay_counts_only_model_calls`；`R::test_expert_main_media_retry_consumes_another_model_turn` | 单元/模型替身；快照独立，自动重试与审批续接共用当前消息计数，可信工具 replay 不重复计数。 |
| Q23 主聊天交互审批 | `R::test_expert_main_ask_uses_main_approval_with_guard_disabled`；`R::test_expert_main_ask_preapproval_replays_without_a_new_request`；`R::test_expert_main_denied_approval_releases_original_snapshot`；`A::test_approval_without_id_resumes_fifo_original_snapshot` | 守卫/准入集成；Main 审批、FIFO 和原快照续接。跨进程限制见后文。 |
| Q24 多页面冲突与草稿保留 | `B::test_binding_cas_serializes_two_independent_local_processes`；`A::test_binding_change_during_snapshot_capture_rejects_and_cleans`；`H > synchronizes a conflicting view without retrying`；`F > restores text and attachment references on a send conflict and synchronizes the binding` | 本地多进程/准入/组件；CAS 一方拒绝、409 同步且不重试。真实双页面验收由浏览器报告单列。 |
| Q25 新建/显式重置 | `F > creates and immediately binds an empty chat before sending any message`；`A::test_explicit_reset_sets_trusted_marker_and_releases_binding[/new,/clear]`；`A::test_compact_and_forged_reset_marker_keep_expert_binding`；`A::test_reset_racing_binding_switch_returns_identity_conflict`；`C::test_expert_reset_does_not_summarize_into_profile` | 组件/准入/命令；新 Chat 初始无绑定，`/new`、`/clear` 清除并生成可信标记；伪造标记被去除，`/compact` 保留绑定；可信专家 reset 不写 Profile。 |
| Q26 同身份恢复/不能同名替代 | `P::test_invalid_current_definition_blocks_then_same_identity_can_recover`；`A::test_unavailable_expert_retains_binding_and_blocks`；`E > shows an unavailable bound identity even when filtered from the selectable list`；`A::test_same_identity_recovers_but_same_name_replacement_cannot_take_over` | 真实本地专家仓储 + 准入/组件；disabled 原 ID enable 后可执行，删除后创建并 enable 同名新 ID 仍拒绝旧绑定。 |

## 已执行命令与结果

所有 Python 命令在 worktree 根目录使用 `PYTHONPATH=src venv/bin/python`，防止共享 editable venv 导入主工作区代码。以下是完成时的独立执行证据，不将不同阶段计数直接相加。

1. 原运行时回归范围：

```sh
PYTHONPATH=src venv/bin/python -m pytest \
  tests/unit/app/test_expert_main_runtime.py \
  tests/unit/agents/test_tool_guard_hook_runtime.py \
  tests/unit/app/test_runner_session.py \
  tests/unit/app/test_console_chat_system_prompt_injections.py \
  tests/unit/app/test_event_loop_request_preparation.py \
  tests/unit/app/test_query_runtime_skill_diagnostics.py -q --tb=short
```

结果：**131 passed**（5.71 秒；异步 cleanup 改造前）。包含专家策略、预算、审批、Prompt/历史恢复和既有普通聊天回归，不能替代完整后端测试。

2. 异步 cleanup 扩大范围：上述六文件加 `tests/unit/routers/test_console_chat_expert_main.py` 和 `tests/unit/routers/test_console_chat_stream.py`。结果：**203 passed**（7.72 秒）。新增实际节点 `R::test_expert_main_cleanup_runs_on_runtime_worker[execution/pending/approval]`、`R::test_expert_main_cancelled_cleanup_waits_for_worker_capacity`、`R::test_expert_main_query_cancellation_waits_for_snapshot_cleanup`：断言不在事件循环线程执行、worker 容量满时取消不丢清理、query 重复取消后仍等清理完成。Registry 状态先同步移除，生产 cleanup 边界均 await worker 清理。

3. 专家功能集中范围：

```sh
PYTHONPATH=src venv/bin/python -m pytest \
  tests/unit/app/test_expert_main_binding.py \
  tests/unit/app/test_expert_main_preparation.py \
  tests/unit/app/test_expert_main_runtime.py \
  tests/unit/app/test_expert_main_commands.py \
  tests/unit/subagents/test_expert_main_dependency_versions.py \
  tests/unit/routers/test_console_chat_expert_main.py -q --tb=short
```

结果：**108 passed**（2.87 秒）。包含本地独立进程 CAS。Source 专家开关子集另跑 `PYTHONPATH=src venv/bin/python -m pytest tests/unit/app/test_source_system_config.py -k expert_main -q --tb=short`：**7 passed、107 deselected**（1.10 秒）；上文 Q1 三项 Source API 权限节点定向执行 **3 passed**（0.85 秒）。

4. 完整 SubAgent 基线比较：`PYTHONPATH=src venv/bin/python -m pytest tests/unit/subagents -q --tb=no`。未修改主工作区：**57 failed, 303 passed**；worktree 在修正 `_summarizing` 对 `__new__` fixture 缺少 `_request_context` 的兼容读取后：**57 failed, 315 passed**。逐项提取 `FAILED` node ID 作集合比较：新增失败 `[]`，基线独有失败 `[]`，**57 项失败名单完全相同**，而非仅总数相同。排序 node ID 逐行加末尾换行所得 SHA-256 均为 `56b330f766ff87bd1d26385b1ba561e0e3f64d6ddf116c21cdc60569af8a27b2`。日志分别为 `/tmp/expert-main-baseline-subagents.log`、`/tmp/expert-main-subagents-worktree.log`。这次全量比较发生在异步 cleanup 与后续记忆补强之前，之后的验证范围如上。

5. 独立前端验证：

- `npm run test:run --` 后跟 H、E、I、W、`useChatRequest.test.tsx`、`chat.expertBinding.test.ts` 六文件：**79 passed**（早期版本）。
- 同范围再加 F：**123 passed、2 failed**；两个失败均为既有上下文徽标测试，在未修改主工作区对相同测试名再次执行得到 **2 failed、34 skipped**，错误一致。名称：`resolves the backend chat id and renders context usage in both composer prefixes`、`does not show the previous active chat usage while a route chat is unresolved`。根目录日志：`/tmp/expert-main-context-badge-root.log`。
- 最后 Welcome 草稿 metadata 修复后，H + W：**39 passed**（5.62 秒）。`W > clears restored interaction metadata when editing a rejected draft` 防止恢复的 Plan 交互参数污染用户改写的普通消息。
- persisted restoreDraft 最后只读复核后，独立执行 W + F，过滤 `restor|conflict|asynchronously prepared|server accepts`：**10 passed、67 skipped**（4.71 秒）；覆盖挂载后恢复、旧提交完成不清除新恢复草稿、冲突文本/附件及跨 Chat 异步取消。
- 前端实施者最新另报告十文件 **189 passed、2 skipped**、TypeScript、格式检查通过；本报告不将此等同于本审查者逐项重跑或真实浏览器验收。

6. 准入矩阵补测：只修改 A 测试文件，完整文件 **25 passed**（1.48 秒）；新增正文提及、同 ID 恢复/不同 ID 同名拒绝、compact/伪造 reset、new/clear 可信 reset、运行中 A 与下一消息 B 各节点，未调用真实模型。

7. Q8 与命令/准入最新集成：`PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_expert_main_memory.py tests/unit/app/test_expert_main_commands.py tests/unit/app/test_expert_main_runtime.py tests/unit/routers/test_console_chat_expert_main.py -q --tb=short`：**64 passed**（2.58 秒）。该次已包括新的 Chat-only memory facade、自动压缩和上文准入补测。

8. 准入取消与删除竞态：先复现取消后 worker 返回的 prepared 无人清理、关闭开关 reconcile 的 KeyError 外漏；修复后运行 A、B、R、M、C 加 `test_console_chat_stream.py` 六文件 **139 passed**（4.53 秒）。新增 `A::test_cancelled_admission_cleans_preparation_after_worker_returns`、`A::test_cancelled_admission_cleans_snapshot_during_revalidation`、`A::test_disabled_admission_delete_race_returns_404[before/after_prepare × release/reload]`：持有 worker 任务直到结果，注册前任何退出回收 snapshot，删除竞态返回 404。

9. 格式检查：对 cleanup 六个改动文件执行 `venv/bin/python -m black --target-version py312 --line-length 79 ...`，并执行 `git diff --check`，均通过。

## 审批租约与环境限制

- Chat 绑定本身保存在服务端仓储，可重建仓储实例读取；**pending 专家执行 lease 当前是进程内状态**。服务重启或审批请求落到其他进程，原冻结执行不可恢复时，`A::test_approval_without_snapshot_never_reprepares[/approve,/deny approval-original]` 验证返回 HTTP 409、`expert_unavailable`、reason `expert_execution_unavailable`，不临时准备新专家配置执行旧工具。`H > explains a lost approval snapshot without blaming the bound expert` 验证明确提示重新发起任务。这是安全拒绝，不能写成跨进程审批恢复已支持。
- 本地两进程 CAS 不代表 Kubernetes 多副本、真实 Linux 3.15、NAS 锁、共享卷故障或 MySQL/Redis 部署均通过。上述真实部署环境未验收。
- 既有共有 I/O seam 仍存在：`command_dispatch._run_conversation_command` 同步创建命令 Chat memory，`MemoryCompactionHook.__call__` 同步加载配置；本次未重构这些普通/专家共用入口，不能宣称所有文件 I/O 都已移出事件循环。
- 模型、Provider 和 MCP 交互主要用替身或本地配置：没有真实收费模型调用、真实网络工具审批、真实社区服务分发/撤回验收。
- 浏览器执行者在隔离 Chromium + 本地 Vite + 全 API mock 环境中已验证“选择后发送前 PUT”及整页刷新恢复；409 首消息最初发现可见 welcome 草稿为空、文本/文件仅在隐藏普通 sender 中恢复；加入 owner 绑定的 persisted restoreDraft 后，执行者已复验可见 Welcome 原文 + 31B 附件 chip、编辑后快捷菜单重渲染保留、带原文件引用和 revision 2 重发、再次 revision 3 冲突仍保留，**该 mock 浏览器路径修复后通过**。详见 `2026-10-27-expert-as-main-browser-validation.md`，不能用组件绿测替代。
- 没有在本报告中宣称完整浏览器 QA。真正页面操作、窄屏/键盘、流式停止、审批、双页面冲突及上传重发应以独立浏览器报告的实际步骤与结果为准。

## Parent 最终冻结复验

最终后端 23 文件 502 passed（10.21 秒）；完整 SubAgent 315 passed/57 failed（17.54 秒），再次与干净基线逐项比对失败 node，新增与消失集合均为空。前端 12 文件 223 passed/2 baseline skipped；SystemConfig 与干净基线在 15 秒超时下均24 passed/1同名stale-draft失败。完整变更文件 pre-commit 所有适用 hook 通过。以上是后续取消修复、类型和格式冻结后的结果，取代前面阶段结果作为最终状态；详细命令及日志见测试报告。
