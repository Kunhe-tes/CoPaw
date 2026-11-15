# 独立 Agent 可观测设计：元数据日志、MySQL 与 NAS 正文

日期：2026-11-15
状态：设计待最终确认；Q1–Q25 已确认，尚未开始实现或执行建表。
决策：[ADR 0047](../../adr/0047-independent-agent-observability-uses-metadata-logs.md)、[ADR 0048](../../adr/0048-independent-observability-metadata-uses-mysql.md)。
背景：[能力蓝图](../../../Agent_可观测增强设计_Span与五大能力.md)、[逐轮决策](../../../.scratch/agent-observability/map.md)。本文为收敛后的实施设计入口；过程草案只用于核查证据。

## 1. 已确认范围

本方案与 swe.tracing、AgentTraceSDK 及其埋点、配置、身份、输出、表、查询均无运行依赖；不升级、替换、迁移或兼容读取旧可观测。新增业务边界观测可位于同一业务代码，但不改旧埋点逻辑、异常/重试/流式行为。

| 范围 | 决定 |
|---|---|
| 应用 | SWE 内独立模块/API，Console 独立页面；不另起必须部署的服务 |
| 产出 | 专用 logger/有界队列，单行 JSON 写 stdout，仅元数据 |
| 入库 | 用户负责人工采集入库；本项目提供 schema、DDL、INSERT 示例、投影与查询，不设计/实现/验收采集器 |
| 存储 | 独立 MySQL 表/索引、独立连接配置；不增加 ES/OpenSearch |
| 清理 | 本期不做合法元数据清理、TTL、归档/分区淘汰任务 |
| 正文 | 只从现有 NAS 正文经业务定位授权读取，不新增正文副本 |
| 身份 | 沿用现有身份/manager/admin 判定；manager 当前 Source，admin 显式跨 Source；同范围可读正文 |
| 开关 | 单一全局开关，默认关闭；新 Run 准入快照，后续 Attempt/SubAgent 继承 |
| P0 执行 | 主对话、专家主执行、后台 SubAgent 基础关联与终态；Cron/独立 Workflow 放 P1 |
| 质量 | 优先业务响应、允许有标记降级，不承诺 Span 零丢失 |
| 刷新 | 手动刷新/有界轮询，无新实时推送通道 |

全局开关工程默认采用 SWE_AGENTOBS_ENABLED=false，所有 Pod 统一后台环境配置，按现有发布/重启方式生效；不提供网页热切换和按 Source 覆盖。全局指此应用部署统一策略，不承诺跨 Pod 瞬时原子切换。数据库配置 SWE_AGENTOBS_DB_* 独立解析，不回退到业务/旧追踪连接；只读能力接口不暴露密码。日志输出不依赖数据库连接成功。

## 2. 链路与模块

```text
真实业务边界 → 独立 obs_context → 白名单元数据 → 有界日志队列 → stdout JSON
                                                        │
                                  用户负责采集并 INSERT inbox
                                                        ↓
独立 MySQL inbox → SWE 内投影任务 → events/runs/attempts/spans → 独立 API → Console
                                                                   │
                                              业务授权/元数据定位 → NAS 正文
```

建议新增 src/swe/observability/{context,models,emitter,config,instrumentation,projector,store,query,content,router}.py，以及 console/src/pages/AgentObservability/、独立 API/types。命名不强迫建立空文件，按实际职责合并小模块。通用 DatabaseConnection、现有身份工具、会话正文读能力可复用；旧可观测代码不可作为依赖。

采集端从业务装配挂新观察点：主请求受理/结算、Agent 连续执行、真正模型调用、模型层实际重试尝试、实际工具执行、guard/审批、SubAgent 启动/worker 结算。新观察失败只记安全计数，不能改业务参数、吞异常、重复调用模型/工具或延迟取消。

## 3. 领域身份与状态

