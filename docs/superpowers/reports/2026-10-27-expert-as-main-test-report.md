# Expert-as-Main 测试报告

日期：2026-10-27。基线：`9873823c42d83e0e68304cba965bba6edcc13664`。所有 Python 测试在 feature worktree 使用 `PYTHONPATH=src venv/bin/python -m pytest`，避免共享 editable venv 导入原主工作区代码。

## 验证结果

| 范围 | 实际结果 |
| --- | --- |
| 后端 23 文件合并定向回归 | 502 passed，10.21 秒；覆盖配置、绑定/API/仓储、准备/依赖、运行时/审批/取消、命令/记忆、Console/重连、Runner/Goal/事件循环 |
| 完整 SubAgent 套件 | feature 315 passed / 57 failed；干净基线 303 passed / 57 failed；失败节点集合完全一致，新增失败为空 |
| 前端 12 文件定向回归 | 223 passed / 2 skipped，12.64 秒；跳过两项已在基线复现的上下文徽标测试，未将其计为通过 |
| SystemConfig 整文件（15 秒测试超时） | feature 与干净基线均 24 passed / 1 failed；相同失败为 stale draft 错误提示断言 |
| TypeScript | `npm run typecheck` exit 0 |
| 生产构建 | `npm run build` exit 0，17.94 秒；现有 chunk 大小警告仍在 |
| 浏览器 | 隔离 Chromium + Vite + 全 API mock；立即保存、刷新恢复、首条 409 可见草稿/附件、编辑后重发已验证，其他实际步骤见独立报告 |

以上范围存在重叠，不相加作为独立总数。未运行整个仓库全量测试，不宣称全仓无失败。最终提交前类型/静态检查及回归复跑结果追加于下方。

## 可复现命令

后端合并范围：

```sh
PYTHONPATH=src venv/bin/python -m pytest \
  tests/unit/app/test_source_system_config.py \
  tests/unit/app/test_source_system_config_agent_runtime.py \
  tests/unit/app/test_expert_main_binding.py \
  tests/unit/app/test_chat_json_repo.py \
  tests/unit/app/test_chat_api_update.py \
  tests/unit/app/test_expert_main_preparation.py \
  tests/unit/subagents/test_expert_main_dependency_versions.py \
  tests/unit/app/test_expert_main_runtime.py \
  tests/unit/app/test_expert_main_commands.py \
  tests/unit/agents/test_expert_main_memory.py \
  tests/unit/routers/test_console_chat_expert_main.py \
  tests/unit/routers/test_console_chat_stream.py \
  tests/unit/routers/test_console_chat_reconnect.py \
  tests/unit/agents/test_tool_guard_hook_runtime.py \
  tests/unit/agents/test_checkpoint_commands.py \
  tests/unit/agents/test_memory_compaction_archive.py \
  tests/unit/agents/test_memory_compaction_checkpoint.py \
  tests/unit/app/test_runner_session.py \
  tests/unit/app/test_console_chat_system_prompt_injections.py \
  tests/unit/app/test_event_loop_request_preparation.py \
  tests/unit/app/test_query_runtime_skill_diagnostics.py \
  tests/unit/app/test_runner_goal_lifecycle.py \
  tests/unit/app/test_runner_selected_expert_dependency_views.py -q

PYTHONPATH=src venv/bin/python -m pytest tests/unit/subagents -q
```

前端在 `console/` 执行：

```sh
npm run test:run -- \
  src/api/modules/chat.expertBinding.test.ts \
  src/pages/Chat/useExpertBinding.test.tsx \
  src/pages/Chat/expertSelection.test.ts \
  src/pages/Chat/index.test.tsx \
  src/pages/Chat/ExpertSelector/index.test.tsx \
  src/pages/Chat/planMode.test.tsx \
  src/pages/Chat/components/runtimeMessageHeader.test.tsx \
  src/pages/Chat/components/SubAgentRunMonitor/index.test.tsx \
  src/pages/SystemConfigPage/registry.test.ts \
  src/pages/SystemConfigPage/workbench.test.ts \
  src/components/agentscope-chat/AgentScopeRuntimeWebUI/core/Chat/hooks/useChatRequest.test.tsx \
  src/components/agentscope-chat/WelcomeCenterLayout/index.test.tsx \
  -t '^(?!.*resolves the backend chat id and renders context usage|.*does not show the previous active chat usage).*'
npm run test:run -- src/pages/SystemConfigPage/index.test.tsx --testTimeout=15000
npm run typecheck
npm run build
```

