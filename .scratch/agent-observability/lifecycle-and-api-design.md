# 独立可观测生命周期与 API 草案

Status: open

最终评审入口：[独立可观测实施设计](../../docs/superpowers/specs/2026-11-15-independent-agent-observability-design.md)。本文为过程草案，字段/阈值以最终设计及DDL为准。
Type: grilling
日期：2026-11-15
前提：[主设计](spec.md)、[存储设计](storage-and-query-design.md)、[决策树](map.md)。本文件只设计，不修改业务状态机或任何旧可观测逻辑。

## 1. Run 与业务 Turn 不是一对一

已确认 Run 终态不可重开，审批同 Run 新 Attempt。但源码显示：

- tool_guard_mixin.py:2414-2419,2620-2650 等待审批后ReAct正常退出，conversation_storage/runner_integration.py:539-561 正常流直接结算业务Turn为completed。
- approvals/external.py:529,564-581 批准时先等Chat idle，再以 approval-{request_id} 新建业务问题；Console卡片也走新提交（ApprovalActionCard.tsx:93-99）。
- tool_guard_mixin.py:2216-2223 的pending.extra含产生本次审批的chat_id/msgid，但多次审批时不是最初根问题。审计写入best effort；service.get_request只读内存，重启后pending不保证恢复。

因此新Run不能直接照抄业务Turn的completed。已确认：产生待审批事实时Attempt以waiting_approval结束、Run保持waiting_approval；批准关联同Run新Attempt；明确拒绝/过期/取消由实际业务结果结算，不因查不到pending自动终结。某条业务completed若只是等待提示不是Run成功。该规则由Q19确认。

统计也不能直接COUNT所有业务Turn当Run数：审批合成问题是后续执行载体。业务受理/终态事实保证其可查询范围，新可观测身份与审批关系负责逻辑归并；关联丢失时单独显示unresolved，不将其静默作为独立自然语言问题或成功Run。

## 2. 状态分层建议

| 层 | 非终态/运行状态 | 终态或质量 |
|---|---|---|
| Run | accepted、running、waiting_approval | succeeded、failed、cancelled、timed_out、rejected，仅按真实业务裁决设置 |
| Attempt | running | succeeded、failed、cancelled、timed_out、waiting_approval；Attempt结束不必Run结束 |
| Span | running | succeeded、failed、cancelled、timed_out、rejected；技术状态与业务处置另列 |
| 可观测质量 | pending、partial、unresolved、unknown | 不等同Run业务终态，不通过缺日志推断业务失败 |
| 正文可读性 | available、pending、not_saved、compacted、unavailable | 对无权/不存在不泄露存在性 |

上表是独立API契约建议，字段枚举最终按事件字典统一；不修改现有业务或公共Chat API状态。内部异常恢复、非Stop取消/进程中断只在业务已裁决时映射；没有明确超时原因不能仅凭elapsed_time转timed_out。

业务异常恢复要求owner已停止且IO drained的验证（conversation_storage/recovery.py:22-63,90-127）；新观测只读取已发生结算，不自行触发恢复或替业务判失败。缺end/start、日志滞后、Pod强杀与后台子任务继续都应先表达数据不完整。

## 3. 上下文与采集快照

建议独立obs_context只包含schema、run_id、attempt关系、业务锚点、capture_enabled及有界父节点/关系。它不读取旧Trace ID，不含正文或权限凭证，不从模型可控制参数接受身份。

- 新问题受理生成Run/开关快照；上下文通过新独立ContextVar进出，finally复位，继承task时不能写错所属执行。
- 审批暂挂需要把该元数据快照随pending记录保存/传回；SubAgent需要随启动快照传给worker。原业务执行/审批/权限语义不变。
- 不能依赖手工采集的日志已经入库来恢复下一个Attempt，也不能仅按session最新Run猜。上下文缺失显示unresolved；Q21已确认允许新增这些观测元数据载体。
- 崩溃后原审批记录本身不可恢复时，不许新可观测偷偷恢复业务。已输出Run可保持未确认；重执行按已确认终态边界决定新Run。
- 新开关在Run准入固定；不在每个Span重新读取配置，避免同Run中途切半。Q22已确认是单一全局开关，不按Source配置；使用全局环境配置SWE_AGENTOBS_ENABLED=false，各实例统一后台配置，不提供网页热切换。

