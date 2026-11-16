# 独立 Agent 可观测：决策树

Status: open

当前阶段：设计树已收敛，无新增决策前沿；[最终方案](../../docs/superpowers/specs/2026-11-15-independent-agent-observability-design.md)等待用户统一确认。
Type: grilling
日期：2026-11-15

## Notes

[当前设计](spec.md)；[ADR 0047](../../docs/adr/0047-independent-agent-observability-uses-metadata-logs.md)；[能力蓝图](../../Agent_可观测增强设计_Span与五大能力.md)。前轮 SDK/旧追踪整合建议已撤回，不能作为本方案依赖。

## Decisions-so-far

| 编号 | 用户确认 | 状态 |
|---|---|---|
| Q1 | 独立方案、独立逻辑、全新增埋点输出元数据日志；不改、不接入旧 SDK/旧追踪/旧埋点/旧存储查询 | resolved |
| Q2 | 第一版面向授权 Source 运营人员与系统管理员 | resolved |
| Q3 | P0 为主对话/专家主执行及后台 SubAgent 基础关联和终态；Cron/独立 Workflow 为 P1 | resolved |
| Q4 | 新 Run 为一次用户问题从受理到终态，不是整个会话或 Goal；不改变旧身份契约，新方案自主管理观测身份 | resolved |
| Q5 | 新日志仅元数据，正文根据业务定位从 NAS 授权查询展示；不修改现有 SDK 的任何内容策略 | resolved |
| Q6 | 新详情优先保护业务延迟，允许有标记降级，不承诺 Span 零丢失；完整统计另明确来源和确认机制 | resolved |

用户强调原文：“此次开发可观测是独立逻辑、独立方案，和已有逻辑和 sdk 没有任何关系。”该边界约束后续全部设计、实现、测试与发布。

已写 GLOSSARY：Independent Agent Observability、Observability Run、Observability Metadata Event、Observability Content Evidence。

## Facts resolved after Round 1

- NAS 保留已提交会话正文与恢复内容，不保证每次完整模型请求；临时 hint 可刻意不持久化，工具结果可在保存前压缩。
- 正文定位需 service_unit/tenant/source/agent/Chat/问题等业务作用域；重复 Msg.id 需 occurrence 关联。归档消息不能只靠在线 answer-turn 接口。
- 业务元数据 MySQL 与 NAS locator 是正文授权读取基础，不是旧可观测逻辑。NAS 文件存在不延长已删除/无权内容的可见性。
- 普通 swe logger 的队列/级别/handler 不是独立元数据出口；Supervisor 默认重定向 stdout/stderr 到文件。采集由用户处理；索引/存储/检索由本项目设计。

## Round 2 — 已确认

| 编号 | 用户确认 | 状态 |
|---|---|---|
| Q7 | 当前 SWE/Console 内独立后端模块、独立 API/页面；不新增必须单独部署的服务，不接旧 Monitor/Tracing 接口 | resolved |
| Q8 | 专用 logger、独立队列、单行 JSON 输出 stdout；部署侧采集方案、实现与验收均不在本项目范围 | resolved |
| Q9 | 仅展示现有 NAS 已保存正文；未保存、压缩或不可用如实显示，不新增正文副本 | resolved |
| Q10 | Run 终态不可重开；未终态原问题的重试/审批恢复沿用 Run，终态后重执行或新问题新建 Run；重连不新建 | resolved |
| Q11 | 用户人工处理日志采集入库；本项目必须设计独立索引、存储、日志入库契约，并完成其余查询/API/展示；不能把索引/存储设计推给外部平台 | resolved |
| Q12 | 允许只读会话/SubAgent 业务元数据确定受理数和终态，日志用于明细/性能并标覆盖；不读旧追踪 | resolved |

## Facts resolved after Round 2

