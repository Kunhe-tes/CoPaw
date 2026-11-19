# 10: 从Span授权查看NAS已保存正文证据

Status: open
Type: task
Blocked by: 05, 06
Triage: ready-for-agent
Priority: P0

**What to build:** 授权运营人员可从问题、模型或工具节点查看对应的NAS已保存正文证据，并准确知道其是否待提交、压缩、未保存或不可用。

**Blocked by:** 05：查看真实模型调用、用量与首输出延迟；06：查看真实工具执行、拒绝与技术错误

**Status:** ready-for-agent

依据已确认的独立可观测设计、Trace视图对照、领域词汇及ADR 0047/0048。与旧SDK、旧埋点、旧追踪ID和旧可观测存储查询没有运行依赖；只输出元数据，正文仅经现有业务授权从NAS读取。采集由用户处理，本票不增加ES、TTL/清理或新身份体系；授权仍沿用项目已有身份判定。

- [ ] 真实执行观察点仅产生精确evidence_ref，关联当前Chat/Turn、消息occurrence或publication/block等业务身份、证据角色与保存范围；不得记录正文、NAS绝对路径或签名URL。
- [ ] 证据日志不等待NAS提交，不改变已有持久化；真实保存后可追加独立证据关联事实，本票包含必要的证据增量读写闭环，不依赖完整通用事件面板。
- [ ] 独立正文API先按现有身份和完整scope授权，再从已提交业务locator解析、pin并限量读取NAS；同时支持在线及归档精确定位，不无界扫描归档。
- [ ] 重复Msg.id或tool_call_id不能按最近值猜；冲突/缺失定位为unresolved，已保存会话片段不能称完整原始模型请求。
- [ ] 区分available、pending、not_saved、compacted及unavailable；每次读取重新检查归属、删除和现有脱敏规则，无权/不存在不泄露存在性。
- [ ] 默认正文32KiB、最多256KiB，超长内容明确截断/继续；Evidence/输入输出Tab按角色展示实际保存内容，不提供原文件下载。
- [ ] 正文不回写日志、独立观测DB或浏览器持久化；复制、深链接和Raw不能绕过鉴权或展示未保存Prompt/异常堆栈。
- [ ] 覆盖在线/归档、迟提交、删除、压缩、从未保存、多Pod、重复消息及跨Source攻击的端到端测试；验证目标浏览器的按需加载及长内容展示。

验收环境不可用时必须明确记录未验证项，不以构建成功或新浏览器模拟替代真实Chromium108验收。

## Comments

2026-11-15：用户已确认15张票的拆分及阻塞关系，现发布为本地实施事项。尚未领取或开工；本次发布不构成功能开发授权。

2026-11-17：模型调用观察点现在为实际 LLM Span 发射 `evidence.linked`，只包含已受理根问题的 Chat/消息身份、`user_question` 类型和 `available` 状态；不记录 prompt/messages/正文。通过 JSONL 和正式 projector 校验的单测。NAS locator 读取对超过上限的 extent 会在 pin/read 前返回 `truncated`，API 同时返回显式截断标记。该证据仍仅覆盖根问题；助手答复、工具输出和模型输入的精确 occurrence 生产关联及 Inbox→MySQL→正文 API 集成未验证。真实 MySQL 当前认证失败，未创建库或写入数据；正文超限没有 continuation cursor。工单保持 open。

同日复验：observability query、History 与模型证据单测 54 passed；目标 Python pre-commit 通过。

2026-11-18：MySQL pipeline 合同新增 `span.event/evidence.linked` 真实协议形状，从 Inbox→Projector→安全 locator 查询断言只返回 Chat/消息 occurrence 元数据、不泄漏注入的 prompt 字段。模型调用 producer 的单测验证问题引用与模型 Span 关联且通过正式 `_validate_payload`。本地集成测试被 skip（未设置专用 `_test` DB）；observability/History/SubAgent 定向套件 108 passed，pre-commit 通过。生产来源目前只提供根用户问题，不覆盖模型完整 Prompt、助手答复和 Tool 输出；正文超限返回 truncated 但无 continuation cursor，工单保持 open。

