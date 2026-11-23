# 会话元数据迁移与线上读写性能方案

评审稿。代码基线为 `709c82419`。

迁移继续使用 `prepare → migrate --apply`。SQL 保存会话元数据和发布状态，NAS 保存恢复快照与正文。三项优化沿用来源独立发布、单迁移 SQL owner、原 manifest 续跑、持久化后再发布以及快速校验与完整审计各自的契约。首轮复用现有数据库索引和 NAS 格式。迁移与线上性能分别验收，使用相同数据、资源限制和基础设施对比。快速校验的字节调度、大块流式读取和摘要内存优化暂缓。

## 1. 按来源读取票据，按 Session 定位 Chat

1. 在已有磁盘索引上建立来源分组，支持按 `(完整来源身份, kind, position)` 顺序迭代，以及通过 publication ID 反查归属。作业恢复时构建一次，journal 在 SQL 提交后更新。批次无显式 scope 时使用现有可信归属规则，归属缺失或冲突继续报错。快速校验只读当前来源，依赖查找按 ID 点查并核对完整归属。作业级唯一性在索引入口校验一次，验证工作量从各来源反复扫描总记录数降为一次建索引加各来源记录和实际依赖。
2. 导入前以 `session.chat_positions` 直接取得关联 Chat，沿用工作区、user、channel、外部 Session ID 校验。由同一批 Chat 决定 Turn 映射与 `session_kind=task`，将候选遍历从 `Session × Chat` 降到 Session 数与关联 Chat 数之和。
3. 注册时批量读取并比对已登记来源证据，仅为新增来源批量注册。保持单 SQL owner、原状态转换和提交对账。每来源发布前的 schema 合约在首轮保留，并单列其 SQL 往返。导入结束时的父 manifest 全量同步也先单列测量。后续若减少镜像写入频率，须先验证每个持久化边界都能由 SQL journal 和现有 manifest 重建，包括提交成功但进程未收到确认的情形。

验收采用总记录数固定、来源数递增的矩阵，以及单工作区 1 万 Session 和 1 万 Chat 的数据。记录实际票据迭代次数、Chat 检查次数、数据库往返、manifest 写入字节数及阶段耗时。目标是全局索引构建一次，之后只处理各来源的增量和实际依赖。已经发布的来源在补迁时仅参与所需的状态和证据对账。

## 2. 用短事务获取历史快照，按需读取 NAS

历史详情和答复轮次共享一次请求内恢复目录。读取流程如下。

1. 在短事务内检查 Chat、Session 与调用者的关联，记录当前恢复 publication、`history_high`、revision、epoch 和请求所需的归档边界。为恢复根及此时已确定的正文出处安装 reader pin，提交后归还连接。
2. 在事务外读取恢复目录，按可见性、layer、水位及 occurrence 选出目标引用。答复轮次复用同一目录确定问题、Turn 归属和下一条用户消息的位置，保留重复消息 ID 的选取顺序。归档锚点去重也在事务外处理。
3. 用第二个短事务确认快照仍有效，并 pin 住所选引用。按 publication 和 block 组织 NAS 读，同一 bundle 复用打开的描述符，同一 block 在请求内只解码一次。会话恢复和历史详情可共用引用读取原语，会话恢复仍须验证并还原完整状态。
4. 返回前复核 Chat 归属及版本、Session epoch、revision 和恢复指针。发生 reset、delete、改绑或恢复指针更新时，按当前读冲突语义处理。用请求级资源栈持有全部 pin，释放前等待已发起的 NAS I/O 排空，覆盖失败、提前返回和取消。始终由事务内的引用校验和 pin 保证 GC 并发安全。

按 Session 停止时，在 SQL 中按完整 scope、user、channel 和外部 Session ID 筛选候选，保留对历史 `meta.source_id`、唯一活动 Chat 和当前执行身份的判断。仅对需要外置字段的候选读 NAS。旧 `GET /chats` 保留全量响应形状与顺序，对实际需要的外置元数据按 publication 合并读取。新迁入的空内容元数据使用缺省 locator，并验证读取方对空对象的语义等价。

用真实 MySQL 和测试 NAS 注入延迟及读取失败，交叉覆盖 reset、删除、改绑、GC、客户端取消和不同 Chat 的并发请求。验收要求事务持有时间与人为增加的 NAS 延迟解耦。单次答复轮次解析一次恢复目录，正文读取按实际命中的块计数。失败和取消后 reader pin 回到请求前基线。按 Session 停止的候选和 NAS 读取数随该 Session 的 Chat 数量增长。