- SWE 已有通用异步 MySQL 数据库层，和旧可观测没有专属关系；会话建表使用人工 SQL、scope 前缀索引、稳定游标分页、TEXT 序列化元数据。生产兼容版本仍需实库确认。
- 现有源码不能证明已部署通用日志 ES/OpenSearch 平台，不据此默认复用。
- 现有角色来自宿主 manager/isSuperManager 并映射 manager/admin；后端不少接口直接读角色 Header，未核实存在 Source 成员 RBAC/可信角色签发体系。新模块必须明确角色的可信来源和 Source 范围，不能只以菜单隐藏鉴权。

## Round 3 — 已确认

| 编号 | 用户确认 | 状态 |
|---|---|---|
| Q13 | 独立 MySQL 表与索引、独立连接配置；不增加 ES/OpenSearch | resolved |
| Q14 | 本期不考虑数据清理；元数据存数据库，不设置30天TTL、不建设自动清理/归档任务 | resolved |
| Q15 | Attempt 是同Run的一次连续执行；Agent层重执行/审批后恢复新Attempt，模型内部重试不更换Attempt，重连不增加Attempt | resolved |
| Q16 | 沿用manager/admin，manager限制授权Source，admin可显式跨Source；不建设角色管理系统；可信身份接入仍需明确 | resolved |
| Q17 | 同范围可观测访问者可以读NAS正文，不另建正文角色；读取仍校验归属/删除/脱敏，不提供原始文件下载 | resolved |
| Q18 | 默认关闭，新Run准入固定是否采集，后续Attempt/SubAgent继承；开关变化仅影响新Run | resolved |

## Round 4 — 已确认

| 编号 | 用户确认 | 状态 |
|---|---|---|
| Q19 | 新Run独立表达waiting_approval，不照抄业务Turn completed；批准后同Run新Attempt，不改业务状态 | resolved |
| Q20 | 缺终态/长期未更新只标unknown或partial，业务明确裁决后才判失败/取消/超时；子任务晚结束不重开父Run | resolved |
| Q21 | 审批记录与SubAgent启动快照可以携带新增obs_context，仅元数据，不依赖人工日志入库来传上下文 | resolved |
| Q22 | 使用一个全局采集开关，不按Source配置；仍默认关闭，Run准入固定采集决定 | resolved |
| Q23 | P0手动刷新/有界轮询，不新增实时推送通道 | resolved |
| Q24 | 首期验收正确性、权限隔离、资源有界和可复现容量报告，生产规模/SLA按真实数据校准 | resolved |
| Q25 | 按照项目已有身份判定，不新建SSO、角色发行、上游验签或独立信任系统；新API仍执行已确认manager/admin与Source过滤 | resolved |

## Design Convergence

Q1–Q25已确认。没有新增必须用户选择的产品前沿；以下按已确认边界给出明确工程默认，最终统一评审：

- 全局开关使用SWE_AGENTOBS_ENABLED=false，各实例统一后台配置/现有发布重启生效，不建设网页热切换；manager/admin仅查询，开关不按Source分级。
- 待审批保持waiting_approval；失联/缺日志只标unresolved/partial，不补造终态、不阻塞后续独立问题。
- 成功率只按可确认归并的逻辑Run统计，业务Turn总量和unresolved另列；不宣称可丢日志也能保证全量逻辑Run统计。
- 全类型安全兜底、Events/Links、可信资产含Prompt元数据、P95/Loop/热点/失败率纳入已承诺P0；评测、价格成本与跨执行对比保留后续。
- 入库只写inbox，归并器维护其它表；非法非元数据payload在校验处置中清空，只保留安全原因，不建立永久违规正文副本。合法元数据不做清理。
- 后台SubAgent沿用root obs_run_id，用独立子操作和业务subagent_run_id表示自身终态，不重开根Run。

## Decision Tree

