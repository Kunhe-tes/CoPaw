# 08: 贯通审批等待与同Run恢复执行

Status: in-progress
Type: task
Blocked by: 06
Triage: ready-for-agent
Priority: P0

**What to build:** 待审批问题在可观测页面保持同一个未终结Run，批准后进入新的Attempt；运营人员可以查看等待区间、连续审批及恢复关系，而不会把审批提示当作问题已成功。

**Blocked by:** 06：查看真实工具执行、拒绝与技术错误

**Status:** in-progress

依据已确认的独立可观测设计、Trace视图对照、领域词汇及ADR 0047/0048。与旧SDK、旧埋点、旧追踪ID和旧可观测存储查询没有运行依赖；只输出元数据，正文仅经现有业务授权从NAS读取。采集由用户处理，本票不增加ES、TTL/清理或新身份体系；授权仍沿用项目已有身份判定。

- [ ] 在真实审批请求/决议和恢复入口产生独立事实；原业务Turn completed不结束待审批Run，当前Attempt以waiting_approval结束。
- [ ] 审批载体携带根Run、根问题、采集快照、原始Run时间、前驱Attempt和request身份，只含元数据；恢复不依赖人工日志已经入库，不按session最新消息猜。
- [ ] 批准后同Run新Attempt，连续审批保留最初根问题；既有业务幂等下的重复批准复用同一次恢复Attempt，不额外执行工具或抢占序号。
- [ ] 真实拒绝、过期、取消按业务裁决结束Run；记录丢失、重启无法恢复或无终态只显示unresolved/unknown，不自行恢复业务或推断失败。
- [ ] 投影和API提供独立等待状态、等待起止、决议与Attempt导航；UI区分Run总耗时、活动时间和审批等待，不把等待拼成连续Agent Span。
- [ ] 恢复/前驱关联使用Link语义，不制造跨Attempt普通父子；即使通用Links票尚未合入，本票须通过审批专用关系和导航独立演示。
- [ ] 覆盖审批跨业务Turn、连续审批、重复决议、先决议后请求、上下文缺失和快照继承；不修改原审批授权、执行或业务状态机。
- [ ] 完成等待→人工入库→批准恢复→同Run新Attempt的API/UI闭环，验证Source隔离与Chromium108/当前浏览器。

验收环境不可用时必须明确记录未验证项，不以构建成功或新浏览器模拟替代真实Chromium108验收。

## Comments

2026-11-15：用户已确认15张票的拆分及阻塞关系，现发布为本地实施事项。尚未领取或开工；本次发布不构成功能开发授权。
2026-11-17：匹配到 pending 审批但观测 carrier 缺失或校验失败时，续跑决议标记为 `unresolved`。业务审批命令仍沿用原处理路径，但不为当前请求新建观测 Run/Attempt，也不建立 deferred settlement；已补单元回归测试。此项只定义未知关联，不影响审批授权或业务状态机。
2026-11-17：验证 `tests/unit/observability/test_runner_lifecycle.py`（10 passed）、本地 MySQL `test_mysql_pipeline.py`（3 passed）及目标文件 pre-commit hooks。Chromium 108 浏览器实测及本票其余连续审批、重复决议、超时/取消和等待区间 UI 验收仍未完成。
2026-11-17：审批请求事件现在使用 ApprovalService 实际创建时间，解决事件保持同一等待起点；授权 Events API 返回受 scope 保护的 `attempt_id`，Inspector 显示受控决议文案、等待时长和关联 Attempt 导航。Stop 将 pending approval 标为 superseded 时，ApprovalService 从经 scope 校验的 carrier 发出 `approval.resolved`，Run 终态仍由原业务持久化 settlement 负责；只清除该已结束等待 Attempt 的 deferred 引用，避免同一 Attempt 重复写终态，普通 Stop 保留活动 Attempt。新增完整 `AnswerTurnCoordinator.claim_stop`→Workspace approval port→真实 `ApprovalService`→session persistence→deferred cancelled settlement 测试，断言审批决议先于 Run 终态且等待 Attempt 只结束一次。定向 Console 测试 25 passed，TypeScript/ESLint/Prettier 通过，Approval/Runner/AnswerTurn 单测 20 passed，MySQL approval continuation 专项 1 passed，全套 MySQL observability pipeline/lifecycle 14 passed。独立复审未发现 Stop 跨 Run 绑定错误；连续审批/重复外部决议覆盖、活动时间汇总和真实 Chromium 108/360 验收仍未完成，故保持 in-progress。
浏览器验收环境检查：本机 CUA browser host 不可用，未发现可执行的 Chromium/360 浏览器或 Playwright browser cache；本轮未执行真实浏览器验收。
2026-11-17：增加连续两轮审批恢复回归，确认审批 carrier 恢复同一 Run 与原问题身份，三段 Attempt 按 predecessor 连续编号；等待期间不发 Run 终态，每轮产生 requested/resolved 事实，最终只产生一次 succeeded Run 终态。重复同一已批准 request 再次进入 admission 时不恢复上下文，避免重复分配观测 Attempt。`tests/unit/observability/test_runner_lifecycle.py` 与 Stop 测试 14 passed，目标 pre-commit 通过。真实 ApprovalService 持久化幂等的端到端链路和 MySQL 连续审批尚未覆盖。

