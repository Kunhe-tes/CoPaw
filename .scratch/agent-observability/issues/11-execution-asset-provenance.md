# 11: 追溯执行时实际使用的资产

Status: open
Type: task
Blocked by: 07
Triage: ready-for-agent
Priority: P0

**What to build:** 从执行节点查看当时实际使用的模型、Agent、Tool、Skill与Prompt身份及可信修订，能够区分真实版本和未知版本，避免用当前配置解释历史执行。

**Blocked by:** 07：追踪重试、恢复及分页Events/Links

**Status:** ready-for-agent

依据已确认的独立可观测设计、Trace视图对照、领域词汇及ADR 0047/0048。与旧SDK、旧埋点、旧追踪ID和旧可观测存储查询没有运行依赖；只输出元数据，正文仅经现有业务授权从NAS读取。采集由用户处理，本票不增加ES、TTL/清理或新身份体系；授权仍沿用项目已有身份判定。

- [ ] 在真实资产使用/解析边界产生安全资产元数据或asset.used事实，包含适用的可信ID、版本或签名及来源；不记录Prompt文本、Tool schema、密钥或任意文件正文。
- [ ] 模型、Agent、Tool、Skill、Prompt均有适用类型模板；注册/配置无历史修订证据时显示unknown，不能查询当前版本回填历史。
- [ ] Skill只有资产使用事实时不创建假执行区间，RAG/Workflow无真实生命周期时不造容器；未知类型安全兜底。
- [ ] 资产事实关联正确Run/Attempt/Span，经安全事件投影、授权API到Assets Inspector完成闭环；分页去重且不在metadata无限累积。
- [ ] 事件先到、重复导入、缺生命周期、版本冲突和资产数组超过32项均有明确行为，部分资产集合不宣称完整。
- [ ] 历史版本或外部资源不可反查时只展示已知元数据；不增加外部资产下载器、版本仓库或跨Run高级反查。
- [ ] 完成至少每种适用资产的代表性真实使用和缺版本用例，验证Source权限、安全Raw及Chromium108/当前浏览器。

验收环境不可用时必须明确记录未验证项，不以构建成功或新浏览器模拟替代真实Chromium108验收。

## Comments

2026-11-15：用户已确认15张票的拆分及阻塞关系，现发布为本地实施事项。尚未领取或开工；本次发布不构成功能开发授权。

2026-11-17：资产 API 现接收签名 keyset 游标，并绑定角色、授权 Source、Run 与 Span 筛选；store 按 `(occurred_at,event_id)` 稳定续页，超过32项可继续读取。增加端点游标/过滤绑定和 SQL 排序键单测。Prompt 使用事实仍没有可信生产来源，且这轮没有真实 MySQL 分页验证；版本未知呈现和大于32项的 Inbox→MySQL→API 集成验收仍待完成。工单保持 open。

资产分页游标、过滤绑定单测与目标 Python pre-commit 通过；未执行真实 MySQL。

2026-11-18：Source Tool 在实际执行闭包中持有不可变 `SourceToolVersion`；调用时现在经当前 Tool Span 发出 `asset.used`，包含该快照的工具名、发布版本、规范化 SHA-256 digest 和 `source_catalog_snapshot` 来源，不写脚本、Schema、参数或结果。Tool Span emitter 失败不会影响 Source Tool 执行。新增 producer/关联/隐私/正式 projector 单测；Source Tool、Tool observability 与观测核心定向单测 52 passed，目标 pre-commit 通过。独立复核发现并修复 digest fixture 未从脚本计算的 P2；修复后 Source Tool 专项 11 passed，复核确认 finding 已关闭且无其他可操作问题。其他 Tool/Agent/Prompt 版本证据和完整资产 API/UI/MySQL 合同尚未闭合，工单保持 open。

同日继续：模型 wrapper 现在从实际请求中的字符串 system-role 消息按顺序和长度边界计算 SHA-256，只发出 `system_prompt` 资产身份、`unknown` 版本、`runtime_model_request` 来源及 digest，并关联当前 LLM Span；不记录 Prompt 原文。无 system 消息或遇到非字符串 system 内容时不产生该事实。新增顺序/边界、排除非 system 消息、fail-closed、正文不泄漏及正式 projector 回归。Source Tool、Tool observability 与观测核心定向测试 53 passed；目标 pre-commit 和 `git diff --check` 通过。独立复核提出的覆盖缺口已补齐并确认无剩余可操作问题。Agent/Tool 其他可信修订、完整资产 API/MySQL/UI 闭环仍待完成，Ticket 保持 open。

2026-11-18：在独立随机 `_test` schema 执行 Inbox→Projector→manager 授权资产 API MySQL pipeline，扩展为同一 Tool Span 下 33 条 `asset.used` 事实，第一页 32 条带签名 continuation cursor，第二页 1 条；验证全部 33 个 event ref 唯一、无遗漏、来源/版本/digest 保留且返回 span 关联。合同通过（1 passed，66.03s）；schema 来自仅测试库使用的 DDL 草案，测试后随机库已删除，并查询确认本轮生成的隔离 schema 余数为 0。测试文件 pre-commit 与 diff check 通过。独立只读复核确认分页大小、终止游标、唯一 ref 和可信资产字段断言有效，无可操作发现；签名游标范围绑定由现有单测覆盖。该合同使用安全合成 Inbox 事实，Source Tool 真实 producer 仍仅有单测，尚无 producer→Inbox 的多事实真实 MySQL 闭环；其他资产类型和 UI/Chromium 验收未完成，Ticket 保持 open。