## 4. 后台子任务

现有SubAgent进程正常可超出父业务轮次生命周期；明确Stop才取消对应子任务（supervisor.py:645-709、coordinator.py:290-293,333-364）。新Run结算不等待所有后台worker，也不重开父Run。子任务基础状态/终态以其业务run记录为事实，元数据可晚到。UI可同时显示“主执行已结束”和“后台子任务运行中”，不伪造跨时钟串行瀑布。

## 5. 独立 API 建议

拟采用 /agent-observability 前缀，前端页面独立命名和菜单，不代理旧Tracing。具体路径可按现有路由前缀习惯调整，但契约保持独立。

| API | 用途 | 范围与限制 |
|---|---|---|
| GET /runs | 已采集Run列表/筛选 | 服务端scope、时间窗、游标；详情状态/后台状态/日志质量分开 |
| GET /runs/{id} | Run摘要、Attempt和业务关系 | 精确授权，不以知道id放行 |
| GET /runs/{id}/spans | 树/瀑布行的分页节点 | 时间/稳定ID排序、父节点缺失标记、明确has_more |
| GET /runs/{id}/spans/{span_id} | 单节点metadata/事件/资产/指标 | 受限Raw仅本方案白名单，不返回任意inbox载荷 |
| GET /runs/{id}/content | 已保存正文证据 | 业务locator在线/归档精确读取、每次授权、脱敏、无原始文件下载 |
| GET /overview | 业务统计、采集覆盖和性能 | 三者总体分别标注，不平均P95、不把未知Usage补零 |
| GET /capabilities | 读取本实例全局开关及功能可用性 | 不返回密码；只供授权用户了解采集/存储状态 |

P0建议不用WebSocket/SSE，按需刷新和有界轮询即可；人工入库不保证实时性，API返回读取/投影时间和可证实的质量，不承诺端到端日志时延。该交付边界已由Q23确认。

## 6. 沿用现有身份判定

Q25已明确：沿用项目当前身份/角色判定方式，不另建SSO、Source角色目录、签发/验签或可信网关适配。新模块使用现有request身份维度及manager/admin角色语义，但所有新列表、详情、正文、资产关系和统计必须执行manager当前Source/admin显式范围限制。普通用户拒绝，隐藏菜单不能替代后端检查。

代码调查中现有Header角色信任模式属于本次不改变的既有系统边界；不把身份体系升级列为本方案开发或上线前置，也不宣称本次增加了不存在的验证。NAS正文仍独立校验业务归属/删除并按现有展示规则脱敏，不能调用旧可观测接口代查。

## 7. 验收预算建议

本期先以正确性、隔离、资源有界、重复/乱序/缺失与NAS权限验收；容量报告给出测试数据量、索引计划、P50/P95和资源使用，不以未获数据支持的生产TPS/日量承诺替代测试。数据库不做清理意味着体量会持续增加；查询必须有界时间窗/分页，不能默认全库聚合。生产规模和目标时延由实际数据基线校准，作为明确未验证项而非功能隐藏限制。该首期验收边界已由Q24确认。

## 8. 收敛后的默认

全局开关为统一部署环境配置SWE_AGENTOBS_ENABLED，默认false；变更通过现有发布/重启方式生效，不承诺多Pod瞬时原子热切换。manager/admin可读功能状态，不提供修改开关的网页/API。本项目不编写部署采集器。审批与SubAgent继承Run准入快照，即使后续开关变化亦然。

业务Turn数量和逻辑Run数量分别统计；无法确认审批归并的记录不进入已确认Run成功率分母，单列unresolved。若只存在业务受理而无观测日志，不伪造obs_run_id，也不推算完整操作树。不会为得到完整分母新增业务审计写入。
