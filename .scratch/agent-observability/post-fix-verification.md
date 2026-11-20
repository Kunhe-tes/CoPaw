# 复核问题修复与验证记录

- 日期：2026-11-20
- 范围：`review-fix-plan.md` 的批次 0–5；批次 6 为本文档与样例/报告对齐
- 结论：5 个 P0 与主要 P1 已在代码层修复并有回归测试；真实 MySQL、真实 worker 子进程、多 Pod 与采集链路仍未验证

## 提交索引

| 批次 | Commit | 内容 |
|---|---|---|
| 0 | `5b6914434` | `delay_ms` 进入 emitter 白名单 |
| 0 | `81b1e1ce3` | 子代理启动前初始化观测状态变量（P0-4） |
| 0 | `a3138b4f3` | 先停生产者再排空 emitter |
| 0 | `96f18a3e0` | cron 过期日志改走 stderr |
| 0 | `c1581f0cf` | 流式空输出重试补发 retry 事件 |
| 0 | `851bb167d` | 媒体回退复用 step 索引 |
| 1 | `2ac9519b1` | 审批决议要求调用方身份（P0-3） |
| 1 | `7079ec56b` | 错误审批 ID 不再回落 FIFO |
| 2 | `d88b2204e` | inbox 逐行隔离与时间字段前置校验（P0-2） |
| 3 | `937144aeb` | worker JSONL 经父进程 emitter 回传（P0-1） |
| 4 | `31574fcd0` | Agent operation Span（P0-5） |
| 4 | `479b4426e` | Guard 状态、短路事实与工具身份修正 |
| 5 | `d90943a96` | service unit / quality / tenant / 聚合列 / 槽位 / 终态 |

## 验证命令与结果

```bash
venv/bin/python -m pytest tests/unit/observability -q
# 138 passed

venv/bin/python -m pytest tests/unit/subagents tests/unit/observability -q
# 528 passed

venv/bin/python -m pytest tests/unit/agents tests/unit/subagents tests/unit/observability -q
# 1810 passed, 13 failed（失败集合与干净 HEAD 完全一致）

venv/bin/python -m pytest tests/unit/observability \
  tests/unit/app/conversation_storage \
  tests/unit/app/test_approval_service.py -q
# 1755 passed

venv/bin/python -m pytest tests/unit/app/conversation_storage \
  tests/unit/subagents -q
# 2053 passed（含真实 worker stdout 转发测试）

venv/bin/python -m pytest \
  tests/integrated/observability/test_review_fixes_mysql.py -q
# 5 skipped（未设置 SWE_AGENTOBS_TEST_DB_HOST）

pre-commit run --files <changed files>
# ast / trailing-comma / mypy / black / flake8 / pylint 全部通过
```

`tests/unit/agents` 的 13 个既有失败（skill pool 覆盖、TLS 回退、model factory 快照、tool guard hook 等）已在干净 HEAD 上复现，与本轮改动无关。

## 未验证项

- **MySQL / TDSQL 集成**：已连接 MySQL 8.0.46 的一次性 `_test` 库执行。新增的 `test_review_fixes_mysql.py` 5 passed；既有目录在补齐 `effective_tenant_id` 后重跑，结果以最终一轮为准。
- **真实 worker 子进程链路**：已由 `test_worker_stdout_events_are_forwarded_by_supervisor` 覆盖——真实启动 `worker.run_worker`，父进程读线程转发 stdout，并断言收到 `span.ended`。
- **多 Pod / 采集链路**：`observer.health` 仍无生产者，丢弃计数无法跨 Pod 汇总。
- **网关 header 信任**：审批身份校验依赖 `X-User-Id`；网关是否保证注入与不可伪造尚未验证。
- **Console / Chromium 108 / 360 / `hideMenu=true`**：未验证，维持原有暂停状态。

## 已知未完成 / 有意保留

- **service unit 历史数据**：该观测功能尚未投产，库中没有 `service_unit_key='swe'` 的历史数据，因此不需要双读或回填；后续投产前若已有数据，再补迁移脚本。
- **SQL 审批等待判定**：`IndexedQuery.finish` 查询审批服务真实状态，`query_waiting_for_approval` 同样以服务记录为准；Stop/Goal/GC 终结审批时补发 `run.ended(cancelled)`。未注册 deferred settlement。
- **DB 行级错误隔离**：`DatabaseSession._run` 对任何异常都会丢弃会话，因此"坏行回滚后标记 rejected"只对 Python 侧错误有效。当前校验/投影已覆盖已知输入，真实 MySQL 未复现毒丸；如未来 schema 漂移，需要引入"新连接隔离坏行"的兜底。
- **`observer.health` 生产者**：存在“队列满时 health 也被丢”的反馈循环，需单独设计。
- **非 ASCII 身份**：按决策直接丢弃事件，不转义、不放宽；契约文档需明确这是预期行为。
- **聚合列写放大**：每个 `span.ended` 都会触发一次 Run 聚合 UPDATE，后续可合并到现有 LLM 聚合语句。
