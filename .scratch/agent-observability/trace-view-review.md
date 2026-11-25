# Trace 视图与独立可观测设计对照评审

日期：2026-11-15
状态：设计修订；未实施代码、未执行 DDL。
输入：[视图方案](../../docs/Agent_Observability_Trace_视图设计方案.md)、[实施设计](../../docs/superpowers/specs/2026-11-15-independent-agent-observability-design.md)、[DDL](schema-draft.sql)、[事件样例](events.example.jsonl)。

## 1. 结论与不可变边界

**需要调整存储投影、索引和埋点字段契约，五表架构足够，不需要增加 Trace 表。** 视图的 Tree + Waterfall 同行模型可直接采用；其 OTel 数据源、Trace 身份、正文采集和成本列不能直接成为本方案的采集契约。Q1–Q25 和 ADR 0047/0048 仍优先：独立模块、独立新 ID、独立元数据日志、独立 MySQL 连接和五表；无旧 SDK/OTel 运行依赖；只通过现有业务定位读取 NAS 正文；不设计采集器、不加 ES、不做清理、不改身份体系。

当前交付物已合入仓库根目录；原 `.worktrees/conversation-mysql-nas/` 路径已不存在。本次修订作用于当前分支同名文件。视图原稿是对照输入，保留原文；以下适配约定为本方案的落地契约。

## 2. 逐项差异

| 视图要求 | 原设计缺口或冲突 | 本次修订 |
|---|---|---|
| §3/§10 Run 对应多个 Attempt/Trace | 独立协议没有 trace_id，不能偷用旧 SDK ID；视图同时写列表按 Run 和每行进入 Trace | 列表每行一个 Run；详情内选 Attempt。Trace 仅作连续执行视图称谓，稳定地址使用 run_id + attempt_id，无第三套身份/表 |
| §4 完整 ID、Session 精确查找 | session_key 有列无访问索引；无明确 Trace ID 映射 | 列表按显式Run/Attempt/Session类型精确查找；Span走已知Run下深链接；不接受旧Trace ID。新增Source+Session索引，仍验证完整scope和原值 |
| §4 Agent/状态/最短耗时/耗时排序 | scope_time 在缺 tenant 等值时不能有效支持 Agent 筛选；耗时无索引 | 新增 Source+Agent+时间、Source+duration+Run 索引；组合过滤仍有工作量预算/超时，不能宣称每种组合都走同一个索引 |
| §4 结果总数、成本 | 无全量精确计数预算；成本在原范围为 P1 | P0 返回 has_more，不默认 COUNT 全库；成本隐藏或 unavailable，不能按当前价格回算历史 |
| §5 顶部 Span/错误数 | 仅 llm/tool 计数，错误数缺投影口径 | Run 增 span_count/error_span_count；标记 observed、summary 覆盖和 as_of，后台晚到可变，根终态不变 |
| §5/§8 name、业务状态与技术状态 | operation 无安全展示名；单个 status 容易混用 | Span 增 name、technical_status、has_error；业务 status 不推导技术错误，子错误不污染根结果 |
| §6 同行瀑布/跨机器时间 | DATETIME(6) 足够，但没有明确浏览器时间单位、显示窗口与时钟质量 | API 保留 UTC 微秒时间和有界相对 offset_us；不传纳秒 epoch Number；本地单调 duration 与墙钟区间分开显示 |
| §7 事件、Link、错误快跳 | 缺按 Span 的事件访问索引；把数组压到 metadata 会丢掉第33个事件 | 新增 run+span+时间索引；补 span.event 增量事实与独立事件分页，Links 从安全关系事实归一化 |
| §7/§8 类型化 Inspector | step、重试、工具关联、provider/request/response model 和 evidence 字段仅笼统描述 | 补字段字典与真实边界埋点；step_index 列，剩余受控详情在 metadata，不为任意属性建索引 |
| §7 输入输出/异常堆栈/Resource | 原稿建议原始 Prompt、工具参数结果和堆栈；与元数据约束冲突 | IO 仅 NAS evidence；不存在则明确不可用；安全错误分类、受控资源白名单，不上传异常原文 |
| §9/§10 2,000 节点、深链接、全树搜索 | 首200条无法保证首错误/匹配祖先/目标节点在已加载页 | 服务端 Run+Attempt 过滤、错误/受控搜索、定点节点+祖先；区分未加载与真实缺父；共享行模型分批加载 |
| §10 重试、时钟漂移、采样提示 | 模型重试容易误分 Attempt；缺日志容易误报采样或失败 | 模型重试仍同 Attempt，显式 operation 层级；只称 partial/unknown，不推断启用采样；保留时间异常 |
| §11 P0 Loop/Context/Checkpoint | 原埋点 P0 不保证每类均有真实区间 | 仅实际有边界时记录；无区间用真实事件/字段，无该操作则展示不支持，不伪造占位 Span |

## 3. 身份、导航和状态

- UI 路径建议 `/agent-observability/runs` 与 `/agent-observability/runs/{run_id}?attempt={attempt_id}&span={span_id}`；REST 前缀仍为 `/agent-observability`。URL 状态包括授权范围内筛选、排序及选中节点，不含正文、凭据或未签名数据库游标。
- 详情头分开显示 Run 总 elapsed、所选 Attempt 时段、后台子任务状态。Attempt 结束不等于 Run 结束；审批等待可在两个 Attempt 之间展示为真实审批区间或事实，不伪造成一次连续 Agent 执行。
- 后台 SubAgent 的基础节点保留启动 Attempt 关联；它可晚于该 Attempt/Run 结束。它不是第二个根 Attempt；视图窗口覆盖已知子节点边界，不能裁到根结束或重开根。
- Link 指向本方案 obs_run_id/obs_attempt_id/obs_span_id 与受控 relation_type；恢复、前驱、因果和异步关联不会变成普通 parent。进入目标仍重新鉴权，越界/不存在统一不可用。
- `status` 为业务结果；`technical_status=UNSET|OK|ERROR|null` 为本方案独立技术状态枚举，只借用常见名称、不读取 OTel；`has_error=1` 表示有明确技术错误证据，0 表示明确无错误，null 表示未知。失败业务结果、取消和拒绝不自动等同 ERROR。

