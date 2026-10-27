# SubAgent 测试报告

日期：2026-10-27。基线：`ab5d8ad12`，功能提交截止：`740db02db`。使用项目虚拟环境及现有 Console node_modules；未新增依赖。

## 结果

| 范围 | 结果 |
| --- | --- |
| 后端完整相关回归 | 565 passed / 69 failed；失败用例集合与未改动基线完全相同，无新增失败 |
| Goal、Runner、Chat API、规划工具、数据库事务、事件循环专项 | 199 passed |
| Chat 归属、依赖视图、显式专家、社区专家、异步准备专项 | 69 passed |
| 前端 registry、Goal API、messageMeta、Plan 状态、计划交互卡片五文件 | 116 passed |
| 系统配置页新增专家发现保存/重读/Source 切换及权限专项（同时复验 prompt 保存） | 3 passed / 22 skipped |
| 前端七文件完整相关回归 | 172 passed / 5 failed；下述五项在未改动基线复现 |
| TypeScript `pnpm --dir console run typecheck` | exit 0 |
| 变更文件 pre-commit 与实际提交 hooks | AST、编码、密钥、空白、trailing comma、mypy、Black79、flake8、pylint、涉及前端时 tsc 全部通过 |
| Git diff / GitNexus detect_changes | diff --check 通过；每次提交前检查范围；Task2 LOW，Task3共享接口 HIGH 并已审查 |

各专项存在重叠，不能相加当作独立总数。未运行仓库全部测试；此报告也不声明 ESLint 全仓无告警。Chat index.test 存在原有 any/require/unused 问题，未进行无关重构。

## 可复现命令

在 feature worktree 使用 `../../venv/bin/python`；合并后在仓库根目录使用 `venv/bin/python`。

```bash
venv/bin/python -m pytest tests/unit/subagents tests/unit/app/goals tests/unit/app/test_source_system_config.py tests/unit/app/test_runner_goal_lifecycle.py tests/unit/app/test_runner_selected_expert_dependency_views.py tests/unit/app/test_runner_plan_mode_state.py tests/unit/app/test_chat_api_update.py tests/unit/agents/tools/test_planning.py tests/unit/agents/test_subagent_research_phase.py tests/unit/app/test_event_loop_request_preparation.py -q

venv/bin/python -m pytest tests/unit/app/goals tests/unit/app/test_runner_goal_lifecycle.py tests/unit/app/test_runner_plan_mode_state.py tests/unit/app/test_chat_api_update.py tests/unit/agents/tools/test_planning.py tests/unit/database/test_connection.py tests/unit/app/test_event_loop_request_preparation.py -q

pnpm --dir console test:run src/pages/SystemConfigPage/index.test.tsx src/pages/SystemConfigPage/registry.test.ts src/api/modules/chat.goalIntent.test.ts src/pages/Chat/index.test.tsx src/pages/Chat/messageMeta.test.ts src/pages/Chat/planMode.test.tsx src/pages/Chat/components/PlanInteractionCards.test.tsx
pnpm --dir console run typecheck
```

## 基线失败说明

后端基线从 `git archive ab5d8ad12` 的未修改副本验证：69 failed / 226 passed。当前 69 项失败以移除内置 plan-researcher 后旧测试仍引用该定义为主，另含旧工具集合断言。不为通过旧测试恢复已移除的产品行为。比较使用规范化测试 node ID，结果新增集合与消失集合均为空。

本轮因 wait 必须校验 session/Chat 而产生的三个 serializer mock 失配已迁移为授权后的持久记录读取测试；保留原序列化断言，未恢复无 session 访问。

前端完整回归五项失败：

1. Chat：resolves the backend chat id and renders context usage in both composer prefixes。
2. Chat：does not show the previous active chat usage while a route chat is unresolved。
3. SystemConfig：saves system prompt injections，完整文件执行时 5 秒超时；单独专项通过。
4. SystemConfig：saves model call policy overrides and restores inheritance，5 秒超时。
5. SystemConfig：clears stale draft and blocks save when the next source load fails，找不到既有错误文案。

前两项及后三项分别在未修改基线复验。SystemConfig 整文件基线为 21 passed / 3 failed，当前为 22 passed / 3 failed；增加的专家开关回归通过。

## 红绿与审查证据

- 社区专家同 Chat/同专家首次并发：修复前一方失败，修复后两次进入 supervisor 并复用已验证视图。
- 无意图普通 Chat 保留记录扫描：线程断言修复前两项失败，移入 worker 后通过；刷新移除预读缓存也有回归。
- Goal 旧快照覆盖 Steering 授权：review probe 从 true→false，修复后 true→true；内存与 MySQL 同事务锁读/合并覆盖。
- /plan 清理草拟授权、客户端过滤内部 meta、初始授权跨澄清/重启、Source 每轮刷新、prepare 异常和取消释放 turn 均有专项。
- 独立 reviewer 对意图/目录、Chat runtime、Goal runtime 分别审查，最终无阻塞 P0/P1/P2。

## 环境与验收边界

测试为本地单元/集成契约验证，数据库事务使用测试连接或替身；未连接生产 MySQL、未进行 Kubernetes 多实例与共享 NAS 的真实发布验收，未进行真实模型端到端调用。部署前可在预发补上述环境验证。

本次会话原始日志保留于 `/private/tmp/subagent-intent-*`，重要结果已归档在本报告；临时目录不属于长期发布制品。
