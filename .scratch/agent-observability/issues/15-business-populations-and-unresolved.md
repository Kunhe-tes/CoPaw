# 15: 展示业务总体、确认Run与未关联记录

Status: open
Type: task
Blocked by: 08, 09
Triage: ready-for-agent
Priority: P0

**What to build:** 运营人员能分别查看当前可查询的业务问题/Turn/SubAgent数量、可确认逻辑Run的成功率及未能关联的记录，审批恢复和无日志问题不会扭曲统计分母。

**Blocked by:** 08：贯通审批等待与同Run恢复执行；09：关联后台SubAgent及晚到终态

**Status:** ready-for-agent

依据已确认的独立可观测设计、Trace视图对照、领域词汇及ADR 0047/0048。与旧SDK、旧埋点、旧追踪ID和旧可观测存储查询没有运行依赖；只输出元数据，正文仅经现有业务授权从NAS读取。采集由用户处理，本票不增加ES、TTL/清理或新身份体系；授权仍沿用项目已有身份判定。

- [ ] 只读现有会话/SubAgent业务元数据取得当前可查询数量与状态，结合独立Run/审批/子任务关系，经新API和独立总览UI分别展示三种统计总体。
- [ ] 业务Turn不是Run：审批合成问题按可确认链路归并，同一Run多Attempt不重复计根；关联不齐单列unresolved，不静默当独立自然语言问题或成功Run。
- [ ] 逻辑Run成功率分母只纳入可确认关联/结算的Run；未知/等待/unresolved按明确口径另列，缺日志不判失败，不声称丢关联时仍有全量逻辑Run统计。
- [ ] 只有业务事实而无日志时返回业务定位及not_collected/unknown等可证明状态，不伪造obs_run_id/操作树，不误称已知采集延迟。
- [ ] 根业务结果与后台SubAgent状态分开，晚到子终态不重开或改写根结果，不用后台未结束强行延长根结束时间。
- [ ] API/UI标明population_source、window、各自as_of/generated_at及观测覆盖；不声称业务DB、独立观测DB与NAS跨库原子快照。
- [ ] 统计遵守当前授权及业务删除规则，说明当前可查询总体可随删除变化；不新增删除后不可变审计副本或合法元数据清理任务。
- [ ] 用正常问题、连续审批、重复批准、根先结束/子晚结束、无日志、缺关联、删除与跨Source数据验证计数/分母及权限；不依赖性能总览票完成。
- [ ] 完成总览端到端测试及真实Chromium108、当前浏览器与适用嵌入场景验收。

验收环境不可用时必须明确记录未验证项，不以构建成功或新浏览器模拟替代真实Chromium108验收。

## Comments

2026-11-15：用户已确认15张票的拆分及阻塞关系，现发布为本地实施事项。尚未领取或开工；本次发布不构成功能开发授权。

2026-11-17：完成后端总体 API、业务 Turn/当前可见 Chat-Session 查询、精确 Run 关联及 SubAgent 聚合。SubAgent 按窗口内创建时间统计，但可见父 Chat/Session 集合独立于窗口内 Turn；缺 Chat 关联的可见 Session 记录单列 unresolved。相关单测 60 项通过，观测/会话/SubAgent 单测合计 2,101 项通过，聚焦 pre-commit 通过。真实 MySQL 集成验证未完成：当前客户端认证被服务器拒绝，未创建数据库或写入数据。按用户要求，页面实现和浏览器验收暂缓，ticket 保持 open。

2026-11-18：新增真实 MySQL 总体查询合同，使用随机 `_test` schema 从 JSONL Inbox 经 Projector 写入并读取精确 workspace 范围的 Run；将结果与三个业务 Turn 身份投影，验证成功和失败各计入 settled 分母、没有观测 Run 的 Turn 为 `not_collected`、身份不匹配 Run 单列 `unresolved`，成功率为 1/2。MySQL 合同 1 passed，纯投影回归 2 passed，目标 pre-commit 全绿；临时 schema 在 finally 删除并验证不存在。SubAgent/业务历史读取仍为单测所覆盖，未做该跨库完整 endpoint/MySQL 合同。页面与浏览器验收按用户要求暂停，ticket 保持 open。

