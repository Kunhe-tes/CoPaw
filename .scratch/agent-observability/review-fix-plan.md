# 可观测后端复核结论与修复方案

- 日期：2026-11-19
- 复核方式：4 个只读子代理分域独立核对源码 + 本地纯单测；未连接 MySQL，未修改业务代码
- 复核对象：`backend-verification-report.md` 与本轮审查结论（P0-1 ~ P0-5、P1 各组）

## 一、复核裁决总表

| 编号 | 原结论 | 裁决 | 备注 |
|---|---|---|---|
| P0-1 | 后台 SubAgent 观测事件写入 `/dev/null` | CONFIRMED | 子项归属需修正：`subagent_background.py:350` 是父进程 Span，不是 worker 侧 |
| P0-2 | 坏时间字段可让投影器永久卡住整批 | CONFIRMED | 比原结论更严重：32 行一个事务、无死信、无重试计数 |
| P0-3 | 审批 pending 路径不校验 user | CONFIRMED | 额外发现 HTTP `/approvals/{id}` 决议路径同样缺 user 校验 |
| P0-4 | 子代理启动工具新增 `UnboundLocalError` | CONFIRMED | 已在 venv 中无写入复现 |
| P0-5 | 生产代码没有 Agent operation Span | CONFIRMED | 全仓仅 6 处 Span 生产点，`span_type` 无 `Agent` |
| P1-A | SQL admission 未注册 deferred settlement | CONFIRMED | 另发现 `interrupted` 不在 `_TERMINAL_RUN_STATUS`，Run 连终态都不会写 |
| P1-B | `run.state` 同状态重复命中槽冲突 | CONFIRMED | 判定为丢弃，直到 `run.ended` 才纠正 |
| P1-C | `attempt_index` 静默覆盖旧行 | PARTIAL | 覆盖机制成立；未找到稳定触发的 index 复用路径，属潜在缺陷 |
| P1-D | stale/GC/Goal 取消不发 `approval.resolved` | PARTIAL | GC/Goal 确实不发；Stop 的 `supersede_pending_for_turn` 会发 |
| P1-E | `/approve` 错 ID 回落 daemon FIFO | CONFIRMED | 且该 FIFO 路径同样无 user 校验 |
| P1-F | `span_count`/`error_span_count`/`tool_calls` 从不写入 | CONFIRMED | 三列无任何 INSERT/UPDATE 来源 |
| P1-G | `service_unit_id` 三处取值不一致 | CONFIRMED | 比原结论严重：业务总体与观测 Run 恒定无法关联 |
| P1-H | Run 查询未绑定 tenant | CONFIRMED | `source` 非租户独占，manager 可跨租户读元数据 |
| P1-I | quality 词表 `observed` vs `complete` | CONFIRMED | 正常结束的 Span 全部落入 unknown |
| P1-J | 流式空输出重试不发 `model.retry_scheduled` | CONFIRMED | 仅此一条重试路径缺口 |
| P1-K | `needs_approval` 的 Guard Span 记成 `waiting_approval` | PARTIAL | 语义 bug 成立；"不在枚举内"只对设计稿成立，实现对它放行并落库 |
| P1-L | 短路分支无 Guard 事实、`tool_key` 未校验注册 | CONFIRMED | 四类短路（shell/policy/hook/policy-budget）均早于 Guard Span |
| P1-M | 媒体回退重试自增两次 `step_index` | CONFIRMED | 一次回退消耗两个 step，`agent_loops` 多计 1 |
| P1-N | `delay_ms` 不在白名单 | CONFIRMED | 重试退避永远为空 |
| P1-O | 停机先关 emitter 再停 manager/pool | CONFIRMED | 停机尾事件全部 `_dropped` |
| P1-P | 进程 stdout 非纯 JSONL | CONFIRMED | 污染点为 `src/swe/app/crons/auth_state.py:483` |
| P1-Q | `observer.health` 无生产者 | CONFIRMED | 多 Pod 丢弃计数无法落库 |
| P1-R | 非 ASCII/空格身份导致整条事件被丢 | CONFIRMED | 业务规则允许、观测 token 规则不允许，投影失败后整条丢弃 |

### 需要修正原文的结论