- Observability Run：一次根用户问题从受理至终态。新问题或已终态后的重执行新建 Run，可记录 predecessor；重连不建 Run。
- Attempt：同 Run 的一次连续 Agent 执行。Agent 层重新执行/审批恢复新建 Attempt；模型层 retry 不换 Attempt。
- Span：真实操作区间。业务类型与技术 kind/operation 分开；只在实际发生且值得计时时生成。
- 新 run/attempt/span/event ID 使用 UUIDv4 小写规范格式，自主管理，不读取或映射旧 Trace ID。业务定位保留 service_unit/tenant/source/agent、Chat、根 question_msgid 等，原值按字节精确匹配。
- 后台 SubAgent 沿用根 obs_run_id，以独立 Agent 子操作和业务 subagent_run_id 标识自身生命周期，不另造会重开根 Run 的第二套根结算。

| 对象 | 状态 | 结算边界 |
|---|---|---|
| Run | accepted/running/waiting_approval；succeeded/failed/cancelled/timed_out/rejected | 终态不可重开；没有明确业务原因不推断超时/失败 |
| Attempt | running；succeeded/failed/cancelled/timed_out/waiting_approval | waiting_approval 为该连续片段结束，不是 Run 终态 |
| Span | running；succeeded/failed/cancelled/timed_out/rejected | 子失败可被恢复，不自动传播为根失败 |
| 数据质量 | unknown/partial/unresolved/conflict，加具体原因 | 与业务状态独立，缺日志不等于业务失败 |
| 正文 | available/pending/not_saved/compacted/unavailable | 无权/不存在对外一致，不能泄露存在性 |

**审批特殊规则**：现有审批提示会让业务 Turn 正常 completed，批准后新建业务 Turn；新 Run 必须保持 waiting_approval，不能照抄 completed。pending 及 worker 启动载体带新增 obs_context：schema、根 Run、根问题、capture_enabled、run_started_at、前驱 Attempt 与本次审批 request_id。仅元数据，不带正文/权限凭证。连续审批沿关联链保留根问题，不按 session 最新消息猜。独立上下文不等待人工日志已经入库。attempt_index由单问题执行所有者在obs_context中推进，重复批准沿既有业务幂等复用同Attempt；后台worker不分配根Attempt序号。

审批记录本身丢失/重启不可恢复、或日志关联不全时，标 unresolved/unknown，不擅自恢复业务或补判失败；后续独立问题可新开 Run，不被旧观测等待阻塞。明确拒绝、过期、取消按实际业务结果结束。后台子任务晚结束只更新子操作及后台概况，根 Run 终态和结束时间不变。

## 4. 元数据事件协议 v1

UTF-8 单行 JSON；schema_version=1，命名空间 agentobs。完整单行最大 24 KiB；先白名单投影再按序列化字节预算裁剪可选元数据，保留必需身份和生命周期。必需字段不可保留时丢事件并计数，不输出无效 JSON。数组默认不超过32项，嵌套深度不超过4；截断用明确标志/原因，不截 JSON 字符串中间。

| 字段组 | 内容 |
|---|---|
| 固定头 | schema_version、event_id、event_name、occurred_at、producer_id（进程启动身份） |
| 身份 | obs_run_id、适用时 obs_attempt_id/obs_span_id、parent_obs_span_id |
| 生命周期键 | entity_kind、entity_id、phase_key、local_seq；序号只在拥有者局部有效，不是跨 Pod 全局时钟 |
| scope | service_unit_id、source_id、tenant_id、agent_id；缺业务作用域显式不支持，不填假身份 |
| 业务引用 | chat_id、root_question_msgid、run_started_at、capture_enabled（每个Run生命周期事件都带）、当前问题/turn、approval_request_id、subagent_run_id（适用时） |
| 操作 | span_type、operation、kind、受控 name、start/end、status、reason_code、attempt ordinal |
| 度量 | duration_us、首有效chunk/首可见文本延迟、已知tokens、loop/tool计数；未知 null |
| 关系/资产 | 安全 Events、Links、cause/recovery、可信模型/Tool/Agent/Skill/Prompt ID与版本/签名 |
| 质量 | start/end证据、metadata_truncated、context_missing、usage_known 等独立信息 |