复验：使用现存隔离 schema `swe_agentobs_codex_20261117_test` 运行 Inbox→Projector→authorized API pipeline、审批延续与 Runner lifecycle 合同，共 6 passed。新增 evidence locator 在真实 MySQL projector 后可读，安全投影未泄露注入的 prompt 字段；未连接业务 schema。

独立复核发现 pipeline 测试曾将 model.call evidence 错挂到 Tool Span；现改为单独投影真实形状的 LLM Span，并分别验证 Tool asset 与 LLM question evidence 关联。修正后的隔离 MySQL pipeline 用例再次通过（1 passed），目标 pre-commit 通过。

2026-11-18：ToolGuard 在工具执行 task 内绑定当前 Tool Span；`ArchiveBinding.append` 仅在包含 `tool_result` 的 Msg 完成 MySQL/NAS 发布后发出 `evidence.linked`，定位使用已持久化 `Msg.id` 和 Chat，不记录正文、工具参数或 NAS 路径。事件不猜 occurrence 序号；正文 resolver 对重复消息 ID 保持 `unresolved`。单元测试覆盖 task-local Span 关联、提交后发射、正式 projector 校验及正文不泄漏，相关单测 61 passed，目标 pre-commit hooks 通过。新增真实 `MySQLArchiveStore`→`HistoryStore.message_occurrence` 集成用例，但当前环境未配置 `SWE_TEST_DB_*`，用例 skip，尚无该链路的本轮真实 MySQL 结果。独立代码复核未发现阻塞问题。助手答复生产 locator、完整助手/工具 Evidence UI、浏览器验收仍未完成，issue 保持 open。

同日继续：assistant-answer producer 在 LLM 返回后按 `(run_id, response.id)` 暂存 Span，仅在 assistant Msg 具有精确 `invocation_id`、可见文本、无 `tool_use`，且 MySQL/NAS 发布成功后追加 `assistant_answer` evidence。复用 response ID 时标记歧义并不关联；事件只含 Chat/Msg locator，不含 invocation ID 或正文。定向单测 50 passed，目标 pre-commit 通过。新增流式 `ObservabilityModelWrapper`→`ArchiveBinding.append`→`HistoryStore.message_occurrence` assistant-answer MySQL 合同，Msg 的 `invocation_id` 取最终消费 chunk ID；本地集成测试因未设置 `SWE_TEST_DB_*` 跳过。独立代码复核未发现关联、时序或隐私缺陷，初始提出的流式测试缺口已补齐。完整原文 Evidence UI、目标浏览器验收仍未完成，issue 保持 open。

2026-11-18：使用仅有空 schema 的控制库 `swe_codex_obs_<random>_test` 运行 Tool output 与 assistant answer 两条 `MySQLArchiveStore`→NAS publication→`HistoryStore.message_occurrence` 合同，2 passed。assistant-answer 集成 fixture 修正为 awaitable 返回 async stream，消费最终 chunk ID 后再写入 Msg invocation_id；工具和助手正文均可从已提交 occurrence 读取，evidence 只含安全 locator 元数据且通过 projector 校验。控制库以及 fixture 为每个测试生成的随机 child schema 均在测试后清理；未访问业务 schema。完整原文 Evidence UI、目标浏览器验收仍未完成，issue 保持 open。

同日完整 observability MySQL pipeline 在随机 `_test` schema 通过 10 项，其中包含 Evidence locator/截断/跨 Source 安全查询合同；本轮未改变正文 API 对未保存、重复 occurrence 和已删除记录的显式状态语义。schema 已删除并确认不存在。完整原文 Evidence UI 与浏览器验收按用户要求暂停，issue 保持 open。