## 4. 存储修改范围

五表职责保持不变；DDL 尚未执行，可以直接修改草案，不产生迁移脚本或自动 ALTER。

| 表 | 新列/索引 | 理由 |
|---|---|---|
| runs | span_count、error_span_count | 详情头的已观测节点/技术错误数；不是业务全量统计 |
| runs | ix_agentobs_runs_session | 完整 Session ID 精确检索；不做前缀/全文检索 |
| runs | ix_agentobs_runs_agent_time | 当前 Source 内 Agent 筛选，不依赖 tenant 为必填查询参数 |
| runs | ix_agentobs_runs_duration | 已结束且 duration 已知的最短耗时/耗时降序 |
| spans | name、step_index、technical_status、has_error | 安全命名、后续 Transcript 顺序、错误与业务状态分离 |
| spans | ix_agentobs_spans_attempt、ix_agentobs_spans_error | Attempt 行集合、首/下一个错误节点定位 |
| events | ix_agentobs_events_span | Inspector 事件/关系增量分页 |

名称最多128个Unicode字符且仍受整条24KiB限制，只来自受控注册信息，不使用用户文本、命令、SQL或 repr。新字段可空语义明确：未观测 step/技术结果为 null；缺安全 name 时用受控 operation 回退。Run 两个新计数为当前规范投影内唯一 Span 数及 has_error=1 的数量，partial 时是已观测下界；其来源/覆盖放入 metadata 的 summary_quality，不把 missing 当0。跨 Source 的管理员查询逐个授权范围执行同等有界查询再稳定归并，不依赖跳过前导列的索引魔法。

## 5. 查询与埋点闭环

详细字段、分页、质量与验收契约见实施设计新增的“Trace视图适配”章节。事件样例应覆盖：正常、技术失败后恢复、审批跨 Attempt、异步子任务晚结束、缺父、未知 Usage、真实内容引用和独立关系事件。只有日志中的真实业务事实或现有业务存储可证明的内容能进入页面。

### 5.1 样例预期投影（未来实施验收用）

当前30条JSONL只是契约样例，所有业务引用为虚构测试标识，不应对生产NAS解析。重复导入不得改变以下唯一计数，打乱顺序后的最终投影应一致：

| 样例 | 预期 |
|---|---|
| 第一个Run | 1个Attempt、4个已观测Span、0个已知技术错误；正常终态为succeeded。evidence.linked晚到只增加证据事实，不增加Span/调用数 |
| 第二个Run | 2个Attempt、6个已观测Span、1个技术错误；根最终succeeded，第一Attempt以waiting_approval结束；失败Tool仍保留ERROR并有recovered_by关系 |
| 缺父与Usage | 第二Run的LLM缺真实父节点，显示partial/orphan；input/output均未知，不显示0；不能因成功终态伪造完整链路 |
| 后台子任务 | 根结束08:01:06，子任务结束08:01:09；子节点时条可越过根结束，根结束时间仍为08:01:06；子任务start/end不同producer但沿显式所有权交接复用同一Span |
| 正文引用 | 第一个Run的tool_result只携带publication/block业务引用；通过完整scope和当前业务归属解析，不允许凭这些字符串直接读文件 |

### 5.2 关键验收矩阵（尚未实施）

1. Session精确查找与Agent/状态/时间组合；耗时排序混合运行中/未知/已结束；授权后翻页无越界，组合条件超预算明确返回错误。
2. 2,000节点首屏200条、最后一页含首个ERROR或搜索命中；可定点定位并加载祖先，未加载父与真正缺父不同提示；列表和瀑布共享行。
3. 迟到节点的started_at落在已经读取页之前；重建分页后能够出现，不能只用最大时间游标漏掉。
4. 技术失败被恢复、拒绝不带技术错误、无end且业务状态未知、时钟逆序，各自不相互冒充。
5. 第33个及后续事件/Link仍可通过独立事实分页读取；单条/单行派生metadata不超过24KiB，单响应受字节预算限制。
6. 原始Prompt/异常堆栈/正文参数注入不得出现在事件和Raw；NAS读取覆盖归档、删除、压缩、未保存、重复消息ID及跨Source深链接。
7. 同一请求真实重试不新建Attempt；逻辑模型容器和底层请求的Usage不重复求和，内部不可见重试显示unknown。

### 5.3 本次代码核查依据

通过项目CodeGraph核查现有业务边界，没有修改源码：`react_agent.py:2135–2192`包含reasoning重试包装，不能把一次_reasoning简单当成一次物理请求；`tool_guard_mixin.py:2377–2426`存在审批/强制replay短路，不一定调用模型；`tool_output_budget_mixin.py:25–105`实际工具调用后可先压缩再打印/入memory；`conversation_storage/semantic_runtime.py:79–100,124–157`区分重复消息ID的实际出现位置；`session_projection.py:50–104`可引用publication或operation/block，不能假定所有消息都有唯一Msg.id。由此补足真实调用边界、不可逆正文缺失提示和精确evidence_ref，不复用既有追踪包装。

## 6. 仍需实施验证

本次仅修订设计。真实 MySQL/TDSQL DDL、组合查询 EXPLAIN、事件乱序并发、2,000节点端到端交互、Chromium108、NAS 授权/归档读取均未运行。不能以静态通过替代这些验收。部署采集不在本项目范围。
