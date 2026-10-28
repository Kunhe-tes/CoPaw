# 会话保存、压缩与前端历史加载契约审计

日期：2026-10-28。范围：当前工作区的普通会话保存、v2/v3 用户准入记录、压缩归档、
历史 API、Console 转换、工具配对、分页和压缩刷新。结论基于本地代码与测试，
没有取得受影响生产会话的完整原始文件，没有进行生产部署或真实浏览器验证。

## 结论

基础协议基本匹配，但端到端一致性仍不完整。压缩归档页不是用户轮次，单条源消息
也不是单个运行时片段；前端必须在已加载的源消息范围内重新组装。此前的分组、
片段去重、工具配对修复解决了这一类问题，本次过程区锚点命名空间修复已独立提交
为 `f990e0744`。

后续审计另复现两处可见一致性缺口：压缩快照替换会移除已加载归档页而保留已推进
的游标；归档与在线快照短暂重叠时，按外层卡片 ID 去重可能留下位于用户之前的
重复响应。另确认显式 `turn_id` 未被用作历史分组屏障。下述前端修复已处理这些
展示一致性问题，不包含后端存储修改；也不能据此断言它们就是尚未取得样本的生产
数据缺失根因。

## 前端修复状态

- 按稳定 runtime fragment ID 对齐重叠响应，使用较新片段内容，保留唯一输出和
  归档边界；共享片段证明同一响应时才跨重复 user 屏障对齐。外层气泡和真实
  response-card ID 的别名均传递到存活卡片，覆盖同 ID 快照刷新。
- 压缩刷新合并已加载归档与在线快照，不再直接替换整个列表。压缩事件保留旧归档
  前缀，另建当前分页代；按共享消息 ID 对齐两代顺序，避免新页排到旧页之前，
  并保持分页游标、去重状态与实际展示集合一致。切换 session/chat 时清空两层。
- 刷新尾部校验使用同一归档层组装后的候选快照，仍保留 boundary、生成状态、
  session/chat、请求期间 revision 校验，避免同轮旧片段加入后永久误拒绝刷新。
- 单页转换与跨页合并均尊重明确冲突的 `turn_id`，兼容缺少 ID 的旧数据；
  `task_run_id`、独立 Stop/cron 输出、生成中响应的既有屏障继续生效。
- 回归覆盖：真实转换器的在线/归档重叠、片段顺序与新值优先、过程锚点别名、
  归档加载在压缩前/后/刷新途中/刷新后完成，以及压缩后新归档发布与旧前缀重读。

后文保留修复前的诊断证据。后端发布事务、磁盘原文缺失和历史数据修复仍未处理；
本次不涉及 MySQL 决策，也没有进行生产会话数据修复或真实浏览器验证。

验证：history/sessionApi、MessageList、Response、Bubble history hooks 共 19 个测试
文件、267 项测试通过；改动文件 ESLint、Prettier、TypeScript 和生产构建通过。
曾运行全量前端测试，未通过：包含身份默认值、预览、管理页面的断言/超时以及
CSS 导入、mock API 缺失错误；该次运行还包含随后已修复并单独复验的归档排序
回归，因此不能将该次全量结果视为最终代码的全量通过证明。

### 分页拼装回归复核

`df62f6de3` 的 MessageList 分页回写另引入两处回归：归档缓存合并跨页响应后
保留较新页的气泡 ID，回写时按该 ID 选择已显示旧卡片，导致新增片段被丢弃；
重复在线响应经归档集合前插、再从当前集合删除，会从问题后方移动到问题前方。
这两项均用真实转换器和 MessageList 集成测试先失败复现，再以
`reconcileHistoryLayers(archiveMessages, current)` 替换该卡片选择/前插逻辑修复。
当前列表提供共享消息的位置和较新数据，归档层补入缺失输出；不再整卡覆盖。

新增三项回归覆盖两页/三页响应累计、每页片段完整性、稳定气泡 ID、过程锚点
别名，以及归档响应先到/用户后到时在线问题与响应的顺序。复核时原有 70 项
测试与新增三项均通过，扩大到 sessionApi、MessageList、Response 与 Bubble
history hooks 共 19 文件、270 项通过。后端、API 与存储协议未改动。

## 身份与存储模型