同日继续：新增 `tests/integrated/conversation_storage/test_observability_evidence_mysql.py`，在同一隔离子 schema 实际执行 Tool `ArchiveBinding.append` 至 MySQL/NAS 提交、Task-local Span 产生 `evidence.linked`，写入 Observability Inbox、Projector 投影，最后经 manager Source 授权 Evidence API 调用真实 `HistoryStore.message_occurrence` 读回正文。验证正文只在 publication 后可读取，locator 关联 Span/Chat/Msg，JSONL 与观测事件不含正文。真实 MySQL 1 passed（17.27s）；随机控制 schema 与 fixture 子 schema 均删除并验证不存在。Evidence/query 与 ArchiveRuntime 定向单测 54 passed，目标 pre-commit 全绿；独立复核无可操作发现。完整助手/问题 producer 合并矩阵、正文超限 continuation 与页面/浏览器验收仍未完成，Ticket 保持 open。

同日扩展：同一隔离 MySQL/API 合同现在同时运行真实 `ObservabilityModelWrapper` 流式响应和 Tool Span。assistant Msg 的 `invocation_id` 显式断言等于消费到的最终 response chunk ID；两种 Span 分别通过 manager 授权 Evidence API 读回各自 NAS 消息，并验证正文均不出现在 JSONL。修正测试 execution fixture 以保留每次 publication 后的 recovery revision。最终真实 MySQL 1 passed（29.76s），随机控制与 child schema 清理完成；目标 pre-commit 全绿、query/ArchiveRuntime 单测 54 passed。独立复核建议的 invocation 身份断言已补齐。页面、浏览器与正文超限 continuation 仍未完成，Ticket 保持 open。

2026-11-18 后续复验：同一 Tool Span 的长正文现在通过 manager 授权 Evidence API 使用签名 continuation cursor 分块读取；测试对完整 UTF-8 JSON 重组并核对原 Msg ID，同时验证跨 Source 404。真实 `ArchiveBinding`→NAS publication→Inbox→Projector→API→HistoryStore 链路在新建随机控制 schema 上 1 passed（51.86s），控制库及 fixture child schema 均已清理并核验。游标绑定角色、Source、Run、Span、响应字节上限和内容摘要；单测另覆盖篡改游标、变更作用域/上限及续读期间内容改变。后端正文 continuation 已有真实 MySQL 证据；原文 UI、在线/归档全状态矩阵与浏览器验收仍未完成，issue 保持 open。

同日继续：新增归档 occurrence→观测事件 Inbox→Projector→manager Evidence API→HistoryStore/NAS 合同。测试先真实 append 并 compact 消息，确认精确行处于 `layer=archive` 且未删除，再从归档 occurrence 读回相同 Msg ID/正文；事件流不含正文，跨 Source 返回 404。隔离 MySQL 实测 1 passed（35.19s），随机控制 schema 与 fixture child schema 均删除并核验。在线和归档正文 API 后端路径均有集成证据；压缩后/not_saved/pending 状态完整矩阵、正文 UI 和浏览器验收仍未完成。

同日继续：Evidence API 单元合同补齐 `pending/not_saved/compacted/unavailable` 状态保真，并确认未知状态降级为 `unresolved`，全部非 available 状态均不加载 workspace 或触发 NAS 正文读取，2 项相关测试通过。归档 API 隔离 MySQL 合同目标 pre-commit 全绿；端到端迟提交与压缩后可用性矩阵、正文 UI/浏览器验收仍待完成。

归档合同再增强：将精确 `source_occurrence_no` 放入 evidence locator，并把已压缩归档正文扩至超过 32 KiB，经有界 continuation cursor 从归档 NAS occurrence 多页读取后重组为原 Msg。确认事件日志不包含正文，manager Source 可读而跨 Source 404。新建随机隔离 MySQL 控制库实测 1 passed（41.71s），schema 和 fixture 子库清理并核验；相关 evidence/history/archive 单元 81 passed，新增非 available 状态合同 2 passed，目标 pre-commit 全绿。

