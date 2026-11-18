# 12: 完成Run Explorer精确检索与组合筛选

Status: open
Type: task
Blocked by: 03
Triage: ready-for-agent
Priority: P0

**What to build:** 运营人员通过授权范围内的完整身份或时间、Agent、状态和耗时条件定位Run，稳定翻页并恢复查询位置，无法通过游标或跨Source条件扩大访问范围。

**Blocked by:** 03：展示真实问题的Run生命周期与采集状态

**Status:** ready-for-agent

依据已确认的独立可观测设计、Trace视图对照、领域词汇及ADR 0047/0048。与旧SDK、旧埋点、旧追踪ID和旧可观测存储查询没有运行依赖；只输出元数据，正文仅经现有业务授权从NAS读取。采集由用户处理，本票不增加ES、TTL/清理或新身份体系；授权仍沿用项目已有身份判定。

- [ ] 搜索显式选择Run、Attempt或Session完整身份；Run/Attempt精确查找不受默认24小时隐藏，不接旧Trace ID、不混猜身份，不开放前缀/全文/正则/SQL检索。
- [ ] 列表支持授权Source、Agent、业务status、时间窗、最短已知耗时组合；默认时间倒序，可选已结束且duration已知的耗时倒序，运行中elapsed不混入终态排序。
- [ ] 使用独立MySQL对应索引和类型化列，完整scope及业务原值精确复核；组合查询提供EXPLAIN及数据规模记录，不能宣称一个索引覆盖所有条件。
- [ ] 默认最近24小时50条、最多200条、单窗最多31天但可选任意历史窗口；返回has_more，不进行无界总COUNT或全库聚合。
- [ ] 游标包含版本、排序/过滤与授权指纹、稳定最后键及独立MAC，每次重验scope；过滤变化拒绝复用旧游标。
- [ ] admin跨Source必须显式指定，最多32个授权Source稳定归并，游标保留各范围位置；manager不能跨Source，不能用只按model/tool的索引代替Run鉴权。
- [ ] 候选扫描默认最多50000、查询5秒及响应字节预算可验证；超限明确range_too_large，不截取前N条冒充完整结果。
- [ ] URL保留可分享筛选和选择，返回列表恢复分页/滚动，不把正文或凭据写入URL；只在可信摘要时显示调用/Token，成本隐藏或unavailable。
- [ ] 验证精确身份、组合条件、相同排序键、游标篡改/换范围、跨Source归并、未知耗时、历史查询、超预算及目标浏览器交互。

验收环境不可用时必须明确记录未验证项，不以构建成功或新浏览器模拟替代真实Chromium108验收。

## Comments

2026-11-15：用户已确认15张票的拆分及阻塞关系，现发布为本地实施事项。尚未领取或开工；本次发布不构成功能开发授权。

2026-11-17：补入 Run/Attempt/Session 精确查询、Agent/status/min-duration 组合筛选、管理员跨 Source 32 范围上限和按 `(started_at,run_id)` 稳定分页；Session ID 已由 Runner metadata-only business_ref 投影至 `session_key` 并通过隔离 MySQL API 用例验证。Run 列表增加已结束、duration 已知的耗时倒序及绑定 sort/filter 的签名 keyset 游标；Console 增加身份、Agent、状态、最短耗时、时间窗与排序控件。验证：MySQL inbox→projection→manager API 1 passed，observability query/lifecycle 单测 21 passed，Console API/页面 Vitest 19 passed，TypeScript 与相关 pre-commit 通过。仍保持 open：跨 Source admin 最多 32 范围归并游标、EXPLAIN/候选扫描 50000 与查询时间预算、同时间排序键/超预算及历史精确身份的专门回归还未齐；Playwright 当前为 HeadlessChrome 157，顶层本地访问没有父 iframe USER_DATA，无法验证受权页面；Chromium 108.0.5359.95/360 内核未验收。

