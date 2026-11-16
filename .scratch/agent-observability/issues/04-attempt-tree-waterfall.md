# 04: 展示Attempt与Agent执行树、同行瀑布

Status: open
Type: task
Blocked by: 03
Triage: ready-for-agent
Priority: P0

**What to build:** 运营人员打开Run后，可按Attempt查看真实Agent操作树和同一行对应的时间瀑布，选中节点即看到基础Inspector，并能辨认运行中、不完整和未知状态。

**Blocked by:** 03：展示真实问题的Run生命周期与采集状态

**Status:** ready-for-agent

依据已确认的独立可观测设计、Trace视图对照、领域词汇及ADR 0047/0048。与旧SDK、旧埋点、旧追踪ID和旧可观测存储查询没有运行依赖；只输出元数据，正文仅经现有业务授权从NAS读取。采集由用户处理，本票不增加ES、TTL/清理或新身份体系；授权仍沿用项目已有身份判定。

- [ ] 真实连续Agent执行生成Attempt与Agent操作；Agent层重执行形成新Attempt，模型重试和重连不形成新Attempt；Attempt序号由根执行拥有者推进且不会与worker争用。
- [ ] Run/Attempt导航使用独立身份，Trace仅为执行链路视图称谓，不创建第三套trace_id或Trace表，不伪造导航Span。
- [ ] 树和瀑布共享选中、展开和固定高度行模型，按真实parent关系和(started_at,span_id)稳定排序；基础分页给窄行而非整段metadata。
- [ ] 基础Inspector展示安全name、类型、operation、业务/技术状态、身份、起止和质量；技术错误与业务结果分离，未知类型安全回退，不伪造未发生的Loop/Context/Checkpoint节点。
- [ ] 使用UTC微秒时间及安全相对偏移；单调duration和墙钟不一致要提示，进行中截至服务端观测时刻，缺end但业务不明不永远声称running。
- [ ] 基础响应受分页/字节预算限制，已加载部分不宣称全树；没有父事实时如实标记，不按名称、时间或层级猜父子。
- [ ] 深链接和列表返回保留选择及必要位置，轮询有界、隐藏暂停、可手动刷新；复杂跨页定位增强由后续票完成。
- [ ] 完成真实Agent→日志人工入库→投影→树/瀑布/Inspector测试，并验证Chromium108、当前浏览器、窄屏面板和hideMenu=true。

验收环境不可用时必须明确记录未验证项，不以构建成功或新浏览器模拟替代真实Chromium108验收。

## Comments

2026-11-15：用户已确认15张票的拆分及阻塞关系，现发布为本地实施事项。尚未领取或开工；本次发布不构成功能开发授权。

2026-11-16：开始实施 Ticket 04。新增授权 `GET /agent-observability/runs/{run_id}`，返回 Run、Attempt 和有界 Span 页面；查询先按 manager/admin Source 范围确认 Run，再读取详情，树排序使用数据库 `started_at,span_id` 稳定顺序。Console Run 行可打开固定宽度 Inspector，展示 Attempt 状态、Span 父关系缩进、操作类型、状态和已知时长，并明确已加载节点受分页限制。后端 observability 34 passed，Console typecheck 与相关 Vitest 8 passed；当前浏览器 Chrome 157 的 hideMenu/窄屏检查已在 Ticket 03 记录，Chromium 108.0.5359.95 仍未验收。

本票仍保持 `open`，因为 Ticket 03 的真实专家主执行和精确 Chromium 108.0.5359.95 验收尚未完成；本次代码作为依赖闭环的预备实现提交，不将其标记为已领取或已解决。