归档 continuation 最终复验：加入 `source_occurrence_no=0` 断言，重新运行同一隔离 MySQL/API 合同 1 passed（44.78s），包括已签名分页续读与重组；本轮随机控制库删除并核验不存在。复核认为在线/归档定位、Source 授权、正文不入观测事件的合同充分，无阻塞发现；目标文件 pre-commit 全绿。

续读正文精确值最终复验：强化断言要求重组出的 assistant 文本与归档前原文逐字一致。随机隔离 MySQL/API 合同再次通过（1 passed，42.25s），控制库已删除并核验不存在；目标文件 pre-commit 与 `git diff --check` 通过。

2026-11-18 后续：ArchiveBinding 现在在异步发布前写只含 Chat/Msg/证据角色的 `evidence.pending`，提交成功后写精确的 `evidence.linked/available`；提交异常保持 pending，不改变原异常或持久化语义。assistant LLM Span 结束后仍可记录 pending，与既有 ended 后 evidence.linked 行为一致。证据查询同时读取两种事实，并按完整消息定位折叠为一项，若已保存则 available 优先。单测 58 passed，覆盖工具/助手的 pending→available、发布失败保留 pending、locator 状态折叠；隔离 MySQL producer→NAS→Inbox→Projector→授权 API 合同 1 passed，断言工具和助手各只返回一个 available 证据，日志正文仍脱敏且跨 Source 404。随机库已删除并核验；目标文件 pre-commit 全绿。

2026-11-18：为满足提交前 pending 语义，`ArchiveBinding.append` 现在先发仅含 Chat/Msg/content_type 的 `evidence.pending`，不等 NAS/MySQL；发布成功后追加含精确 occurrence locator 的 `evidence.linked/available`。发布失败只保留 pending，不推断未保存或失败。Span store 在同一 locator 有 pending 和 available 时合并为一条并优先 available，避免 API 重复显示。Tool/assistant 成功转换及存储失败合同单测 3 passed，ArchiveRuntime 与 Evidence Query 定向套件 58 passed；producer→Inbox→Projector→authorized Evidence API 的真实隔离 MySQL 合同 1 passed，断言 Tool/assistant 各仅返回一条 available Evidence，随机库清理并核验。目标 pre-commit 全绿。未保存/压缩事实只在有业务证据时记录，完整 UI/浏览器验收仍暂停。

同日独立代码复核发现 locator 去重原在 SQL `LIMIT 32` 之后，pending 事实可能占满界限并挤掉同批 available 状态。现以 `ROW_NUMBER()` 按完整 locator 在 SQL 内先优先选择 `evidence.linked`，再做 32 条响应限制；JSON locator partition 显式统一 collation。新增隔离 MySQL 合同，先写 40 个 pending locator 再写对应 40 个 available，查询仍返回首 32 个 locator 且均为 available。测试 1 passed（11.29s），目标 pre-commit 全绿，控制库删除并核验不存在。

2026-11-18 后续修复生产 occurrence 接线：`MySQLArchiveStore.append_message` 将同一 `MessageInstall` 的 `source_occurrence_no` 随 commit 结果返回；`ArchiveBinding.append` 只在提交成功后的 `evidence.linked` 中附加该精确 occurrence，提交前 `evidence.pending` 保持无 occurrence。Locator 查询将无 occurrence 的 pending 与当前新 append 的默认 occurrence 0 在内部配对，不在 pending 响应中伪造精确身份。归档 Evidence MySQL 测试现通过真实 assistant wrapper、ArchiveBinding append、NAS publication、archive compaction、Inbox/Projector 和 manager API 读回 occurrence 0，不再手工注入 evidence 事件；同组覆盖 pending/available 去重、Tool/assistant producer、长正文 continuation 与跨 Source 拒绝。隔离 MySQL 文件 4 passed（159.63s），相关单测 125 passed，目标 pre-commit 与 diff check 全绿，随机控制库删除并核验。若历史记录仍有多个相同 Msg ID 且相同 occurrence，HistoryStore 继续返回 `unresolved`，不会猜选；完整 UI/浏览器验收仍按用户要求暂停，Ticket 保持 open。