2026-11-17：扩展真实 MySQL approval continuation 合同为两轮连续审批，在同一隔离库投影后查询授权 Run Detail/Events；断言三段 Attempt predecessor 链、两个 approval requested/resolved 分别指向等待与恢复 Attempt、根问题保持不变、最终 Run 只结束一次。MySQL 专项 1 passed（14.73s），`test_mysql_pipeline.py` pre-commit 通过。仍缺实际 ApprovalService 重复外部决议持久化幂等、拒绝/超时/取消完整 MySQL 流程与浏览器验收。
Chromium 108.0.5359.29 实机页面检查被 dev server 的认证、有效配置和模板 API 500 阻断，审批 Inspector 未加载；该检查不构成兼容性验收。108.0.5359.95、360 内核与 `hideMenu=true` 仍待服务环境可用。

2026-11-18：Projector 为 `approval.resolved.decision` 增加受控枚举校验，仅接受 `approved/denied/timed_out/superseded`，未知值不作为自由文本持久化。定向 query/lifecycle/Stop 单测 47 passed，目标 pre-commit 通过。真实 ApprovalService 持久化的重复外部决议与拒绝/超时 MySQL 流程、浏览器验收仍未完成。

独立只读复核确认四个值覆盖当前所有生产发射路径，无具体兼容性问题。

同日使用隔离 `_test` schema 重验两轮 approval continuation 的 MySQL 投影/API合同，并与 pipeline、Runner admission 一起共 6 passed。真实 ApprovalService 重复外部决议持久化幂等、拒绝/timeout业务闭环和 Chromium108/360 验收仍未覆盖。

补充：新增真实 `ApprovalService` + `ApprovalAuditStore` 调用路径合同，覆盖 approved、denied、timed_out 首次决议及冲突重放；断言只持久化一条 resolved 事件，重放不改首次状态或 Future 结果。审批审计服务单测 6 passed。当前 shell 未配置 DB 连接环境变量，本轮未对该服务合同执行真实 MySQL；此前隔离 `_test` schema 的审批恢复投影/API验证仍为 6 passed。浏览器验收和完整拒绝/超时/取消 MySQL 流程仍未完成。

2026-11-18：新增 `tests/integrated/conversation_storage/test_approval_audit_mysql.py`，在 fixture 生成的隔离 conversation schema 上真实初始化 `ApprovalAuditStore` 并调用 `ApprovalService.create_pending/resolve_request`；参数覆盖 approved/denied/timed_out，随后提交相反决议重放。MySQL 实测 3 passed，验证 requests 表保留首次状态、events 表只有 created/resolved 各一条，resolved.status 与首次决议一致，Future 结果也未变化。随机控制 schema 和 fixture 子 schema 均清理，另查同名隔离 schema 余数为 0。审批 audit/service 单测 26 passed，目标 pre-commit 全绿。独立复核进行中；外部 HTTP/消息通道、拒绝/超时/取消 Runner 全链路及浏览器验收仍未完成。

独立复核指出缺少 scope 持久化断言；现已增加 `scope_id` 与 PendingApproval 身份一致，以及 tenant/source 精确断言。修复后隔离 MySQL 参数化合同再次 3 passed，单测 26 passed，目标 pre-commit 通过；复核确认 finding 已关闭，无其他可操作发现。完整外部通道/Runner 闭环和 Chromium108/360 验收仍未完成。

2026-11-18：新增独立 `test_approval_terminal_mysql.py` 参数化合同，覆盖 denied→rejected 与 timed_out→timed_out 的 MySQL 投影和授权 Run Detail/Events API；验证等待 Attempt 保留、approval ID 与 Attempt 关联、请求早于决议、Run 仅终结一次。使用随机 `_test` schema 按设计 DDL 初始化后实测 2 passed，测试后删除并核验 schema 余数为 0；相关生命周期/query/audit 单测 54 passed，目标 pre-commit 与 diff check 通过。独立复核指出该合同从 lifecycle hooks 发射事件，验证投影/API，不经过 Runner 的真实审批决议分支；该缺口保留为后续真实 Runner 拒绝/超时集成验证，本合同不代表完整业务闭环。浏览器验收仍未完成。