| 对象              | 身份及位置                                               | 语义                                              |
| ----------------- | -------------------------------------------------------- | ------------------------------------------------- |
| 用户准入记录      | `turn_states[turn_id].message`，通常以用户 Msg ID 为 key | 执行前持久化用户锚点，不等于全部模型输出          |
| AgentScope 源消息 | `Msg.id`；在线 memory 或归档 JSONL                       | 一个源消息可含思考、调用等多个块                  |
| Runtime 片段      | 历史接口的 message ID；`metadata.original_id` 关联源消息 | 多片段各自需要稳定且不同的 ID，不能仅按源 ID 去重 |
| 工具执行          | `call_id` / `tool_call_id` / 显式工具块 ID               | 用于配对调用与结果，不代表完整用户轮次            |
| 外层响应气泡      | `history-response-<stableId>`                            | 列表卡片、普通滚动锚点的命名空间                  |
| 响应卡数据        | `cards[0].data.id = response_<stableId>`                 | 渲染器过程区使用 `process:<此 ID>`                |
| 归档边界/游标     | batch UUID、source Msg 下标、chat ID                     | 存储/分页边界，不能当作执行边界                   |

`buildResponseCard` 位于 `console/src/pages/Chat/sessionApi/index.ts:580`；真实过程区
DOM 位于 `Response/Card.tsx:388`。这是本次 review 指出的两套 ID 不匹配的直接证据。

### v2 与 v3

- v2：主 session JSON 的 `turn_states` 存储准入记录。没有 `.turn-ledger` 是正常的。
- v3：主文件只保留热集合；终态记录可进入
  `sessions/.turn-ledger/<session_generation>/`。目录由
  `TurnLedger.directory`（`src/swe/app/runner/turn_ledger.py:137`）决定。
- v3 history 会先 materialize 冷热集合，再按 chat 过滤并按 admission order 排序；
  不能仅查看主 JSON 就判定用户记录丢失。
- 因此“所有用户输入始终都在主文件 turn_states 中”不成立。v2 的旧数据、未经过
  新准入路径的数据、导入数据和损坏数据，也不能承诺有完整准入记录。

## 正常链路与匹配情况

1. **准入与保存**：`session_lifecycle.py:171` 的 `admit_user_turn` 在 Agent 工作前
   保存用户原文、状态和 chat ID。`runner.py:7066` 的普通保存从既有顶层 state
   复制，仅替换 agent 等指定字段，不会正常清空 `turn_states`。
   `SessionExecution.commit_state`（`session.py:446`）持会话锁，增加 revision，
   v2 原子替换 JSON；v3 使用 ledger 提交/恢复。
2. **压缩**：`MemoryCompactionHook` 是 pre-reasoning hook，可以在一次执行中触发。
   `check_valid_messages`（`agents/utils/tool_message_utils.py:36`）校验工具输入、
   输出 ID 集合相等，不保证整轮用户输入、过程和最终回答在同一批次。
3. **归档**：`conversation_archive.py:2578` 先 durable commit，再从在线 memory
   移除对应消息；随后更新摘要。checkpoint 路径也按源消息前缀和 revision 校验，
   并不保证完整轮次分批。归档 batch、manifest/checkpoint 有自己的发布顺序与锁。
4. **初始 history**：`api.py:826` 合成在线 memory、任务/错误和需要补回的用户
   准入锚点；`api.py:322` 只过滤已归档的补回锚点，避免在在线列表再次添加。
   它不会过滤 memory 本身已有的用户消息。被过滤的原文应从归档分页取。
5. **归档分页**：`conversation_archive.py:1709` 从新向旧选择一页，返回页内时间线
   顺序；limit/offset 以源 Msg 计数。`api.py:962` 再把源 Msg 展开为运行时片段，
   所以前端不能用展开后的条数推算游标。游标绑定 chat、batch 和源下标并签名。
6. **前端组装**：`convertArchivedPage`（`sessionApi/index.ts:783`）在源 Msg 最后
   一个片段后放置对应 divider，再重新合并响应。`mergeHistoryResponses` 跨页和
   divider 组装已加载的历史，保留独立 Stop 输出及任务运行边界，不合并生成中输出。
7. **工具配对**：`Response/ToolMessageMerge.ts:117` 在同一响应内按显式调用 ID
   双向配对，输出先出现也能配对；同名并发不靠名称强行合并；真正缺失一侧时保留
   单侧内容。配对范围受响应分组影响，无法跨一个错误的 user barrier 配对。
