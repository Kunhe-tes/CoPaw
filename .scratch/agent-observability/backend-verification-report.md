# Independent Agent Observability Backend Verification

Date: 2026-11-19

## Verified

- Independent metadata event core, bounded JSONL projection, Run/Attempt/Span lifecycle, model/request-attempt metrics, Tool/Guard facts, SubAgent ownership, Assets, Events/Links, Performance, Run Explorer, ancestor paging, and business population APIs.
- NAS Evidence API for online and archive occurrences, duplicate message IDs, pending/available pairing, compacted content, signed continuation cursors, `not_saved` model input facts, Source authorization, and post-delete `unavailable` behavior.
- SQL approval continuation for deny, approve, timeout, consecutive approvals, external submission, scope mismatch, audit replay repair, and deferred cancellation settlement.
- Search-to-ancestor navigation: an authorized search hit returns the same Span followed by its parent path.

## Evidence

- `tests/integrated/observability/test_mysql_pipeline.py`: 12 passed on a fresh isolated MySQL `_test` schema after installing the current observability DDL.
- `tests/integrated/conversation_storage/test_observability_evidence_mysql.py`: 6 passed, including archive deletion invalidation and `model_input/not_saved` evidence.
- `tests/integrated/conversation_storage/test_approval_observability_sql_mysql.py`: 8 passed, including deferred cancellation settlement.
- `tests/integrated/conversation_storage/test_business_population_mysql.py`: real MySQL business Turn plus persisted SubAgent population contract passed.
- Observability, model, Tool, Query, Runner, approval and lifecycle focused suites passed; the combined recent regression set reached 120 passed.
- Targeted Python pre-commit hooks and `git diff --check` passed.

Each acceptance run used a disposable schema ending in `_test`; schemas were removed and checked through `information_schema` after completion. No business schema was used.

## Remaining

- Console UI and browser acceptance, including Chromium 108/360 and `hideMenu=true`, remain paused by the user instruction.
- Real external channel, Router authorization, tool side effects, deployment collector, and process-restart audit recovery remain outside the verified scope.
- The production code has no Tool automatic retry/recovery state machine, so no fabricated Tool retry facts were added.

## 2026-11-20 复核后修复状态

独立复核发现的 5 个 P0 与主要 P1 已修复并提交，详见
[post-fix-verification.md](post-fix-verification.md)。

- 新增回归测试覆盖：子代理变量初始化、inbox 逐行隔离、审批跨用户拒绝、worker 事件转发、Agent Span、Guard 短路事实、service unit / tenant / quality / 聚合列 / 槽位语义。
- `events.example.jsonl` 已由真实 emitter 重新生成，并通过 `_validate_payload`；新增契约测试防止再次漂移。
- 本轮验证仍限于纯单测；MySQL 集成、真实 worker 子进程、多 Pod 与采集链路未复证，原文 "12/6/8 passed" 的环境前提（`SWE_AGENTOBS_TEST_DB_HOST`）保持不变。