1. P0-1 中 `subagent_background.py:350` 的 Span 在**父进程**创建，其 `span.started` 可被采集；丢失的是 worker 的 `span.ended` 与 worker 内 LLM/Tool 事件。结论不变，归属需改。
2. P0-5 的枚举描述：`emitter.py:42-55` 已列出 `Agent`/`Approval`，缺的是**生产者**；审批走 `entity_kind="approval"` 实体事件而非 Span。
3. P1-K："`waiting_approval` 不在 Span 枚举内"仅对设计稿成立（`docs/superpowers/specs/2026-11-15-independent-agent-observability-design.md:58`）；`emitter.py:56-63`、`projector.py:206-217` 均放行，DB 列 `VARCHAR(32)` 无约束。
4. P1-D：并非所有取消都不发 `approval.resolved`，Stop 的 `supersede_pending_for_turn` 会发。
5. P1-C：`attempt_index` 覆盖是防护缺失，不是已证实的稳定故障。
6. 文档漂移：`issues/05-model-call-observability.md` 实际已有 2 项勾选（原文称 0 勾选）；原文漏列 `08-approval-run-continuation.md`（0/8 未勾）。

## 二、修复批次

批次按"风险 × 依赖"排序，同一批次内可并行。人日为粗略估计。

### 批次 0：零风险止血（约 0.5 人日）

| 编号 | 改动点 | 做法 | 验收 |
|---|---|---|---|
| 0-1 | `agents/tools/subagent_background.py:318-341` | 将 `observability_span`、`observability_span_transferred`、`supervisor_start_in_progress` 初始化移到 `try` 之前；删除 `:339-341` 重复赋值 | monkeypatch `_resolve_subagent_start_definition` 抛 `RuntimeError`，断言返回 `status=failed/reason=invalid_request` |
| 0-2 | `observability/emitter.py:19` | `_ALLOWED_KEYS` 增加 `delay_ms` | emitter 单测断言 `metrics.delay_ms` 保留 |
| 0-3 | `app/crons/auth_state.py:483` | `print` 改 `logger.debug` | 单测断言 stdout 无输出 |
| 0-4 | `app/_app.py:899-917` | 顺序改为：停 `MultiAgentManager` → 停租户工作区池 → `shutdown_default_emitter()` → 停 projector/DB | 停机顺序单测；断言停止期产生的 `span.ended` 未进 `_dropped` |
| 0-5 | `providers/retry_chat_model.py:663-682,716-722,770-784` | 流式空输出重试调用点补 `_notify_retry(...)`，与 `:535-543` 非流式路径对齐 | 流式空输出单测断言 `model.retry_scheduled` 出现 |
| 0-6 | `agents/react_agent.py:2183-2192` + `agents/tool_guard_mixin.py:2630-2632` | 媒体回退前保存 `_observability_step_index`，回退调用时恢复，不重新自增 | 一次 media fallback 后 `agent_loops` 不增加 |

批次 0 全部为局部改动，不改变业务返回语义，建议单独一个 commit（可按 0-1~0-6 拆成 6 个小 commit）。

### 批次 1：审批越权（安全，1~2 人日）

**根因**：scope 粒度是 `tenant+source`（`config/context.py:264-271`），不是 user；`PendingApproval.user_id` 字段存在但决议逻辑不使用。Console 恰好把 `X-Tenant-Id` 设成 `X-User-Id`（`console/src/api/authHeaders.ts:58-61`），掩盖了该缺陷。

| 编号 | 改动点 | 做法 |
|---|---|---|
| 1-1 | `runner/runner.py:786-801` `_select_pending_approval` | 增加 `user_id` 必传参数；`request_id` 分支与 `get_pending_by_session` 分支都校验 `pending.user_id`；同步 `admission.py:195`、`expert_main_admission.py` 调用点 |
| 1-2 | `runner/runner.py:3377-3392` pending 分支 | `resolve_request_once` 之前硬闸门比较 `pending.user_id == request.user_id`；不匹配直接返回 `(None, False, None)` |
| 1-3 | `app/runner_lifecycle.py:158-182` `restore_approval_context` | 拆分"身份不匹配"与"无观测上下文"两种 None，身份不匹配必须中止决议，不得只影响上报 |
| 1-4 | `app/approvals/service.py:372-407,478-487` | `get_request` 增加可选 `user_id`；`resolve_request_once` 锁内再校验 user，消除先读后改窗口 |
| 1-5 | `app/routers/approvals.py:139-214` + `app/approvals/external.py:490-620` | HTTP 决议路径比较调用方 user 与 `pending.user_id`；该路径当前直接以 `pending.user_id` 恢复执行 |
| 1-6 | `app/runner/daemon_commands.py:157-172` + `command_dispatch.py:402-406` | `/approve <id>` 指定 id 且 miss 时返回明确错误，禁止回落 FIFO；无 id 的 `/approve` 才允许 FIFO，并加 user 过滤 |

