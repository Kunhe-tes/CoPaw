# 13: 完成大链路跨页定位与晚到数据刷新

Status: open
Type: task
Blocked by: 04
Triage: ready-for-agent
Priority: P0

**What to build:** 在大型执行链路中稳定滚动、查找和定位目标操作，即使错误或祖先位于未加载页、事件迟到插入旧页，树、瀑布与Inspector仍保持一致。

**Blocked by:** 04：展示Attempt与Agent执行树、同行瀑布

**Status:** ready-for-agent

依据已确认的独立可观测设计、Trace视图对照、领域词汇及ADR 0047/0048。与旧SDK、旧埋点、旧追踪ID和旧可观测存储查询没有运行依赖；只输出元数据，正文仅经现有业务授权从NAS读取。采集由用户处理，本票不增加ES、TTL/清理或新身份体系；授权仍沿用项目已有身份判定。

- [ ] 在所选Attempt全集内提供受控name/operation/tool/model查询和技术错误定位，按稳定开始时间/Span ID顺序导航；不只查已加载首屏。
- [ ] 定点节点返回正确Attempt及必要祖先，祖先每页最多64并可继续；visited防循环，超预算/异常关系显示质量，不把截断路径当Root。
- [ ] parent_not_loaded、过滤保留的ancestor_context和经授权定点确认不存在的Parent missing分别展示，不猜父子或把Links画成parent。
- [ ] 20/200/2000节点共享虚拟行、展开/选择模型；Span默认200/最多1000、窄行响应受1MiB建议字节预算限制，大metadata按需读。
- [ ] 深链接、末页搜索命中、末页首错误、上下错误及跨页祖先均能定位；只有集合完整且duration已知才算前10%慢节点，否则用明确阈值。
- [ ] 刷新重新遍历当前已加载分页并按ID去重，不能只读started_at大于旧最大值；已读页之前的晚到节点可见，响应明确eventual一致性及刷新未齐。
- [ ] 保留真实墙钟异常与单调耗时差异；不把缺end永远当running、不把并发耗时相加；无已知后台时终态停轮询，隐藏暂停且手动刷新可查晚到事实。
- [ ] 通过合成大链路契约数据从投影到API/UI验证，不阻塞于尚未接入的模型/工具真实挂点；首错误定位不自动称根因。
- [ ] 在真实Chromium108与当前浏览器、1280/1440和hideMenu=true验收滚动、键盘选择、面板和时间轴，记录数据量与交互表现。

验收环境不可用时必须明确记录未验证项，不以构建成功或新浏览器模拟替代真实Chromium108验收。

## Comments

2026-11-15：用户已确认15张票的拆分及阻塞关系，现发布为本地实施事项。尚未领取或开工；本次发布不构成功能开发授权。

2026-11-17：修复已加载 Span 后刷新只重读首屏、并保留旧后续页的问题。Inspector 手动刷新现在按已加载页数重新遍历游标前缀、按 span_id 去重并替换当前页集，因此已读页之前晚到的 Span 与补到的跨页 Parent 可见；手动刷新在隐藏标签页仍允许，自动轮询保持隐藏暂停，刷新可清除五分钟暂停并重开窗口。页面回归覆盖首屏后加载下一页、旧页前插入晚到 Span、晚到 Parent 解除 parent_not_loaded；页面测试 19 passed，TypeScript、目标 ESLint、Prettier 通过。
Chromium 108.0.5359.29 实机页面无法读取：本地 dev server 的认证、有效配置和模板 API 返回 500，未加载 Inspector；108.0.5359.95、360、当前授权浏览器及 `hideMenu=true` 仍未验收。跨页全链路搜索/定点祖先路径、虚拟列表和大数据 UI 性能也未完成，故工单保持 open。