事件名：run.accepted/run.state/run.ended、attempt.started/attempt.ended、span.started/span.ended、approval.requested/approval.resolved、subagent.started/subagent.ended、asset.used、observer.health。observer.health为全局诊断元数据，允许无Run/scope，使用进程启动observer实体UUID与health序号；仅admin能读取全局诊断，manager不得查跨Source健康事件。其它生命周期事件必须完整Run/scope，不能借可空列绕过校验。结束事件携带操作起始时间、终态、完整有界汇总，即使 start 丢失也可展示 partial。每个事件固定生命周期槽：(entity_kind,entity_id,phase_key,local_seq)，重传槽与event_id保持；不同event_id重复同槽不重复计数，同槽冲突标记而非最后到达获胜。

元数据禁止正文：问题/回答、messages/prompt、工具参数/结果/说明/schema、检索Query/片段、URL query、文件文本、原始异常消息/堆栈、人工自由文本理由、密钥。错误只记受限 error.type/phase/code 与 cause/recovery ID。名称来自注册/配置且限长，不接受用户输入或任意 repr。当必须正文解释时查 NAS；NAS 没保存就不可用。

**类型兼容**：13类业务类型注册显示；P0真正埋 Agent/LLM/Tool、存在的guard/审批阶段及SubAgent基础节点。Skill只有资产使用则为事件；无真实RAG/Workflow生命周期不造空节点。未知业务类型受限显示Custom；未知属性不任意透传，支持版本内安全字段可保留，非法/未知载荷隔离为安全原因。原蓝图“未知字段不丢”不得突破元数据边界。

## 5. 日志与资源边界

专用logger不挂swe handler，不继承普通日志级别/队列/formatter；propagate=false，异步线程单写stdout。默认队列4096条且总预算8MiB，包含in-flight；满则非阻塞丢事件并累加安全计数，后台有机会时输出observer.health。关闭最多等待1秒排出并报告未确认数量；进程强杀仍可能丢失，不能保证计数摘要本身必达。

这些是可配置工程初值，不是性能SLA。不开逐token日志、不每chunk序列化累计正文；只在内存保存少量计时/Usage元数据，按Provider累计快照取最终Usage不逐帧相加。关闭采集的新Run不深拷贝/投影正文，不尝试连接观测DB。已开启Run的后续Attempt和SubAgent继续继承快照。

## 6. MySQL、入库与投影

设计基线 MySQL 8.0.21+、InnoDB DYNAMIC、16KiB页和strict mode；实际MySQL/TDSQL必须实库验收。DDL由人工预建，应用只检查readiness，不启动时CREATE/ALTER。时间UTC DATETIME(6)，业务身份VARBINARY精确值，新UUID为ASCII CHAR(36)，扩展为应用校验TEXT，不存正文、不设TTL。

[DDL草案](../../../.scratch/agent-observability/schema-draft.sql) 定义五表：

| 表 | 写入者 | 核心用途/索引 |
|---|---|---|
| swe_agentobs_inbox | 用户INSERT，投影器更新状态 | payload_text；(processing_state,ingest_id)领取pending |
| swe_agentobs_events | 投影器 | event_id主键、生命周期槽唯一；按run/实体、scope/时间查安全Events |
| swe_agentobs_runs | 投影器 | scope/时间、根问题定位、独立Run结算、质量 |
| swe_agentobs_attempts | 投影器 | Run+Attempt序号/自身ID，连续执行及恢复关系 |
| swe_agentobs_spans | 投影器 | Run+开始/父节点、类型/模型/工具/错误受限筛选 |

用户最小INSERT只带payload_text，数据库默认生成ingest_id、received_at、pending；[事件样例](../../../.scratch/agent-observability/events.example.jsonl) 给出对应JSON。用户无需维护派生表或投影版本。重复导入inbox允许，规范events层幂等。