2026-11-17：Run 列表在执行分页查询前增加与实际过滤相同的候选探测，最多读取 50001 个 Run ID；超过 50000 返回 `range_too_large`。候选和页面 SELECT 均设置 MySQL 5 秒执行上限，响应序列化限制 1 MiB。专用测试库 API 集成验证超预算返回 422，query 单测验证 MySQL 执行超时识别；`EXPLAIN` 对 26 行、Source+时间窗查询选择 `ix_agentobs_runs_scope_time`，实际返回 26 行，候选探测加页面查询约 82ms。该容量结果仅代表 26 行测试数据，不外推生产 SLA。仍缺 URL 恢复/分享、管理端多 Source 游标与同 duration 并列键跨页测试及 Chromium 108 验收。

2026-11-17：筛选、Source 集合、签名分页游标和选中 Run 已写入 URL；刷新恢复筛选/页游标/Inspector，浏览器 back/forward 监听 `popstate` 并重新查询，保留 `hideMenu` 等非观测参数。Console 页面/API 测试 20 passed、TypeScript 通过。仍缺管理员跨多个 Source 的真实分页归并、duration 相同值的跨页无遗漏/重复与游标换过滤拒绝等专门 MySQL 测试；Chromium 108.0.5359.95/360 页面验收未完成。

2026-11-17：对隔离库 `swe_agentobs_codex_20261117_test` 用唯一 bench Source 插入 50,001 条合成 Run 行，授权列表 API 候选探测返回预期 `422 range_too_large`，单次请求耗时约 0.46s，插入耗时约 11.06s。脚本按唯一 Source 清理，随后确认所有 `bench-%` Source 行数为 0。此为单次 API 延迟观测，未采集 MySQL 主机 CPU/内存，也未重复计算 P50/P95，不能据此宣称资源预算或生产 SLA 达标；108/360 页面验收仍待服务 API 可用。
同日 Chromium 108.0.5359.29 页面尝试被本地 dev server 的 `/api/auth/status`、有效配置及模板 API 500 阻断；Run Explorer 没有渲染，故该次不计作 UI 验收。Chromium 108.0.5359.95、360 内核及嵌入模式仍未验证。
2026-11-17：扩展隔离 MySQL 授权列表合同，向第二个测试 Source 写入三条 Run，以 `limit=2` 通过多页管理员跨 Source keyset 查询；断言两 Source 都出现、排序稳定、无重复且游标结束。manager 越权拒绝保持 403。该 pipeline 用例通过（55.71s），目标文件 pre-commit 通过。

2026-11-17：完成上条记录列出的查询合同覆盖：MySQL 集成测试新增 admin 两 Source 查询、manager 越权拒绝、相同 duration 多页稳定键/无重复、过滤变化复用 cursor 返回 400；另验证候选预算超额 API 返回 422。query 单测 13 passed，MySQL 专项 1 passed，Console API/页面 22 passed，TypeScript 与相关 Python pre-commit 通过。候选探测 EXPLAIN 在 35 行库上选用 `ix_agentobs_runs_agent_time` skip scan、计数 35、约 36ms；仍需更大数据规模下的查询/资源报告与目标 Chromium 108/360 页面验收。

2026-11-17：补齐管理员请求两个 Source 的授权列表、manager 跨 Source 拒绝、50,000 候选阈值、过滤变化时签名游标拒绝，以及三个相同 duration Run 的 keyset 跨页唯一性 MySQL 合同覆盖；MySQL 专项 1 passed，query 单测 13 passed，Console API/页面测试 22 passed，TypeScript、相关 pre-commit 通过。隔离库当前 35 行，候选探测返回 35、约 36ms；其 EXPLAIN 选择 `ix_agentobs_runs_agent_time` skip scan，列表页 EXPLAIN 选择 `ix_agentobs_runs_scope_time`。样本很小，不能证明 50,000 行时预算性能，仍需大样本/资源报告及 Chromium 108/360 验收。