2026-11-17：补入授权 Run 内 Span 搜索 API 与 Console 控件，支持当前 Attempt 限定、name/operation/tool/model 字段文本查找、失败筛选、受控每页 100 条和过滤/授权绑定签名游标；首批命中追加至 Inspector 树并可直接选中。候选超过 50,000 返回 `range_too_large`，候选与页面 SQL 含 5 秒执行预算、响应含 1 MiB 字节预算。Console API 序列化测试、搜索命中 Inspector 测试、TypeScript/ESLint/Prettier 通过；MySQL Inbox→projector→manager Run Detail 搜索 `read_file` 与组合错误筛选集成用例通过（pipeline 专项 1 passed）。当前仍缺定点搜索跨页父祖先获取/64 深度截断质量、2000 项虚拟列表和末页错误导航；Chromium 108/360 与 hideMenu 实机验收受本地服务 API 500 阻断。
Span API/Inspector 页面与模块测试现合计 28 passed；搜索命中不会依赖首屏加载，选择后并入 Inspector 树。当前搜索本身按每页 100 条分页，但仍未实现搜索命中祖先路径按 64 条继续取回和图/时间轴的定点滚动导航。

复审后补强：分页刷新按 Span ID 合并已读节点与重读页，新值覆盖旧值，避免早页晚到 Span 将已加载尾节点挤出当前树；回归覆盖页首插入、尾部保留、新父节点出现和旧 parent_not_loaded 消失。搜索筛选变化会取消旧请求、删除旧查询命中并清空旧游标；新命中按 `(started_at, span_id)` 排序。50,000 候选预检在每个搜索游标页重新执行，避免 Run 增长后绕过阈值。当前 Console 页面/API测试 28 passed，MySQL 搜索/投影与 Run 查询主合同 1 passed（57.54s），query 单测 14 passed，pre-commit、TypeScript、ESLint、Prettier 通过。
最终 MySQL 合同再次通过（59.99s），额外验证搜索 cursor 不能换用不同 query；完整 Console API/页面套件 28 passed、query 单测 14 passed，Python pre-commit 全绿。生产构建通过，仍有仓库既有循环 chunk 与大 chunk 警告。

2026-11-17：为已有 Span ancestor store/API 补充无 MySQL 依赖的单测，覆盖64深度游标续取、链根结束、Parent missing 和环检测；29项 observability query 单测通过，目标 pre-commit 通过。当前 MySQL 认证不可用，授权 API→MySQL 的祖先分页及 Source 隔离没有在本轮重验；页面定点滚动、虚拟列表和 Chromium 108/360 验收仍未完成，工单保持 open。

2026-11-18：补充 ancestors 路由合同：manager Source 查询不到 Run 时在调用祖先 store 前统一返回 404；授权 Run 则将 continuation cursor/limit 传至 store 并保留 `depth_limited` 质量。query 单测 32 passed，目标 pre-commit 通过。真实 MySQL 和 UI/浏览器验收未完成。

同日继续：新增隔离 MySQL 祖先分页/API 合同，Inbox→Projector 写入五层 Span parent 链，验证 Store 按最多两项返回并以 continuation cursor 续取，跨到其他 manager Source 的同一 Run 通过授权 API 返回 404。首次契约中的任意 Span `name` 被安全元数据投影器丢弃，按真实协议改用已注册 `agent.execute` 名称后通过；生产投影规则未修改。真实 MySQL 1 passed，祖先 Store/API 单测 2 passed，目标 pre-commit 全绿；随机 `_test` schema 删除并验证不存在。跨页搜索命中祖先滚动、虚拟列表和浏览器验收仍未完成，Ticket 保持 open。

同日完整 pipeline 复验继续通过 10 项，包含该祖先分页合同及 Search/Run Detail 主链路；未改变“跨页定点滚动、虚拟列表、浏览器验收”仍未完成的范围判断，Ticket 保持 open。

2026-11-19：在新建隔离 `_test` schema 安装当前观测 DDL 后重跑完整 `tests/integrated/observability/test_mysql_pipeline.py`，12 passed（203.95s）。本轮重新验证 Search/Run Detail、超过32条事件/资产分页、祖先 continuation、Links/迟到投影、性能/容量阈值和 Source 授权；控制 schema 含预置5张观测表，测试结束后显式删除并查询确认不存在。UI 跨页命中定点滚动、2000节点虚拟列表及 Chromium108/360/嵌入验收仍未完成，Ticket 保持 open。

同日继续：在真实 MySQL Search/Run Detail 合同中串联搜索命中与祖先 API，命中 SubAgent Span 后按同一 Run/Source 获取 `[命中 Span, parent Span]` 路径，并验证 manager 作用域；该合同 1 passed（65.30s），控制 schema 删除并确认不存在，目标 pipeline pre-commit 通过。前端定点滚动、虚拟列表和浏览器验收仍未完成，Ticket 保持 open。