**验收**：新增 4 个用例——(a) 同 tenant+source 不同 user 选择 pending 返回 None；(b) HTTP `/approvals/{id}/approve` 跨用户被拒；(c) `/approve <错误ID>` 不批准任何 pending；(d) SQL 与非 SQL 两条 admission 路径均被拦截。

**风险**：若线上确有"同租户多用户共用审批"的用法，改动后会拒绝。按审批语义应属缺陷，但需在灰度前确认业务方无此依赖。

### 批次 2：投影器可靠性（P0-2，1~2 人日）

**根因**：`_project_one` 的 `try/except ValueError` 只包住 `_validate_payload`；`_store_event` 在 `else` 分支，异常穿出导致整批 32 行回滚；`RELEASE SAVEPOINT` 有、`ROLLBACK TO SAVEPOINT` 全仓不存在；inbox 无重试计数/死信。

| 编号 | 改动点 | 做法 |
|---|---|---|
| 2-1 | `projector.py:186-218` `_validate_lifecycle_values` | 对 `started_at`/`ended_at`/`attempt_started_at` 调 `_timestamp`（允许 None），错误码区分 `timestamp_missing`/`invalid_timestamp` |
| 2-2 | `projector.py:619-633` `_project_one` | 将 `_store_event` 纳入 `try`；异常时 `ROLLBACK TO SAVEPOINT agentobs_row`，该行置 `processing_state=2` + `reason_code`，批次继续 |
| 2-3 | `projector.py:586-601` `_run` | 区分"行级数据错误"（已置 2，继续）与"基础设施错误"（连接/超时，退避后重试），避免宽泛捕获吞掉断连 |
| 2-4 | `schema-draft.sql` inbox | 增加 `retry_count SMALLINT NOT NULL DEFAULT 0`（可选 `last_error VARCHAR(255)`）；超过阈值转死信，不再领取 |

**验收**：构造 3 行批次，第 2 行 `started_at="not-a-date"`——第 1、3 行提交成功，第 2 行 `processing_state=2`，下一轮不再领取；另测 DB 断连仍走重试而非标记坏行。

**风险**：`ROLLBACK TO SAVEPOINT` 需在 asyncmy 下验证保存点语义；schema 增列需与多实例部署协调（先加列、再发布）。

### 批次 3：子代理事件回传（P0-1，2~3 人日）

**根因**：`supervisor.py:958-969` 以 `stdout=subprocess.DEVNULL` 启动 worker；`emitter.py:165-172` 构造时快照 `sys.stdout`；worker 无独立 sink、无事件回传通道。

**方案对比**

| 方案 | 做法 | 评价 |
|---|---|---|
| A（推荐） | `stdout=PIPE` + 父进程 per-run 读线程 + `JsonlEmitter.emit_raw(bytes)` | 事件流进父进程同一队列/写线程，顺序与预算统一；改动集中在 supervisor/emitter |
| B | 去掉 `stdout=`，继承父进程 stdout | 最简单，但 worker 与父进程并发写同一 pipe，>4KiB 事件可能交错，第三方输出会污染 JSONL |
| C | 每 run 独立事件文件，部署侧采集 | 采集在项目范围外，且无清理策略，不建议本轮做 |

**已决策：采用方案 A（PIPE + 读线程 + `emit_raw`）**。以下为实施要点。

1. `supervisor.py:958-969`：`stdout=subprocess.PIPE`，`stderr` 保持 `{run_id}.stderr.log`。
2. `JsonlEmitter` 新增 `emit_raw(line: bytes)`：跳过白名单投影（worker 已投影），直接入同一 deque，由同一写线程落 stdout；队列满走现有 `_drop()` 计数。
3. 新增读线程：逐行读取，单行长度超过 24KiB 预算则丢弃并计数；非 JSON 行跳过并计数（不阻断）。
4. 生命周期：`_reap_one`/cancel/finally 中带超时 join 读线程并关闭 pipe 读端，避免 worker 退出后线程悬挂。
5. 兜底 end：仅当 `returncode != 0` 且读线程未见过该 `obs_span_id` 的 `span.ended` 时，由 launcher 补发 `span.ended(status="failed")` 并标 `terminal_fact_source="launcher"`。**不要**无条件在父侧补发——projector 的 upsert 会用后到事件覆盖 `status`（`projector.py:932-934`），会与 worker 真实结果冲突。
6. 不改 worker 侧埋点，不新增 worker 直连 MySQL 的路径（会引入第二套连接与权限面）。

**验收**：(a) 单测用假 Popen 产出 JSONL，断言行进入 emitter 队列；(b) 子进程级测试：真实启动 worker 最小命令，断言父进程输出中存在 `SubAgent/agent.execute` 的 `span.ended`；(c) 有 MySQL 时集成断言子代理 Span `ended_at` 非空。