同日继续：新增 source tool producer MySQL 合同。测试调用真实 `build_source_tool_function`，只 stub 被观测脚本执行本身；不可变 `SourceToolVersion` digest/version 经 task-local Tool Span 发出 JSONL，随后真实写入 Inbox、Projector，并由 manager 授权资产 API 读回，核对 span、版本、SHA-256 和 source。该用例在随机 `_test` schema 通过（1 passed）；schema 删除后查询确认本轮 agent-observability 隔离 schema 数量为 0。Source Tool、observability core/query 定向单测 80 passed，pipeline 文件 pre-commit 通过，`git diff --check` 通过。独立只读复核无可操作发现。底层脚本执行仍由 Source Tool 单测覆盖；Agent/Prompt 其他可信版本与 UI/Chromium 验收未完成，Ticket 保持 open。

该 pipeline 合同的首次运行捕获到测试辅助函数读取 JSONL 前未排空 writer 的时序问题；现先关闭并 drain emitter 再消费记录。修正后的真实 Source Tool producer→Inbox→Projector→manager 授权 API 合同通过（1 passed），相关目标文件 pre-commit 通过；schema 清理余数为 0。

同日继续：普通已注册工具的使用事实现在显式带 `asset_version=unknown`。MCP 工具执行时额外记录关联 MCP server 资产：SubAgent 使用启动私有快照中的稳定 key，普通 Agent 使用注册服务名；其来源为 `runtime_snapshot`，修订仍为 `unknown`。检查确认 MCP 快照/协议未提供可信历史修订或内容摘要，本实现不将配置、headers、env、Schema 或工具正文写入事件，也不对含凭据配置做摘要。Tool observability、Source Tool 与 observability core 定向测试 54 passed；目标 pre-commit 复跑全绿，diff check 通过。测试覆盖 Tool Span 关联、SubAgent key 映射及敏感字段不泄漏。完整 MCP 真实 producer→MySQL/API 合同、其他 Agent 可信修订、完整 UI/Chromium 108 验收仍未完成，Ticket 保持 open。

同日追加：真实 `ToolGuardMixin` MCP producer 合同读取注册工具 `mcp_name`，通过 SubAgent 快照 key 映射发出 tool 与 `mcp_server` 两项 `asset.used`，关闭并排空 emitter 后逐条导入 Inbox，经 Projector 写入随机 `_test` schema，再由 manager 授权 Assets API 按 Tool Span 读回。验证两个资产身份、`unknown` 修订、来源和关联 Span；事件 JSONL 不含工具输入/输出、MCP 配置或凭据。隔离 MySQL 合同 1 passed，schema finally 删除并验证不存在；目标 pre-commit 通过。该用例 stub 的仅是外部 MCP 执行本身，实际 MCP 网络服务及其未提供的版本元数据不在验证范围内。Agent/Prompt 可信版本与 UI/Chromium 108 验收仍未完成，Ticket 保持 open。

同日继续：Run 准入的 Agent profile 与 Model wrapper 的实际 provider/model 身份现在也显式发 `asset_version=unknown`；只有 Source Tool 的不可变发布快照和 system Prompt 的运行时 digest 保留可证明的修订/内容身份。相关资产 producer 单测 43 passed，instrumentation/core 与 pipeline 目标 pre-commit 通过。随机 `_test` schema 上将 MCP、Source Tool producer/API 和业务总体合同合并复跑，3 passed，schema 已删除并确认不存在。Agent/Model 没有历史版本来源，因此明确未知，不用当前配置回填；完整 UI/Chromium 108 验收仍按用户要求暂停，Ticket 保持 open。

同日追加：扩展真实 ModelWrapper→RetryChatModel 重试成功 MySQL 合同，在同一成功 Run 上同时调用授权 Performance 与 Assets API。验证实际 Agent profile、provider/model、system Prompt 三种资产均可读取；Agent/Model 版本明确 `unknown`，Prompt 含运行时 SHA-256 digest，运行响应正文与 system prompt 正文均未进入 JSONL。Performance 同时验证逻辑调用与两次物理 request attempt 分开计数。隔离 MySQL/API 合同 1 passed，schema 清理并确认不存在；目标 pipeline pre-commit 全绿。Agent/Model 历史版本证据仍未知，页面/Chromium108验收按用户要求暂停，Ticket 保持 open。

独立只读复核确认该合同使用真实 RetryChatModel 一次 429 后成功，同一 Run 经 MySQL 同时验证 Performance 与 Assets API，Source/manager 授权明确，未发现新的可操作问题。

2026-11-18：新增独立 Skill producer→Inbox→Projector→manager Assets API MySQL 合同。使用规范 `_build_signature` 对临时 Skill 目录生成真实内容签名，经真实 `SkillInvocationDetector._activate_and_record_skill` 发出 `asset.used`；验证事件和 API 均保留 skill ID、snapshot 来源及签名，Skill 正文不进入 JSONL，Skill 资产不伪造 Span，其他 Source 返回 404。隔离随机 `_test` schema 实测 1 passed（6.90s），测试后删除且核验余数为 0；目标 pre-commit 全绿。初次运行发现测试误将规范原始十六进制签名加上 `sha256:` 前缀，按 producer 事实修正后通过。Chromium108/当前浏览器验收仍按用户要求暂停。