同日复审又发现并修复两项 Console P2：缺少 `min_duration_ms` 时避免将 `Number(null)` 解释为 0（否则会隐藏 duration 未知的运行中/部分 Run）；POP 筛选或 Source 变化但 `selected_run` 不变时保留并重新授权读取所选详情。页面测试增加默认 duration、同 Run 选择恢复断言，Console API/页面 Vitest 23 passed，目标 ESLint 与 TypeScript 通过。

2026-11-18：在当前工作区状态下重新运行完整 `tests/integrated/observability/test_mysql_pipeline.py`，随机 `_test` schema 初始化后 12 passed（310.09s），覆盖候选预算、管理员多 Source 分页、manager Source 隔离、相同排序键稳定翻页、游标过滤绑定和精确身份等现有合同；schema finally 删除并回查不存在。query 与 Skill detector 单测 167 passed，相关集成文件 pre-commit 全绿。测试运行伴随 pytest 并发临时目录清理 warning，不影响用例退出状态。

2026-11-18：新增历史精确身份 MySQL/API 合同：Inbox 写入一条 7 天前的已结束 Run 和 Attempt，经 Projector 后验证默认最近 24 小时列表不返回该 Run，而按完整 `run_id` 或 `attempt_id` 查询均由 manager 授权 API 精确返回它。随机 `_test` schema 安装当前观测 DDL 后通过（1 passed，74.12s），测试结束删除 schema 并查询确认不存在。大规模查询资源报告和浏览器验收仍未完成。

同日整理：为避免将该合同混入共享 pipeline 文件中的其他未提交覆盖，迁移为独立 `test_historical_run_query_mysql.py`；独立合同在同样的隔离 DDL/schema 流程通过（1 passed，6.71s），测试后删除并验证 schema 不存在。目标 pre-commit 全绿。

2026-11-18：针对 Run 列表候选扫描另建随机 `_test` schema，批量插入 50,001 条同 Source、同一 12 秒窗口的合成 Run，且全部命中查询条件，作为非选择性的最坏候选集。对生产 `count_run_candidates` 与首屏 `list_runs(limit=51)` 各执行7次：候选计数始终截到50,001，P50=240.56ms、nearest-rank P95=250.62ms；首屏每次51条，P50=285.57ms、P95=316.66ms。授权 Run List API 对同一范围返回 `422 range_too_large`。MySQL 8.0.46 EXPLAIN：候选查询选 `ix_agentobs_runs_question`（仅使用 service/source 前缀，估算25,000行）；首屏选 `ix_agentobs_runs_scope_time` 并出现 `Using filesort`（估算25,000行）。该次仅一个Source和单次 schema 装载，测得 Python client CPU 0.1104s；没有 MySQL 主机 CPU 归因，也没有采集服务器内存数据，因此不代表生产 SLA、选择性时间窗或并发容量。随机 `_test` schema 已删除并查询确认不存在。

同日选择性窗口复测：另建随机 `_test` schema，将 50,001 条 Run 按秒分布于约 13.9 小时，查询其中 10 秒窗口命中10条。ANALYZE TABLE 后，Store 层 `count_run_candidates` 与 `list_runs(limit=51)` 各测7次，候选数及页大小均为10；P50/P95 分别为154.87/160.03ms和162.43/167.59ms。MySQL 8.0.46 EXPLAIN 两条查询都选择 `ix_agentobs_runs_source_time`，估算10行；首屏为 backward index scan，无 filesort。该结果仅覆盖单Source和简单时间筛选，未测组合筛选、多Source或 API 请求延迟。耗时包含远端连接往返，不能视为数据库纯执行时间；本轮未测 MySQL 主机 CPU/内存，亦不代表并发或生产 SLA。随机 `_test` schema 删除并核验不存在。

同日追加：新增 Source authorization 单测，确认 admin 请求 32 个唯一 Source 成功、重复 Source 在计数前去重、33 个唯一 Source 返回 400 `Too many Source filters`。定向 pytest 1 passed，目标 pre-commit 全绿。