8. **加载隔离**：MessageList 对 session/chat/generation 校验，拒绝不前进的游标，
   加载错误可重试，旧分页请求不写回新一代。压缩快照还要求非 generating、
   boundary 存在、尾部指纹匹配、请求期间本地消息 revision 不变。

这些保护是有效的，但没有提供跨“归档文件 + session 快照 + 前端分页状态”的统一
发布事务。后述问题发生在这些局部正确机制的交界处。

## 本次已修复：过程区锚点命名空间

`historyAssembly.ts` 现在将外层气泡别名与 response-card 别名分别保存在
`historyAnchorIds`、`historyResponseCardIds`。解析 `process:` 时匹配卡片数据 ID
及其别名，返回存活卡片的 `cards[0].data.id`，不再返回外层 message ID。

测试使用真实转换器生成的 ID，明确断言 outer ID 与 card ID 不同，并覆盖：
多次合并的别名传递、MessageList 加载后的滚动偏移、转换器到真实 Card 渲染器
的 DOM 契约。修复前 resolver 与滚动测试失败，修复后通过。

## 修复前已复现的缺口

### 1. P2：压缩快照替换与归档游标脱节

位置：`MessageList/index.tsx:354` 的全量 `setMessages`；分页状态在同文件
`:433-465` 推进，压缩事件在 `:647-663` 重置一次。

复现步骤：

1. 收到压缩事件，当前仍 generating，刷新等待。
2. 用户加载一页归档，消息加入列表，游标推进到 `after-first-page`。
3. 当前执行结束，后端快照满足 boundary 和尾部指纹校验。
4. 快照全量替换列表，将刚加载的旧 user 移除，但没有重置分页游标/去重集合。
5. 下一次分页仍携带 `after-first-page`，已被移除的那页不再重取。

使用真实 MessageList、mock context/API 的测试已确认第 2 步旧 user 存在、第 4 步
消失、第 5 步携带已推进游标。预期保留旧 user 的断言失败。这里是展示集合丢失，
并非磁盘归档删除；重新进入会话并重新分页可以恢复。

最小修复方向：快照接受和归档分页必须共享一次一致性更新。可以保留独立的已加载
归档源集合并与新在线快照统一组装；若选择清空列表，则必须同步重置 cursor、
dedup、done、generation 并防止旧请求回写，同时处理阅读位置。仅清空去重集合
不能修复已推进的游标。验收需要覆盖快照接受前后两种分页完成顺序。

### 2. P2：归档/在线重叠按卡片 ID 去重，留下无用户前导响应

后端证据：`archive_compacted_messages` 发布归档早于新的 session memory 快照
保存；两者没有统一锁/原子版本。真实 archive store 与 history API 的本地测试
确认同一 user 和第一段 assistant 同时出现在在线 history 与归档页。

前端复现输入：在线为 `[user, answer1, answer2]`，归档新页为 `[user, answer1]`。
真实转换器将在线响应 ID 设为包含两段 ID 的组 ID，归档响应组 ID 只含第一段。
MessageList 的外层 ID 去重删除重复 user，但无法删除不同组 ID 的重复响应。
最终列表为 `[assistant(answer1), user, assistant(answer1, answer2)]`。真实
MessageList + 真实转换器测试预期 `[user, assistant]`，实际三张卡，已失败复现。

这可以造成“历史中有只含模型过程、没有对应用户输入的一张额外卡”的表象，但不
等于用户原文真的丢失。`mergeHistoryResponses` 的组内去重不能越过保留的 user，
因此单纯增强组内去重不够。

最小修复方向：在转换/分组前按 runtime fragment identity 统一去重在线和归档
来源，保留用户边界与源顺序，再生成卡片；不要用组 ID 代表源消息身份。长期可
加入共同发布 revision，使在线快照与归档可见范围来自同一发布状态。

### 3. P2（有条件）：显式 turn_id 没有作为分组屏障

位置：`sessionApi/index.ts:726` 和 `historyAssembly.ts:71`。分组主要使用 user
边界和 `task_run_id`。两条明确不同 `metadata.turn_id`、但中间没有 user 的输出，
在单页及跨页情况下都会合并；本地诊断已确认。