## 3. 缩短准入往返，复用 Session 索引

### 准入与连接

- 一次顶层数据库操作复用同一 checkout。准入结果绑定当前任务、连接和完整来源身份，嵌套调用只在当前事务内复用。独立的自动提交语句仍各自确认状态。连接归还后结束复用，NAS 等待前后的短事务分别重新准入。运行时写事务保持来源门禁及原有 CAS，测试旧 adapter 遇到来源记录缺失或不可用时的拒绝路径。如果现有入口需要在同一事务内重新观察来源状态，则保留该复查并单独计量。
- MySQL 继续提供当前发布状态。已验证的 workspace proof 在进程内按服务、迁移 ID、租户、来源及证明内容摘要有界复用。可先由数据库返回状态及证明摘要，未命中时按同一事务快照取原文并校验。需要测量数据库计算摘要的成本，尤其是来源包含大量 workspace 的场景。命中时业务查询无需传输并解析整份 proof。证明变更、身份不符或失败结果立即重新校验或按现有错误语义拒绝。
- 首轮验收目标是热路径一次 checkout、一次状态查询加业务查询，事务内部的额外 SQL 与准入查询解耦。摘要与准入合并成单语句可在后续以实测决定，前提是能明确区分无权和零业务结果，并保证证明与数据在相同读取边界。

### Session 筛选

- 指定 `session_id` 时，从 Session 的索引解析内部 ID，再按 `chats.session_id` 读取摘要或停止候选。明确 user 与 channel 时优先验证 `uq_conv_session_identity`，明确 channel 时验证 `ix_conv_session_lookup`。保留所有匹配的内部 ID 以及 `updated_at, external_chat_key` 的全局排序、游标和响应语义。
- channel 缺省时，等值前缀较短。单独测试此分支及跨 user 的合法查询，保留当前查询作为对照。根据目标实例实际执行计划、扫描行数和写入放大，决定是否单独增加索引。兼容列表保留调用方要求的 total，仅摘要游标使用现有 `LIMIT page_size + 1`。

验收首先核对不同 source 和 user 使用相同外部 Session ID 时返回隔离、排序稳定。再测冷热证明、并发 checkout、数据库故障和缓存淘汰。分别记录 SQL、连接 ping、解码字节和池等待，并在实际版本 MySQL 上验证有无 channel、有无 user 的第一页和深游标查询。

## 实施顺序与测量

| 增量 | 交付 | 验收证据 |
| --- | --- | --- |
| 1 | 来源索引和 Session 对应 Chat 的定位 | 样本扩容时票据和 Chat 检查次数，以及阶段耗时 |
| 2 | 历史短事务、按需读取与批量列表 | 慢 NAS 下的 SQL 连接持有与锁等待、读次数和 pin 清理 |
| 3 | 准入复用与条件化 Session 查询 | 真实执行计划、每次请求的 SQL 和 ping 数、P95/P99 与隔离回归 |

每个增量单独对比基线。迁移使用既有 10k workspace 样本，再加大量来源和单长会话两个规模样本。线上以多请求并发和跨实例 GC 为主。保留 SQL cursor 调用、事务次数、连接池排队、NAS open 与读字节、RSS、临时盘以及 P50/P95/P99 指标。96 分钟的历史记录来自不同提交与远端链路，用作规模参照。上线时长和容量由同环境的基线和改版测量给出。

代码入口见 [verify_fast.py](../../../src/swe/app/conversation_storage/migration/verify_fast.py)、[disk_manifest.py](../../../src/swe/app/conversation_storage/migration/disk_manifest.py)、[importer.py](../../../src/swe/app/conversation_storage/migration/importer.py)、[history.py](../../../src/swe/app/conversation_storage/history.py)、[archive_reader.py](../../../src/swe/app/conversation_storage/archive_reader.py)、[tenant_admission.py](../../../src/swe/app/conversation_storage/tenant_admission.py) 和 [chat_repository.py](../../../src/swe/app/conversation_storage/chat_repository.py)。既有约束与记录见 [ADR 0050](../../adr/0050-conversation-migration-uses-fast-structural-verification.md) 和 [切换手册](../../../analysis/playbook/conversation-storage-cutover.md)。
