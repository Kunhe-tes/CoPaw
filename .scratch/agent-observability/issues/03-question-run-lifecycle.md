# 03: 展示真实问题的Run生命周期与采集状态

Status: claimed
Type: task
Blocked by: 02
Triage: ready-for-agent
Priority: P0

**What to build:** 一次真实主对话或专家主执行问题能够通过独立日志关联为一个Run，人工入库后展示受理、运行、业务终态及采集质量；观测开关或故障不会改变原业务行为。

**Blocked by:** 02：打通人工入库到授权Run列表的最小闭环

**Status:** claimed

依据已确认的独立可观测设计、Trace视图对照、领域词汇及ADR 0047/0048。与旧SDK、旧埋点、旧追踪ID和旧可观测存储查询没有运行依赖；只输出元数据，正文仅经现有业务授权从NAS读取。采集由用户处理，本票不增加ES、TTL/清理或新身份体系；授权仍沿用项目已有身份判定。

- [ ] 在真实受理/结算边界调用已发布的独立内核，主对话与专家主执行均可从实际问题到日志、投影、API及页面闭环验收，不以旧SDK状态为事实来源。
- [ ] Run只代表一次根问题；新问题和终态后的重执行创建新Run并可关联前驱，重连不创建，终态不可被晚到子事实重开。
- [ ] 准入时固定全局采集快照，后续执行继承；每个Run上下文携带原始run_started_at、capture_enabled、完整scope与根问题锚点，accepted丢失仍可构建partial根记录。
- [ ] 仅按已发生的业务裁决映射成功、失败、取消、超时或拒绝；等待审批不能因业务Turn completed误判Run成功，为审批专票预留独立等待语义。
- [ ] 缺日志、长时间未更新、进程中断和不明终态显示unknown/partial/unresolved；不由elapsed或查不到状态推断失败，不阻塞后续独立问题。
- [ ] 页面展示安全采集能力、数据质量和截至信息；全局observer健康仅admin可读，不泄露连接秘密或将全局健康按Source伪分配。
- [ ] 覆盖新旧开关组合、关闭低成本、取消/异常传播、观测DB不可用及输出降级的业务回归；采集传输由用户负责，不纳入验收。

验收环境不可用时必须明确记录未验证项，不以构建成功或新浏览器模拟替代真实Chromium108验收。

## Comments

2026-11-15：用户已确认15张票的拆分及阻塞关系，现发布为本地实施事项。尚未领取或开工；本次发布不构成功能开发授权。

2026-11-16：Ticket 02 已完成并解除依赖。本轮开始将独立 Run/Attempt 上下文接入普通 Runner admission，覆盖 SQL 与 legacy 会话路径；尚需补齐终态事件与审批等待回归、重连/重复受理证明及 Chromium 108 页面验收。

2026-11-16：本轮已完成普通 admission 的 accepted/running/terminal 事件接线、SQL/legacy 重连去重、审批等待状态、默认租户 scope、取消早于 stream finally 的结算顺序，以及 metadata-only 前驱 Run carrier；受影响后端回归 189 项通过。仍保持 claimed：无 answer-turn coordinator 的 legacy Runner 以及完整真实主对话/专家主执行、Chromium 108 页面验收尚未在本票完成；审批续跑归并继续由 Ticket 08 处理。

2026-11-16：新增 manager/admin 能力状态与 admin-only 全局 Health API；Run 状态缺失的 Console 行显式显示 `unknown`，质量仍独立显示。后端 observability 单测 32 passed，Console 类型检查通过，相关 Vitest 7 passed、ESLint 通过。完整真实主对话/专家主执行验收及精确 Chromium 108 补丁版仍待完成。