只在用户边界完整时，该问题通常不触发。没有证据证明当前普通输出都会持久化
turn_id；runner 的通用附加路径主要写 trace_id。也不能将任意 trace_id 等同
turn_id。最小方向是尊重已有明确且冲突的执行身份，缺失身份时保留旧历史的
连续组装降级策略，不要求旧数据凭空补出身份。

## 其他边界与生产核实项

- **已缺失的原文**：若在线 memory、v2 turn_states（或 v3 冷热 ledger）、归档
  均无该用户原文，前端无法恢复。当前普通保存路径不会正常删除顶层 turn_states，
  但旧版本未准入、复用用户 message ID、外部覆盖/导入和历史损坏仍需样本核对。
  `admit_user_turn` 对相同 key、不同 message 会覆盖记录，这是条件风险，尚未
  证实生产发生。
- **无 ID 的非标准旧记录**：安装的 `Msg.from_dict` 对缺失 id 的输入会生成新 ID；
  同一 raw record 两次反序列化已验证 ID 不同。显式空 id 才可能走后续 legacy
  fallback，而 fallback 依赖 session ID/位置。当前规范归档会写 `Msg.id`，不受
  此问题影响；不要承诺损坏/导入无 ID 数据的身份稳定性。
- **异常时间戳**：在线 history 按 `_message_sort_key`（`api.py:679`）排序，归档
  按存储顺序返回。缺失/非法时间戳会排在线有效时间戳之后，可能改变用户边界的
  相对位置。正常有效时间戳数据没有据此确认问题。
- **损坏归档的可观测性**：`_select_page`（`conversation_archive.py:2228`）会跳过
  不一致 batch，坏记录也会被跳过；最终可返回 `has_more=false`，API 没有独立的
  incomplete 标记。日志有 warning，但 UI 可能把“不完整”显示为“已到开始处”。
- **压缩刷新重试上限**：当前退避为 50/100/250/500/1000/2000ms。尾部组装形状
  变化可能让合法快照不匹配，重试耗尽后仍保留本地状态；没有专门的可见失败状态。
  这是待补端到端用例，不能直接当作已复现丢失。
- **Kubernetes 多副本**：需核实同租户 session/dialog 根目录共享、文件锁在实际
  NAS 上有效、cursor secret 在副本间一致（环境变量
  `SWE_CONVERSATION_ARCHIVE_CURSOR_SECRET` 或共享 secret 文件）。本地锁与游标
  测试不能代替多副本/NAS 验证。现有部署证据不足，不能归因于部署错误。

## 验证证据与范围

- 锚点修复相关前端：16 文件、231 项通过；typecheck、定向 ESLint、Prettier、
  diff check、提交钩子通过。包含真实 Card DOM 契约测试。
- 完成审计后再运行 historyAssembly、真实 Card、MessageList 三个正式测试文件：
  77 项通过，typecheck 再次通过；临时诊断已移出 Console。
- 后端扩展审计：12 个 session/ledger/history API/archive/compaction/checkpoint
  测试文件，198 项通过（8.25s）。日志：
  `/private/tmp/swe-history-contract-backend.log`。
- 归档先发布而在线快照尚旧的真实后端最小诊断：1 项通过，证明重叠窗口存在。
- 两个前端集成诊断：2 项预期断言失败，分别证明快照遗漏已加载页及重叠重复卡。
  失败不属于锚点回归测试；诊断材料保存在
  `/private/tmp/swe-missing-user-diagnostic/`，不混入常规测试套件。
- 另有 explicit turn_id 分组、无 id 反序列化诊断；前者确认分组忽略该字段，
  后者确认非标准记录身份不稳定。它们证明边界行为，不证明生产缺失的唯一原因。
- 未运行生产数据修复、迁移、部署或 push；没有宣称实际浏览器/NAS 场景通过。

## 后续实施顺序

1. 用上述失败复现补正式回归，修复压缩快照与分页集合/游标的一致性。
2. 统一在线与归档的源片段去重，再分组，覆盖重叠、跨页、重复 user、工具双侧。
3. 在不破坏无 turn_id 旧历史降级行为的前提下，加入明确执行身份屏障。
4. 补异常存储/时间戳可观测性，并用生产快照、实际 NAS/多副本验证持久化边界。

验收应以不同 page size、不同刷新交错最终产生同一已加载消息集合为准，同时校验
用户原文、工具输入/输出、响应边界与阅读锚点；单独测试 helper 或仅看通过总数
不能证明跨层契约成立。
