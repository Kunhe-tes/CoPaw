# 09: 关联后台SubAgent及晚到终态

Status: in-progress
Type: task
Blocked by: 04
Triage: ready-for-agent
Priority: P0

**What to build:** 在根Run中看到后台SubAgent的基础关联和实际状态，即使根已结束也能继续查看子任务进展与最终结果，根Run不会因后台晚结束被重开。

**Blocked by:** 04：展示Attempt与Agent执行树、同行瀑布

**Status:** in-progress

依据已确认的独立可观测设计、Trace视图对照、领域词汇及ADR 0047/0048。与旧SDK、旧埋点、旧追踪ID和旧可观测存储查询没有运行依赖；只输出元数据，正文仅经现有业务授权从NAS读取。采集由用户处理，本票不增加ES、TTL/清理或新身份体系；授权仍沿用项目已有身份判定。

- [x] 启动快照传递独立Run、启动Attempt、子Span/父Span、业务子任务身份、根scope和采集快照，worker显式绑定及复位；不得由模型参数提供观测身份。
- [x] 根授权scope保持不变，worker执行Agent身份单独记录；P0仅覆盖基础关系与终态，不扩大为worker全量细粒度树。
- [x] 启动方拥有started槽，交接后worker拥有ended槽，自包含结束沿用不可变安全元数据；启动失败未交接时由启动方结算，不能双重结束。
- [x] 区分sync/async及真实业务task/run身份；启动成功不等于完成，worker不分配根Attempt序号，不额外创建第二个根Run。
- [x] 独立日志→乱序/重复投影→API→树/瀑布展示后台基础节点、状态和质量；缺上下文或终态标unresolved/partial，不替业务推断失败。
- [x] 允许子时条超出根/启动Attempt结束时间；根状态和ended_at保持原值，页面可同时显示根终态与后台运行，已知后台仍运行时有界轮询。
- [x] 覆盖父先结束、worker晚结束、启动失败、取消、进程中断、所有权交接与并发子任务时间重叠；不改变原Stop、执行或持久化语义。
- [ ] 验证跨Source详情不能访问、两种浏览器及嵌入场景；不开发新的进程恢复器或部署采集方案。

验收环境不可用时必须明确记录未验证项，不以构建成功或新浏览器模拟替代真实Chromium108验收。

## Comments

2026-11-15：用户已确认15张票的拆分及阻塞关系，现发布为本地实施事项。尚未领取或开工；本次发布不构成功能开发授权。
2026-11-17：Tool 启动边界现在先发 `span.started`，并将 Span ID、不可变 scope/Run/Attempt、父 Span 与开始时间封装进有版本的元数据 carrier。仅在 supervisor 返回已持久化的启动记录后转移 ended 槽所有权；容量拒绝或启动异常由父侧结算。Worker 重新校验业务 scope，丢弃 carrier 后绑定上下文，结束同一 Span ID；其 Agent Span 以该 SubAgent Span 为父，不创建第二个 Run，也不推进根 Attempt 序号。超时/拒绝等业务结果通过白名单 `result_status` 保留，通用 Span 状态使用协议枚举。

2026-11-17：`_span_for_api` 对 SubAgent 仅投影四个白名单身份/状态字段；Inspector 已显示 SubAgent Run、执行 Agent、模式和业务结果。MySQL pipeline 实测 start 与 end 可乱序入 inbox，详情 API 保留真实 parent span 与业务 ID，根 succeeded 保持不变。单元验证 117 passed；该文件 API/UI 24 passed；TypeScript 与目标文件 pre-commit 通过。

2026-11-17：复审发现并修复无 worker terminal 启动返回问题：仅当 supervisor 返回带正 worker PID 的记录才转移 ended 槽；无 worker terminal 记录由父侧结束，容量拒绝映射 rejected。Supervisor start 取消时保留未结束 Span，避免猜测 worker 是否已经写 ended 或重复结束；其观测状态明确为 partial/unresolved，而业务取消与进程清理由原 supervisor 负责。回归覆盖取消向上传播和不伪造终态。

2026-11-17：连接用户提供的 MySQL，在隔离库 `swe_agentobs_codex_20261117_test` 重跑 pipeline 与 Runner lifecycle 集成，14 passed。覆盖 SubAgent Span 的乱序投影、API 关联及根 Run 终态保持；OS 进程信号/worker 被杀、父先结束后的轮询和真实 Chromium 108/360 验收仍未完成。

2026-11-17：补充 Console 轮询回归：根 Run 与父 Agent Span 已 succeeded/ended、后台 SubAgent Span 仍开放时，Inspector 继续有界刷新；SubAgent 终态到达后停止自动轮询，手动刷新仍有效。AgentObservability 页面测试 18 passed，TypeScript、目标 ESLint 和 Prettier 通过。此为组件行为验证；真实 Chromium 108.0.5359.95/360 与 `hideMenu=true` 浏览器验收仍未完成。
2026-11-17：详情自动刷新新增每次打开/手动刷新的 5 分钟窗口；仍有已知开放 Span 时暂停并显示状态，不再无限轮询，手动刷新重新开启窗口。页面测试 19 passed，TypeScript、目标 ESLint、Prettier 与 `git diff --check` 通过。真实 Chromium 108/360 和 `hideMenu=true` 验收仍未完成。

