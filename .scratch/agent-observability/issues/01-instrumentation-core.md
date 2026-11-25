# 01: 设计完整埋点契约并实现独立观测内核

Status: resolved
Type: task
Blocked by: None
Triage: ready-for-agent
Priority: P0

**What to build:** 后续业务观察点使用统一的独立接口，即可为一次问题及其连续执行和真实操作输出可入库的安全元数据日志；以代表性执行场景验证核心行为。此票先完成完整埋点与类职责设计，再实现共用内核，不接入全部业务挂点，也不包含数据库投影器或Console页面。

**Blocked by:** None (can start immediately)

依据已确认的独立可观测设计、Trace视图对照、领域词汇及ADR 0047/0048。与旧SDK、旧埋点、旧追踪ID和旧可观测存储查询没有运行依赖；只输出元数据，正文仅经现有业务授权从NAS读取。采集由用户处理，本票不增加ES、TTL/清理或新身份体系；授权仍沿用项目已有身份判定。

- [x] 形成完整埋点矩阵，覆盖主请求、Agent连续执行、模型逻辑调用及可见请求尝试、实际工具、审批、SubAgent、资产和正文证据；逐项说明真实边界、拥有者、身份/父关系、必填字段、唯一生命周期槽、结束责任和缺失降级。
- [x] 提交事件模型、作用域与业务引用模型、独立上下文、观测门面、Span生命周期及安全输出的类职责、最小接口和调用时序；明确依赖方向，不建设通用插件框架或复制业务执行器。
- [x] 独立生成规范UUID身份；Run、Attempt、Span和event身份各司其职，生命周期槽在重传时稳定；结束事件自包含起始时间、关系、状态和有界摘要，支持缺start。
- [x] 独立上下文可绑定/复位、嵌套、并发隔离和序列化；审批/SubAgent载体只含元数据，明确跨进程Span槽所有权交接，不依赖日志已入库。
- [x] 单一全局开关默认关闭，在新Run准入快照固定，Attempt/SubAgent继承；关闭时不构造正文、不深拷贝正文、不连接观测数据库。
- [x] 使用独立有界writer将UTF-8单行JSON写stdout。单条24KiB、数组32项、深度4、4096条和含in-flight的8MiB预算及最多1秒关闭均有验证。
- [x] 白名单先于序列化；可选字段超限时安全截断并标记，必需字段无法保留时丢弃并安全计数；不得输出正文、工具参数结果、密钥或异常消息/堆栈，不做逐token日志。
- [x] 代表性Run→Attempt→Span测试覆盖成功、失败、取消、增量事实、开关快照、上下文串扰、队满、输出失败和进程关闭；新观测不能改变业务返回、异常或取消语义。
- [x] 验证与旧可观测没有导入/调用/数据依赖；新旧开关组合互不影响。本票不实施旧SDK改造、采集器或生产部署。

## Answer

已新增 `src/swe/observability/` 的事件/身份模型、Run/Attempt/Span门面、任务本地上下文及显式跨进程carrier、全局开关快照和独立有界stdout JSONL writer。应用关闭阶段最多等待1秒；禁用或writer不可用时保持业务结果/异常语义。埋点矩阵与调用时序见 [`instrumentation-matrix.md`](../instrumentation-matrix.md)。

检视：子代理完成两轮只读代码审查，修复重复增量槽、Attempt前驱、敏感字符串数组、事件身份覆盖、取消分类、嵌套字段白名单、关闭上限和writer初始化失败等问题；终审无阻塞项。

验证：`venv/bin/python -m pytest tests/unit/observability/test_core.py tests/unit/app/test_agent_trace_sdk.py tests/unit/app/test_runtime_diagnostic_integration.py -q`（35 passed）；Black检查与`git diff --check`通过。测试输出含既有 pytest 临时目录清理警告，不影响测试结果。

## Comments

2026-11-15：实现授权来自本轮用户目标“implement-spec”；本票完成并通过子代理代码检视。
