# 05: 查看真实模型调用、用量与首输出延迟

Status: open
Type: task
Blocked by: 04
Triage: ready-for-agent
Priority: P0

**What to build:** 在执行链路中查看真正发生的模型调用，理解请求与实际模型、耗时、首输出延迟及已知用量；没有调用模型的短路和缺Usage不会制造调用或零值。

**Blocked by:** 04：展示Attempt与Agent执行树、同行瀑布

**Status:** ready-for-agent

依据已确认的独立可观测设计、Trace视图对照、领域词汇及ADR 0047/0048。与旧SDK、旧埋点、旧追踪ID和旧可观测存储查询没有运行依赖；只输出元数据，正文仅经现有业务授权从NAS读取。采集由用户处理，本票不增加ES、TTL/清理或新身份体系；授权仍沿用项目已有身份判定。

- [ ] 观察点位于实际模型调用边界，分别定义逻辑调用与本项目可见请求尝试；保留后续重试扩展身份，不能把一次reasoning包装等同一次物理请求。
- [ ] 从真实流式与非流式请求到独立日志、Span投影、API、LLM Inspector和Run摘要完成闭环；审批/计划等无请求短路不计llm_calls。
- [ ] 记录受控provider、请求模型、响应模型、streaming和finish reason；响应模型补齐可替换请求回退索引值并保留来源，二者不同不标身份冲突。
- [ ] 首有效chunk排除空启动与usage-only帧，首可见文本另计；无输出为null，非流式不伪造TTFT，未证明为首token时页面不称精确TTFT。
- [ ] Usage取真实最终/最新累计快照，不逐帧相加，不重复统计父逻辑容器和请求操作，不默认把推理Token额外加进输出；未知input/output分别保持null并展示覆盖。
- [ ] 只记录真实存在的Step及实际Loop计数，不创建假Loop区间；数据字段与详情/性能使用同一口径。
- [ ] 测试流式取消、异常、无输出、Usage缺失、实际模型变化与并发上下文；日志/Raw不包含prompt、messages或响应文本，成本保持P1。
- [ ] 验证LLM类型详情在Chromium108、当前浏览器及适用嵌入场景正常展示。

验收环境不可用时必须明确记录未验证项，不以构建成功或新浏览器模拟替代真实Chromium108验收。

## Comments

2026-11-15：用户已确认15张票的拆分及阻塞关系，现发布为本地实施事项。尚未领取或开工；本次发布不构成功能开发授权。

2026-11-16：预备实现独立 `ObservabilityModelWrapper`，位于 RetryChatModel 外层，记录逻辑 LLM Span、受控 provider/request model、非流式最终 Usage、流式首个有效 chunk 和取消/异常状态；metrics 合并保留实测 duration，正文和 prompt 不进入事件。确定性单测 26 passed，真实普通 Runner MySQL 链路已验证主执行，但该票仍保持 `open`，等待 Ticket 04 完成树/Inspector，并需补齐模型 Span 的真实投影/API/UI验收及 Chromium 108 基线。

2026-11-16：使用独立 `swe_agentobs_codex_20261116_test` MySQL 库完成真实 Runner 验证：生命周期/结算与普通、专家主执行共 6 passed；Inbox 投影、授权 Run 查询和事件分页 2 passed；observability 单测 36 passed；Console typecheck、页面 Vitest 6 passed、相关 ESLint 通过。MySQL readiness 返回 `ready=true`，无缺表、列或索引。真实 Runner 断言覆盖 LLM Span 的 request/response model、来源、streaming、finish reason、Usage、API 查询及非流式首输出保持 null。未连接或写入业务库。Chromium 108.0.5359.95、当前浏览器及 `hideMenu=true` 下新增 LLM Inspector 展示仍未验收；流式取消、无输出、Usage 未知及并发上下文的端到端边界也未全部覆盖，因此本票继续保持 `open`。

2026-11-16：补充模型包装器边界回归：流式 Usage 使用最终累计快照而非逐帧相加；空输出/无 Usage 保持 token 与首输出延迟未知；Task cancel 与 async generator `aclose()` 均以 cancelled 结束 Span 并关闭源流；并发 Run 共用包装器时身份隔离，正文不入日志。`tests/unit/observability` 与 Runner 生命周期集成入口合计 41 passed、6 skipped（该次未提供真实 MySQL 环境变量）；Ticket 04/05 真实 MySQL 集成此前另行实测通过。目标 pre-commit 通过。Ticket 仍保持 open，浏览器及完整 UI 验收尚未完成。
