# 06: 查看真实工具执行、拒绝与技术错误

Status: in-progress
Type: task
Blocked by: 04
Triage: ready-for-agent
Priority: P0

**What to build:** 从执行链路识别工具真正执行了几次、用了多久、处于什么业务和技术状态，并能区分审批/策略拒绝与实际执行失败。

**Blocked by:** 04：展示Attempt与Agent执行树、同行瀑布

**Status:** in-progress

依据已确认的独立可观测设计、Trace视图对照、领域词汇及ADR 0047/0048。与旧SDK、旧埋点、旧追踪ID和旧可观测存储查询没有运行依赖；只输出元数据，正文仅经现有业务授权从NAS读取。采集由用户处理，本票不增加ES、TTL/清理或新身份体系；授权仍沿用项目已有身份判定。

- [x] 真实工具执行使用独立tool_execution_id，关联业务tool_call_id和受控tool_key；同call重放可有不同execution_id，不能把包装层重复观察计为多次执行。
- [x] 记录实际可知的executor_kind、timeout budget、retry index和exit code，从日志→投影→API→Tool Inspector及Run实际调用计数完成闭环。
- [x] guard/审批/策略短路单独记录真实事实；未执行不增加工具执行次数，结构化失败不只依赖Python异常。
- [ ] 业务status、technical_status、has_error和受控error.type/phase/code独立；失败、取消、拒绝不自动等同技术ERROR，子失败不自动把根或父操作标ERROR。
- [ ] 安全name来自注册值而非命令/SQL/用户参数；工具schema、参数、结果和异常原文不进日志或安全Raw；为后续NAS证据保留精确业务关联。
- [ ] 重复或乱序结束不叠加计数；缺开始可用自包含结束摘要但标partial，父身份/业务身份冲突不静默覆盖。
- [x] 测试实际成功/结构化失败/异常/取消/超时明确裁决、guard拒绝及并行工具；验证原工具调用次数、返回与取消语义不变。
- [ ] 完成真实工具的端到端演示及Chromium108、当前浏览器受影响Inspector验收。

验收环境不可用时必须明确记录未验证项，不以构建成功或新浏览器模拟替代真实Chromium108验收。

## Comments

2026-11-15：用户已确认15张票的拆分及阻塞关系，现发布为本地实施事项。尚未领取或开工；本次发布不构成功能开发授权。

2026-11-16：预备接入独立 Tool Span：在 `ToolGuardMixin` 的真实 hard-timeout 工具执行边界包裹 `registered.tool`，携带受控 tool_key、tool_call_id、executor_kind，按实际返回、结构化空结果、异常和取消分别结束，不记录参数/结果正文。既有工具相关回归 135 passed；本票仍保持 `open`，等待 Ticket 04 详情闭环后补投影/API/Inspector 及 Chromium 108 验收。

2026-11-16：已补充 Tool Span 的 timeout budget 与 execution id，按结构化 `isError` 区分业务失败和技术错误；取消不标成技术 ERROR。工具标识与白名单元数据已贯通 JSONL、MySQL span 投影、manager 授权 Run Detail API 和 Console Inspector。最终验证：相关 Python 单测 107 passed；真实 MySQL `_test` schema observability 集成 9 passed；Inspector Vitest 10 passed；TypeScript、目标 ESLint、生产构建和 pre-commit 均通过。没有连接或写入业务库。工单保持 `open`：Ticket 04 尚未关闭，且真实 Chromium 108.0.5359.95/360 验收环境不可用。
2026-11-17：新增 `tests/unit/agents/test_tool_observability.py`，直接运行真实 `_run_tool_call_with_hard_timeout_impl` 边界并替换外层 toolkit 执行器，验证成功/结构化 permission_denied/普通异常/取消的 Span 终态、技术状态、正文不落日志和业务返回/异常传播。7 项边界与模型调用路径测试通过。Ticket 06 其余未完成项：Guard/审批短路的独立事实、超时/并行工具执行覆盖、真实 Chromium 108 Inspector 验收。
2026-11-17：补充 Guard 判定事件：auto-denied 以 `Guard/rejected`、待审批以 `Guard/waiting_approval` 记录，身份只含 tool_key/tool_call_id/executor_kind，不生成 Tool execution id、不增加实际工具调用数。Projector 明确允许 Guard 携带安全 Tool identity，但拒绝 Guard 伪称拥有 tool_execution_id。直接 `_acting_impl` 回归验证策略短路未进入 tool executor，两个 Guard 状态通过正式 `_validate_payload`。
2026-11-17：连接用户提供的 MySQL，在隔离库 `swe_agentobs_codex_20261117_test` 重跑观测 pipeline 与 Runner lifecycle 集成，14 passed。验证覆盖 Guard 身份从 inbox→MySQL→manager 授权 Run Detail 的闭环；未写业务库。真实 Chromium 108/360 验收仍未完成。

2026-11-17：`tests/unit/agents/test_tool_observability.py` 增加真实 hard-timeout 路径与两项并行工具重叠验证，断言 timeout 取消底层执行、以受控 `tool_timeout` 标记技术错误；并行工具各自保留 tool_call/execution ID，原结果及一次调用语义不变。成功、结构化失败、异常、取消、guard 拒绝、timeout、并行场景共 8 passed。Chromium 108.0.5359.95/360 Inspector 实机验收仍未完成。