投影器是现有SWE生命周期内独立后台任务，独立连接池与事务，不继承业务事务。READ COMMITTED下每批最多32条pending，SELECT ... FOR UPDATE SKIP LOCKED，逐行保存点校验/归并；处理和标processed同事务。失败回滚仍pending，不用MAX(id)游标永久跳过晚提交的小ID。坏事件清空payload仅留安全原因和ID；这是入库校验处置，不是合法元数据按龄清理。规范化成功后inbox.payload_text置NULL，安全事件仅在events保存一份；inbox保留元数据处理记录。槽内容比较排除event_id和入库字段，比较其余规范语义；相同槽换event_id的重传不重计。

事件上下文必须携带根run_started_at和capture_enabled，用于accepted丢失时创建partial根视图，不以子Span开始时间冒充根开始。缺Attempt自身事实时保留Span的attempt引用并标关联未齐，不伪造Attempt序号/起止。全局observer.health仅写规范events而不创建runs。

同一Run归并先创建/锁runs行，固定加锁顺序run→attempt→span；唯一槽与event_id同时校验，scope/根问题/父身份不可变。重传不重复加tokens/调用数；汇总基于唯一操作终态重算/差量替换，不能盲加每条end。并发死锁整批有界重试；冲突终态质量标conflict，保留事实并从明确业务结算校正，不按入库先后选择真相。子操作晚到不回滚根终态。