### 批次 4：Agent operation Span 与埋点语义（P0-5，2 人日）

**4-A Agent Span**

- 落点：`app/runner/turn_lifecycle.py:144` 包住 `runtime.agent(turn_msgs)`（主 Agent 实际调用边界）。
- 防重复：`agents/react_agent.py:2537` `reply()` 是 runner/CLI 统一入口；若也在此开 Span，需用 contextvar 深度守卫保证一次执行只产生一个 `Agent` Span。建议只在 `turn_lifecycle` 开，`reply()` 不重复开。
- 语义：`span_type="Agent"`，operation 用注册标签（如 `agent.reply`），`kind="INTERNAL"`，携带 `step_index`；结束态覆盖 `succeeded/failed/cancelled`。
- 父链：`SpanHandle.__enter__` 已会把 `parent_obs_span_id` 设为自身，LLM/Tool 自动挂到 Agent 下；`agent_loops` 的 `COALESCE(parent_span_id, attempt_id)`（`projector.py:1027-1033`）无需改 SQL，分组自然正确。
- 不埋：命令短路、纯文本卡边界。
- 与 `SubAgent/agent.execute`：子代理已有对称 Span，不要把主 Agent Span 做成子代理 Span 的并列兄弟。

**4-B 埋点语义修正**

| 编号 | 改动点 | 做法 |
|---|---|---|
| 4-1 | `agents/tool_guard_mixin.py:1986-1994,2213-2219` | `agent_role=="subagent"` 且 `needs_approval` 时记 `rejected`，或让 `_should_require_approval()`（`:689-691`）对 subagent 返回 False；同步明确设计稿与实现的状态枚举 |
| 4-2 | `agents/tool_guard_mixin.py:1911-1934` | shell/policy/hook/policy-budget 四类短路各产生 Guard 事实（`reason_code` + `executor_kind`），不增加 Tool execution 计数 |
| 4-3 | `agents/tool_guard_mixin.py:440-446,2017-2020` | `tool_key` 与 `toolkit.tools` 注册表比对；未注册标 `executor_kind="unregistered"`，且不标 `asset_used(source="runtime_registered")` |

**验收**：主 Agent 一次执行产生且仅产生一个 `Agent` start/end；同一 Attempt 两次 Agent 调用时 `agent_loops==2`；SubAgent Guard 断言 `status=rejected`；policy/hook/shell 三条短路各产生一条 Guard 事实。

### 批次 5：存储与查询一致性（P1，2~3 人日）

| 编号 | 改动点 | 做法 |
|---|---|---|
| 5-1 | `observability/runner_lifecycle.py:107-108` + `query.py` 全部 `SWE_SERVICE_UNIT_ID` 读取 | 抽出唯一解析函数，统一优先 `CMB_CAAS_SERVICEUNITID`（`conversation_storage/identity.py:8`）；写入与查询共用；历史 `"swe"` 数据双读或一次性回填 |
| 5-2 | `store.py:176-204,393-411` + performance | `_run_where_clause`/`get_run`/样本查询增加必填 `tenant_key`（及可选 `agent_key`），取 `request.state.effective_tenant_id`；缺失 tenant 直接 403；admin 跨租户需显式列表 |
| 5-3 | `projector.py:1014-1036` 模式 | `span.ended` 后重算 `span_count`/`error_span_count`/`tool_calls`，与 `llm_calls` 合并为一条 UPDATE；明确"已观测非业务全量"口径与 Guard/SubAgent 是否计入 |
| 5-4 | `projector.py:789,879,979-987` vs `query.py:1514-1531` | **已决策（B+C）**：查询侧显式映射 `{observed→complete, complete→complete, partial→partial}`，其余→`unknown`；写入端不改、不迁移历史；同时补文档区分"观测完整度"与"分页完整性"两个同名词 |
| 5-5 | `projector.py:689-691,896-906` | 增加 `(run_id, attempt_index)` 查重，冲突返回 3，不静默 upsert 覆盖旧行 |
| 5-6 | `instrumentation.py:1108-1126` + `projector.py:655-677` | `run.state` 改为最新覆盖语义（`phase_key="state"` + 单调 `local_seq`），或按 append 语义处理，避免同状态第二次被丢 |
| 5-7 | `admission.py:45-56,123-130` + `runner_integration.py:283-338` | SQL 路径注册等价 deferred settlement；Stop 时清除 `_tool_guard_pending_info` 或传 `waiting_for_approval=False`；`_TERMINAL_RUN_STATUS`（`runner_lifecycle.py:25-32`）补 `interrupted` |
| 5-8 | `approvals/service.py:826-848,589-597` | GC/Goal 取消统一走"终结审批" helper，发 `approval.resolved`（decision=timeout/superseded） |