## 失败基线与红绿证据

后端干净基线位于 `/tmp/swe-expert-main-baseline`。完整 SubAgent 的 57 个失败主要引用已移除的内置 `plan-researcher` 或旧 toolkit 集合。逐行抽取 `FAILED` node ID，去掉错误正文并排序比较，新增集合和基线独有集合均为空；最终日志 `/tmp/expert-main-final-subagents.log` 与 `/tmp/expert-main-baseline-subagents.log`。没有为通过旧断言恢复已移除的行为。

前端两项上下文徽标测试：`resolves the backend chat id and renders context usage in both composer prefixes`、`does not show the previous active chat usage while a route chat is unresolved`，在原未改动工作区定向复现相同失败。SystemConfig 失败 `clears stale draft and blocks save when the next source load fails` 在 feature 与干净基线相同命令均复现。默认 5 秒超时的广范围前端运行曾出现更多 timeout 与 FileManager 失败（10 failed / 595 passed），不能将这十项全部声称已逐项基线复现；定向结果及上述一致比较单列。

新增行为的失败到通过证据包括：绑定 CAS/旧写保护，私有依赖一致性，专家 Bootstrap 隔离，预算审批 replay，自动压缩且不写 Profile，`/new` 不先由前端丢失专家 reset 身份，以及准备任务被取消后的快照回收。最后的浏览器 409 probe 实际发现可见 Welcome 空而隐藏 sender 有草稿；修复为当前 owner 持久 restoreDraft 后，真实浏览器验证可见文本、31B 附件芯片及重发 payload/revision，不能用组件测试代替该证据。详细节点见覆盖矩阵。

## 审查、提交与环境边界

独立 agent 审查后回归，提交前执行 GitNexus `detect_changes`（指定 worktree）核对范围；静态索引部分新符号为 UNKNOWN、存在重复 UID，不能据此宣称零影响。完整 pre-commit 使用显式 `--files` 检查，避免默认提交 hook 自动 stash 并行工作区造成错误；修复新增 mypy/statement-limit 后重跑。提交使用已单独验证结果并禁用自动 hooks，避免再度 stash。

绑定 CAS 测试使用两个独立 Python 子进程和本地文件锁；不代表真实 NAS/Kubernetes/MySQL/Redis 已通过。pending 审批执行 snapshot 为进程内租约，跨进程无法恢复时验证安全 409 拒绝，不重新准备旧调用。未调用真实收费模型、真实审批网络工具或社区分发服务。共享命令与压缩 hook 中既有同步配置 I/O 未在本次通用重构。

## 最终提交前复验

- 最终后端 23 文件复跑：**502 passed / 0 failed，10.21 秒**，包括准备取消、revalidation 取消、并发删除与 Chat memory 补强。
- 最终完整 SubAgent：**315 passed / 57 failed，17.54 秒**，再次逐项比较干净基线，新增失败 `[]`，消失失败 `[]`。
- 前端 12 文件：**223 passed / 2 baseline skipped**；SystemConfig 15 秒超时两边均 **24 passed / 1 同名失败**。TypeScript 和 build exit 0。
- 完整功能变更文件显式 pre-commit：AST、docstring、编码、private-key、空白、tsc、trailing comma、mypy、Black79、flake8、pylint **全部通过**，日志 `/tmp/expert-main-precommit-final.log`。首次执行发现并修复了新增 lease 类型、准入 statement 数量及测试资源生命周期说明；formatter 变更均在最终后端复跑前冻结。
- 代码提交：`0a1f18390` 配置、`1a30ed216` 原子绑定、`b785d529f` 快照、`6d9258a3b` 执行链、`52e1ed45b` 前端。提交前各自执行 detect_changes，后两次风险为 HIGH 与 LOW，范围已核对。
- 独立 frontend reviewer 对最新持久草稿补丁结论无阻塞，10 个相关定向用例通过；隔离 Chromium 409 可见恢复及再次发送通过。

配套材料：[功能报告](2026-10-27-expert-as-main-functionality-report.md)、[Q1–Q26 覆盖矩阵](2026-10-27-expert-as-main-coverage.md)、[浏览器报告](2026-10-27-expert-as-main-browser-validation.md)。