同日继续：将上述契约提升为真实 `/agent-observability/business-population` HTTP 路由合同；业务历史 Turn 与 SubAgent population 使用受控 stub，Run population 继续从隔离 MySQL Store 经 Inbox→Projector 读取。响应验证 Turn/settled 成功率、`not_collected`、unresolved、SubAgent count 与 `observability_as_of`，MySQL 合同 1 passed，随机 `_test` schema 清理并验证不存在。仍未做真实业务历史库和 SubAgent 持久化的跨库原子快照，页面/浏览器按用户要求暂停，ticket 保持 open。

2026-11-18：扩展该 API 集成合同，使 SubAgent population 使用临时目录中的真实 `PerRunSubAgentRunStore` JSON 记录与 `create_monitor_service()`，验证 pending/running 状态计数、缺 Chat 关联的 unresolved，以及可见 Session 下不匹配 Chat 被排除；仅业务 History 继续 stub。独立只读复核未发现问题。相关投影与 SubAgent 单测 48 passed，目标 pre-commit 全绿；本次 MySQL 路由用例因当前 shell 未配置专用 `_test` DB 环境变量而跳过，故该扩展尚未做真实库验收。页面/浏览器仍按用户要求暂停，ticket 保持 open。

同日复验：通过本轮临时注入的数据库连接配置在随机 `_test` schema 初始化仓库 DDL，重跑该 API 合同，真实 MySQL 1 passed；finally 删除该 schema 并查询确认不存在。未访问或写入业务 schema。页面/浏览器仍暂停，Ticket 保持 open。

同日再验：相同的随机 `_test` schema 流程完整运行 `tests/integrated/observability/test_mysql_pipeline.py`，12 passed（199.50s）；测试进程退出前删除 schema 并用 information_schema 查询确认不存在。仅有 AnyIO pytest 插件重写告警及既有临时目录清理警告，无测试失败。Ticket 仍保持 open，页面/浏览器按要求暂停。

同日继续：新增 `tests/integrated/conversation_storage/test_business_population_mysql.py`，在 fixture 创建的随机 conversation `_test` 子 schema 中同时安装会话表与观测表，实际插入授权 Source 的已准入/已完成 Turn 和另一 Source 的 admitted Turn，经真实 `HistoryStore.business_turn_population()` 及 manager `/business-population` API 查询。验证只统计授权 Turn、状态与 `not_collected` 口径、真实可见 Chat/Session 范围及空观测 Run/SubAgent 分母。真实 MySQL 1 passed；随机控制 schema 和 fixture child schema 均由 finally 清理并确认不存在。目标 pre-commit 全绿，独立复核确认 Source 隔离断言有效、无可操作问题。该合同仍 stub 观测 store 连通性之外的业务 Worker/身份中间件，且未覆盖真实 SubAgent 与业务 History 同时由业务库读取；页面/浏览器按用户要求暂停，Ticket 保持 open。

2026-11-19：扩展同一真实 MySQL/API 合同，使用 `PerRunSubAgentRunStore` 写入同一可见 Session 下的 pending、running 和无 Chat 关联记录，并写入另一 Chat 作为排除项；业务 Turn 继续从真实 `HistoryStore` 读取。manager API 正确返回 `subagents.count=2`、pending/running 状态各1、unresolved=1，同时保留授权 Source 和 `not_collected` 口径。真实测试 1 passed（6.20s），控制 schema 和 fixture 子 schema 清理并确认不存在；目标文件 pre-commit 通过。仍未覆盖跨进程业务库与 SubAgent 持久化的原子快照、页面及浏览器验收，Ticket 保持 open。