仍未验收：OS 进程信号取消/worker 被杀后的迟到事实专项（start 请求取消按 partial/unresolved 保留）；父 Run 先终结、worker 晚结束后 UI 有界轮询/刷新行为；共享同一父 Span 的并发 SubAgent 时间重叠；真实 Chromium 108 页面与 `hideMenu=true` 页面验收。故本票保持 in-progress。

2026-11-17：增加两个并发 `_run_background_runtime` 调用合同测试：两 worker 各自看到传入的 SubAgent Span 为 parent，结束事件 business_subagent_key、Span ID 和根 Run ID 对应各自载体，任务上下文未串写。定向测试 1 passed。现有隔离 MySQL Inbox→API 主合同也验证 manager 用另一 Source 查子 Run 得 404。尚未模拟 OS 强杀 worker、同一 parent 下并发真实 worker 时间重叠和两种浏览器/嵌入场景；进程间强杀仍保留 unresolved，不自动补终态。

Worker 与工具定向单测合计 78 passed，worker 改动文件 pre-commit 通过；隔离 MySQL Run/Span 查询合同（含跨 Source 详情 404）1 passed。并发测试只证明 task-local 身份与 carrier end ownership 不串写，不代替多 OS worker 进程时间重叠/被杀验收。

2026-11-18：新增真实 OS 子进程 SIGTERM 合同：父侧先写入 SubAgent `span.started` 并传递版本化 carrier，子进程进入 worker runtime 后收到 SIGTERM；日志保留有效 start、没有伪造 ended，持久业务记录仍为原 `running`，未从观测事实改写业务状态。测试 1 passed，worker 测试文件 pre-commit 通过。独立只读复核确认真实子进程、carrier 和无伪造终态断言覆盖到位，无可操作发现；此测试证明进程中断语义，但不代替 MySQL projector/API 的本轮集成和真实 Chromium108/360/嵌入验收。

当前唯一可派生 SubAgent 运行形态为 supervisor 管理的 background worker；事件显式记录 `mode=background` 和底层持久 SubAgent `run_id`。启动成功只交接 ended 槽，不结算完成；worker 复用根 Run、不分配根 Attempt 序号。同步专家主执行仍属于根 Agent execution Span，没有独立 SubAgent task/run，因此不伪造同步业务子任务身份。

同日继续：新增隔离 MySQL 父先结束/子晚结束合同。Inbox→Projector 先写开放 SubAgent Span，再写根 `run.ended=succeeded`，最后写晚到 `span.ended`；验证根 Run 的 `status/ended_at` 保持原终态，晚到 Span 仍可查询并保留 `business_subagent_key`。真实 MySQL 1 passed，目标 pipeline pre-commit 全绿，随机 `_test` schema 清理并验证不存在。OS worker 被杀、并发跨进程时间重叠及浏览器/嵌入验收仍未完成，Ticket 保持 in-progress。

同日复验：新增父先结束合同后，完整 observability MySQL pipeline 在另一全新随机 `_test` schema 通过 11 项（190.87 秒），schema 已删除并确认不存在；仅 pytest 临时文件夹并发清理产生警告，不影响通过结果。原有未闭合 OS 并发/浏览器验收项维持不变。

独立复核发现首版合同只读 Store，未经过详情授权 API；现增加 manager Source 授权 Run Detail 断言，验证根 Run 仍 succeeded 且 ended_at 保持原值，同时晚到 SubAgent Span 显示 succeeded、较晚 ended_at 和业务子任务身份。与 Ticket 05 两种模型异常合同使用同一随机 `_test` schema 合跑 3 passed；schema 清理核验为0，两文件目标 pre-commit 全绿。Finding 已按代码更新待确认关闭；OS worker 被杀、并发跨进程时间重叠及浏览器/嵌入验收仍未完成。

2026-11-18 后续：并发 worker 屏障合同现在额外断言两个 SubAgent Span 的 `[started_at, ended_at]` 区间真实重叠；由屏障保证两个 runtime 均进入后才返回，时间戳断言作为可观测证据，并将调度超时放宽到 5 秒。该测试与 supervisor 启动失败、取消交接保留 partial、真实 OS SIGTERM 不伪造终态合同合跑 4 passed。父 Run 先结束、SubAgent 晚到终态的 Inbox→Projector→manager Detail API 合同在全新随机隔离 `_test` schema 复验 1 passed，schema 删除并核验不存在。该项后端验收现已覆盖；浏览器/嵌入验收仍按用户要求暂停。