MySQL锁队列用法依据官方[Locking Reads](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking-reads.html)；索引按[最左前缀规则](https://dev.mysql.com/doc/refman/8.0/en/multiple-column-indexes.html)设计。SKIP LOCKED只用于待处理队列，不用于用户需要一致结果的列表查询。具体隔离级别/超时/死锁须实库验证，当前未执行DDL。

## 7. 正文与统计的事实边界

NAS保存已提交会话/恢复消息，不保证每次原始模型请求：临时hint不持久化，工具结果可已压缩。读取经service_unit/tenant/source/agent/Chat/消息occurrence定位MySQL publication，再pin/限量读NAS；不用日志绝对路径、不扫文件找最近消息。在线与归档精确定位均需支持，现有answer-turn只查在线不能冒充完整归档解析。每次鉴权/删除检查及展示脱敏，正文不回写日志或新数据库，不新增原始下载。

统计分三类，API和UI始终标population/window/generated_at：

1. 当前可查询的业务受理问题/Turn/SubAgent数量与状态，只读业务元数据，不受日志采样影响，但不等于逻辑Run全量分母。
2. 可确认关联/结算的逻辑Run成功率；审批归并缺失的unresolved单列，不混入成功率分母，不承诺删除后不可变全历史审计。
3. 已观测的操作/性能分布，标span数量、start/end完整率、Usage已知覆盖；无日志业务问题标not_collected，不伪造Run身份。

业务DB与独立观测DB/NAS没有跨库原子事务；各自读取/投影截至信息显式返回。日志未出现无法区分未采集/未入库/丢失时标unknown，不给虚假的精确采集延迟。

## 8. 五大能力与指标口径

| 能力 | P0 | 降级或P1 |
|---|---|---|
| 过程可观测 | Run/Attempt、真实操作树/瀑布、Events/Links、13类型注册兜底、SubAgent基础状态 | Cron/独立Workflow/P1专项实际埋点；缺父节点标orphan，不猜树 |
| 结果可解释 | 已保存问题/回答/工具正文证据与业务定位、采集范围显示 | RAG答案片段→文档/版本/Chunk只有真实映射才显示；不证明内部推理或答案正确 |
| 过程可追溯 | 实际模型/Provider、Agent/Tool/Skill/Prompt的可信ID/版本/签名 | 外部修订不可得为unknown；版本反查增强/P1，不用当前覆盖历史 |
| 异常可定位 | error分类/phase、cause、recovery、已恢复子错误与根结果分离 | 原始敏感异常文本不进入新日志；无因果证据不强称根因 |
| 性能可分析 | 时长P50/P95/P99、TTFT/首可见文本、Token覆盖、AgentLoop、实际Tool次数/失败率与类型热点、丢弃计数 | TPOT/关键路径/CPU分解、价格成本/质量评测/跨执行对比为P1 |

Run elapsed含审批等待，active time为Attempt活动区间并集；操作duration取本地单调计时。模型逻辑调用与底层运行时重试尝试分别统计，Provider内部不可见HTTP重试不冒充已观测请求。首有效chunk从实际逻辑模型调用到非空输出chunk，首可见文本另计；空启动/usage-only不算输出。stream无输出时延迟null，非流式不伪造TTFT。Usage取提供方真实终态/最新累计值，未知不填0，推理Token不是默认额外加到输出总量。

父子时长不相加，热点按操作类型分组并说明可能并行，P95用明确样本集nearest-rank，不平均各组P95。不采用隐蔽抽样：初值每次聚合最多读50000个满足过滤的已结束样本；超出时返回range_too_large提示缩小窗口，不默默抽前N条。取消、失败、成功的耗时分布可分开筛选，已恢复失败的工具仍计工具失败但不计Run失败。

## 9. 新 API 与页面

前缀/agent-observability；所有数据API先应用现有身份判定和服务端manager当前Source/admin显式Source过滤，普通用户403，越界详情/正文与不存在统一404。admin跨Source须明确all_sources或列表，默认不自动全库。service_unit由后台允许范围约束，不让客户端任意指NAS根。

- GET /capabilities：全局配置快照、只读可用性，不返回连接秘密。
- GET /runs、GET /runs/{id}：分页列表、摘要/关系/Attempt。
- GET /runs/{id}/spans、GET /runs/{id}/spans/{span_id}：共享行模型、事件/Links/安全Raw、资产和性能。
- GET /runs/{id}/content：以受控证据键查询已保存正文，默认32KiB、最多256KiB，每次鉴权；截断/分页明确。
- GET /overview：业务总体/确认Run/观测性能分别给口径和质量。

游标携带版本/过滤指纹/授权scope/稳定最后键，用MAC防改，scope每次重验；不复用业务会话cursor的秘密。列表默认24h、50条，最多200条；单次范围最多31天但可明确选择任意历史窗口，不清理数据。Span分页默认200、最多1000，旧页已加载节点不宣称整树完整，缺父提供安全祖先摘要或标orphan。服务查询默认5秒超时，超限返回可重试/缩小范围，不影响Agent。

Console使用独立“Agent可观测”入口：上方筛选/数据质量，执行列表，详情共享Tree+Waterfall行模型，Inspector含Overview、Evidence、Assets、Errors、Performance、Events/Links/Raw。总览嵌在同页面，不铺大量孤立页面。尝试/审批/后台状态各自可见。手动刷新及运行/等待时5秒轮询，页面隐藏暂停、终态停止自动轮询，可手动查晚到日志。

外观以console/DESIGN.md为唯一规范，不照搬第三方主题。真实Chromium108与当前浏览器验证独立滚动、长列表、键盘选择、1280/1440宽度和hideMenu=true；窄屏Inspector改抽屉。不得无回退使用subgrid/Popover；滚动条需webkit样式，保持原有壳层语义。

## 10. 实施顺序与验收

1. 独立协议/全局配置/上下文/输出：关闭零正文工作量、队满不阻塞、取消不变、JSON白名单/UTF-8限额；旧可观测无导入依赖。
2. MySQL DDL/readiness/inbox投影：样例导入、重复/不同ID同槽/冲突、乱序、并发、晚提交小ID、事务回滚；先实际数据库验DDL/索引。
3. 主请求/模型/工具/审批/SubAgent观察点：正常链、未请求模型的短路、内部retry、审批跨Turn/重复批准、流中取消、背景晚结束、新旧开关组合独立。
4. 读API/NAS/统计：manager/admin/普通用户、scope冲突、归档/已删除/未保存/压缩/迟提交、Usage缺失、已确认分母/unresolved；数据库不可用不影响业务。
5. Console与容量报告：查询计划、P50/P95/内存/CPU、节点数和数据量有实测记录；真实Chromium108+当前浏览器验收。生产TPS/全局采集延迟不编造，采集不在验收内。

本期不交付：采集代理/部署日志路由、旧追踪迁移/修复、ES、TTL/清理、SSO改造、新实时推送、模型完整Prompt副本、确定性重演、未确认的计费和评测。最终共同理解确认后才实施。