**验收**：Run 列表计数列非 NULL；Service Unit 取业务值时 Run 与业务 Turn 可关联；不同 tenant 列表互不可见；完整 Span 的 `sample_quality.status=="complete"`；Stop 后 Run 出现 `run.ended`。

### 批次 6：文档与验证（1 人日）

1. `.scratch/agent-observability/issues/`：按真实实现更新 03/04/05/07/08/10–15 的勾选状态；`ticket-breakdown.md` 同步状态。
2. `events.example.jsonl`：删除或替换白名单外字段（`summary_quality`、`evidence_refs`、`error_phase`、`metrics.llm_calls`），或显式标注为"目标契约样例，非当前实现"。
3. `backend-verification-report.md`：标注 MySQL 集成测试以 `SWE_AGENTOBS_TEST_DB_HOST` 为前提、缺省整体 skip；补充本轮未验证项。
4. 新增修复后验收清单：纯单测 + MySQL 集成 + 真实 worker 子进程链路 + 停机顺序。

## 三、执行顺序与依赖

```text
批次 0（止血）──────────────┐
批次 1（审批越权）──────────┤ 相互独立
批次 2（投影器）────────────┘
        ↓
批次 3（worker 回传）── 依赖批次 2 的行级隔离提供安全网
        ↓
批次 4（Agent Span）── 4-1/4-2/4-3 可先于 4-A 独立合入
        ↓
批次 5（存储/查询）── 5-1/5-2 可与批次 3/4 并行
        ↓
批次 6（文档与验证）
```

- 批次 0、1、2 无互相依赖，可并行开发。
- 批次 5-7（SQL deferred settlement）与批次 1 共享审批链路，建议同一个人跟进，避免语义分叉。
- 5-3 聚合列依赖 4-A 的 Span 树形态确定口径，建议在批次 4 之后做。

## 四、决策记录（2026-11-19 已确认）

### D-1 worker 事件回传：采用方案 A

- 机制：`stdout=PIPE` + 每 worker 一个 daemon 读线程 + `JsonlEmitter.emit_raw(bytes)` 入父进程同一队列/写线程。
- 放弃 B（继承 stdout）：`PIPE_BUF` 仅 4096 字节，事件上限 24KiB，父子并发写会撕裂行。
- 放弃 C（独立文件 sink）：采集器在项目范围外，且无清理策略。
- 约束：读线程必须持续 drain，不得因父队列满而停读（否则 worker 写 pipe 阻塞）；停机先 reap 再关 emitter；兜底 end 仅在 `returncode != 0` 且未见 end 时补发。
- 待补验证：真实 worker 子进程链路测试（父进程输出中存在 `SubAgent/agent.execute` 的 `span.ended`）。

### D-2 quality 词表：采用 B+C

- 查询侧显式映射：`{"observed": "complete", "complete": "complete", "partial": "partial"}`，其余计入 `unknown`。
- 写入端保持 `observed`/`partial`，不做 schema 迁移。
- 契约口径：`observed` 即完整观测——Run 收到 `run.ended`；Span 同时观测到 start 与 end。
- 文档要求：API 返回中的分页完整性字段（`complete`/`partial`/`cycle`）与 `span_quality_counts` 是不同概念，必须分别说明。
- 待补验证：完整 Span 的 `sample_quality.status == "complete"`。

### D-3 非 ASCII / 空格身份：不处理，按现有规则丢弃

- 保持 `_TOKEN_PATTERN` 不变，不引入转义或字段级放宽；不合格身份导致的事件丢弃视为预期行为。
- 因此不做 scope 编码改造，`business_run_population` 的键无需同步编码，历史数据无需迁移。
- 遗留风险（不在本轮修复）：此类丢弃目前只在本地 `_dropped` 计数中体现，无生产者上报。若后续需要可观测性，随 `observer.health` 一并设计。
- 文档要求：在观测契约中明确"身份必须是 ASCII token，否则事件被丢弃"，避免被误判为采集故障。

## 五、本轮不处理项

- 方案 C（worker 独立事件文件 + 部署侧采集）：采集器在项目范围外，且无清理策略。
- `observer.health` 生产者：存在"队列满时 health 也被丢"的反馈循环，需要单独设计直写/降级策略。
- 非 ASCII 身份：已决策为丢弃，不做转义或放宽（见 D-3）。
- Console UI、Chromium 108/360、真实采集链、多 Pod、网关 header 信任：本轮未验证，维持原有暂停状态。