- 已定独立模块/stdout/人工采集入库/独立MySQL → 事件表/查询表/幂等归并器/入库样例 → 查询/API与性能验证。
- 已定本期不做数据清理 → 保持入库元数据 → 查询窗口/迟到事件/业务删除后统计覆盖；不增加TTL/清理任务。
- 已定 Run终态不重开与Attempt边界 → 业务挂起/取消/超时/失败映射、进程中断与SubAgent生命周期。
- 已定manager/admin与同域正文权限，沿用现有身份判定 → 新API范围检查/跨Source与NAS拒绝验证，不增加新身份接入前置条件。
- 已定全局开关+新Run快照 → 配置入口最终确认 → 审批上下文保持/跨进程上下文/关闭不串写。
- 上述确认后 → 日Run/Span量、峰值、节点上限/查询时延预算、TTFT与分位口径 → UI取舍和验收 → 词汇/必要ADR → 用户确认共同理解后实施。

## Implementation Progress

- 01 已完成并由子代理检视：独立事件/上下文/埋点内核、元数据白名单writer和埋点矩阵。详见 [ticket 01](issues/01-instrumentation-core.md) 与 [instrumentation matrix](instrumentation-matrix.md)。后续首个可领取票为 02；其余票仍按现有依赖阻塞。
- 02 的实现与代码检视已完成，代码已通过单测和前端构建；ticket保持claimed，因为目标MySQL 8.0.21+实库与 Chromium 108/360 验收环境当前不可用。03–15 仍受 02 阻塞。

## Facts resolved after Round 3

- 等审批会让业务Turn正常completed；批准创建新业务Turn，因此Run必须独立结算，业务Turn计数不等于逻辑Run数。
- pending.extra可定位产生该审批的Chat/msgid，但连续审批不是根问题；审计持久化best effort且服务无完整重启恢复读取。不能依赖人工日志已入库来传下次Attempt的观测上下文。
- 进程恢复需业务owner停止/IO drained等证明；观测超时不能替业务判失败。
- 后台SubAgent可在主执行结束后继续，父Run不应因此重新打开。

## Verification Limits

- 数据库已定独立MySQL，独立连接配置；物理库名、目标版本与容量须配置/验证，不另引入ES。
- 生产日量级、峰值与时延预算未知；本期不做清理，测试环境8.0.46不是生产版本证明。
- 身份机制按用户要求沿用现状；不宣称现状增加了密码学验证，也不把新身份体系作为交付阻塞。
- 业务删除后“全历史不可变统计”未获授权；当前全量指所选窗口内可查的业务事实，日志指标另标覆盖。
- 不设计/实施/验收部署侧日志采集；但表/索引/幂等/归并/查询契约必须完整交付。

## Comments

2026-11-15 第一轮：明确独立元数据日志 + NAS 正文，已记录 ADR 0047 与词汇；撤回 SDK 方案及相关文档修改。

2026-11-15 第二轮：Q7–Q12 已按用户回答确认。采集与入库操作排除；索引/存储设计、独立查询与展示包含。Run 终态不重开，统计只读业务元数据。

2026-11-15 第三轮准备：已按Q11拆出 storage-and-query-design.md，明确用户只需写原始事件，派生归并不暗中转嫁给用户；存储、保留、Attempt、权限与开关提出Q13–Q18。

2026-11-15 第三轮确认：Q13–Q18已记录。Q14明确替代30天建议：元数据保留数据库，本期不做清理。Attempt、角色、正文与开关规则均确认。

2026-11-15 第四轮准备：补充lifecycle-and-api-design.md，查明审批Turn与Run不一一对应；提出Q19–Q25，以明确独立状态结算和有限验收边界。

2026-11-15 第四轮确认：Q19–Q25全部记录；Q22改为单一全局开关；Q25沿用已有身份判定，不引入新身份体系或部署接入前提。准备最终文档收敛。

2026-11-15 设计收敛：无新增产品追问。全局环境开关、现有身份、已确认Run统计/未关联单列等工程默认已写最终方案；待用户统一确认共同理解后再实施。