更正并扩展同日 occurrence 验收：生产新 append 会查询当前 Chat 中该 `source_msg_key` 的可见 memory/task/error 与 archive occurrence，分配 `MAX(source_occurrence_no)+1`，所以重用 Msg ID 时后续 publication 使用下一个 occurrence。先前将每次 append 固定为 occurrence 0 的实现已被此序号分配替换。Store 查询还会先排除与同 Span/Chat/Msg/content role 已有 committed linked locator 对应的无 occurrence pending，再按各自精确 occurrence 保留所有 linked 项。新增真实 producer→Inbox→Projector→manager Evidence API 重复 Msg ID 合同：两个逐次 append 生成 occurrence 0/1，并各自读回对应正文。隔离 MySQL 专项 1 passed；完整 Evidence MySQL 文件 5 passed（122.54s），随机控制库及 fixture child schema 清理并核验；Evidence/Store 定向单测 106 passed，目标 pre-commit 与 diff check 全绿。若历史已存在同一 scope/Chat/Msg ID 的重复 occurrence 值，仍返回 `unresolved`，不猜测选择；完整 UI/浏览器验收按用户要求暂停。

最终复验：在线重复 Msg ID 合同按真实 Runner 顺序逐条将消息加入 Task-local memory 并立即 append，避免测试预载未来消息造成 recovery projection 提前提交。隔离 MySQL 专项 1 passed；Evidence MySQL 整文件 5 passed（120.87s），覆盖在线重复 ID occurrence 0/1 精确读取及归档 occurrence continuation；随机控制库与所有 fixture child schema 清理完成并核验。SQL pending/linked 折叠另有真实 evidence producer 与 API 合同覆盖。有效 occurrence 的生产分配及同 ID 多 occurrence 正文 API 路径已闭合；数据中出现重复 occurrence 序号时仍 fail-closed 为 unresolved。

2026-11-19 复验：使用全新空 conversation 控制 schema 重跑 `test_observability_evidence_mysql.py`，5 passed（124.59s）。覆盖 Tool/assistant 证据由真实 MySQLArchiveStore 提交后经 Inbox/Projector 和 manager API 读取、长正文签名游标续读、归档及在线重复 Msg ID occurrence、pending/available 去重顺序。控制 schema 删除核验为 0，`test_conversation_*` fixture schema 前后差异为 0。运行期间 pytest 临时目录清理产生 `ENOTEMPTY` 警告，但不影响测试通过或数据库清理。该复验未覆盖完整未保存/压缩状态矩阵的端到端来源，也不包含正文 UI 和浏览器验收；Ticket 继续 open。

同日复核发现同一 Msg 的较早 linked 可能隐藏后一次 append 的 pending；若按 local_seq 合并，同一消息失败 append 后重试也可能把前一次失败 pending 误折叠。现在每次真实 `ArchiveBinding.append` 生成独立随机 `reference_id`，pending 与该次提交后的 linked 共用该 ID；Store 对明确 occurrence 按 occurrence 去重，对尚无 occurrence 的 pending 仅按 reference_id 和对应 linked 配对。相同 Span 内不同 append/retry 的 pending 不互相折叠，linked 只完成自己的提交事实。新增随机隔离 MySQL 合同覆盖旧 occurrence 0 available、新 append pending、同刻且 event ID 反序的 occurrence 1 linked，以及两次无 occurrence 的失败/重试 pending 中仅重试成功对应 linked 的情况。该专项 1 passed；最终 `test_observability_evidence_mysql.py` 全量 6 passed（123.42s），ArchiveRuntime/Tool evidence 定向单测 12 passed，目标 pre-commit 全绿；控制 schema 删除为 0，fixture schema 差异为 0。独立复核确认 reference ID 因果配对与同刻反序合同关闭先前 finding；pytest 临时目录仍有 `ENOTEMPTY` 清理警告，不影响测试退出或 MySQL 清理。原文 UI、端到端未保存/压缩状态矩阵和浏览器验收仍未完成，Ticket 保持 open。

后续 SQL 复核发现 `legacy_pending_ambiguous` 已在 CTE 计算但未从最终 SELECT 投影，导致历史无 reference ID 的 pending 无法由 API 标记为 unresolved；现已补出投影列，并扩展 Store 单测覆盖标记映射。Store/ArchiveRuntime 定向单测 58 passed，目标 pre-commit 全绿，`git diff --check` 通过。独立复核确认 placeholder 顺序与 legacy fail-closed 逻辑一致，并建议增加“无 linked 的旧 pending 保持 pending”正例，已补充到隔离 MySQL 合同。本轮尝试以隔离随机控制 schema 执行真实 MySQL 专项，但连接在认证阶段被拒绝，未创建 schema；MySQL 合同及清理核验因此未执行，前述 2026-11-19 数据库成功记录不作为本轮投影修复的验收证据。Ticket 继续 open。

后续补充可证明的工具输出压缩状态：预算器仅在最终保存的 Tool 消息输出确实被缩短时，按该 Msg ID 标记当前 Tool Span；ArchiveBinding 提交后的 linked Evidence 记录 `saved_state=compacted`，不记录原始文本。Evidence API 仍按现有授权读取该精确 NAS occurrence，正文返回压缩后的已保存消息；跨页响应持续保留 `compacted`，并用 `truncated` 标志表示仍有后续片段。单测覆盖预算器精确消息标记、多 chunk 最终消息裁决、ArchiveBinding 状态传播、API读取压缩消息及分页状态保持；相关单测 75 passed。全量 `test_observability_evidence_mysql.py` 在随机隔离 schema 上 6 passed（122.34s），验证压缩状态跨页、NAS 裁剪正文重组、Source 隔离及其他 Evidence 合同；fixture 子 schema 前后差异为 0，控制 schema 已删除。`SWE_DB_ACCESS` 现支持原始访问值和明确的 `BEE_` 前缀两种格式，配置单测 5 passed；目标 pre-commit 全绿，`git diff --check` 通过。Ticket 10 的 `not_saved` 生产事实、其它完整端到端场景及页面/浏览器验收仍未完成，Ticket 保持 open。

2026-11-19：实际 `ObservabilityModelWrapper` 在每个有 Chat 身份的 LLM Span 上发出 `model_input/not_saved` 事实，locator 仅含 Chat、状态及当前 Span ID，不含 message ID、Prompt 或消息正文。单测通过正式 projector 校验；真实随机隔离 MySQL 合同从 Tool/assistant NAS publication 经 Inbox、Projector 到 manager Evidence API，验证 assistant 正文仍可授权读取且 `model_input` 只返回 `not_saved` 元数据。该合同 1 passed（30.11s），临时控制 schema 已删除；Observability 与 ArchiveRuntime 定向单测 108 passed，目标 pre-commit 与 `git diff --check` 全绿。pytest 退出时有临时目录 `ENOTEMPTY` 清理告警，不影响测试或数据库清理。完整正文 UI、Chromium 108 验收仍按用户要求暂停，Ticket 保持 open。

同日继续：归档助手正文 Evidence 先经 manager API 读取成功，再将对应 archive occurrence 标记删除；同一 locator 的后续读取返回 `unavailable` 且不含正文，Span 上的 `model_input/not_saved` 仍保持元数据状态。真实 MySQL 合同通过（整份 `test_observability_evidence_mysql.py` 6 passed，123.59s），控制 schema 及随机 fixture 子 schema 清理并确认不存在；目标 pre-commit 和 `git diff --check` 通过。pytest 仍有临时目录清理告警。正文 UI、Chromium 108 验收及完整多 Pod 场景按用户要求暂停，Ticket 保持 open。
