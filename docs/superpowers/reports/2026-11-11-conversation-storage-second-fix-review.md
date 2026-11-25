# 会话迁移与 CRUD 第二轮修复复核

日期：2026-11-11。源码固定为 `062cf455edb9d3cbae7b3012b7a875295b2b3014`。
主代理与三个子代理分别实读历史读取、CRUD/授权、旧格式迁移及备份恢复/GC。本轮只新增报告，未修改实现或操作业务数据。历史正文生成新 bundle 是当前预期。

## 结论

最新修复关闭了原 F3 的 reset 交错及原 F4 的单条 DELETE 交错，但尚未覆盖同类全部路径。本轮确认三项剩余问题：共享 Session 的 compact/prune 在途读取、batch-delete 授权快照遗漏、自动标题保存覆盖并发元数据。因此不能认定增删改查逻辑完全正确且完备。

这些结论来自源码和可达调用交错；不是从单元测试失败推断。不存在可以诚实交付的全系统“100% 正确”保证，尤其当前已有明确反例。

## 修复是否成立

- **F3/reset 具体交错：成立。** `history.py:278` 的 snapshot 现在记录 Session.context_epoch；`:343` 的 `_validate_snapshot` 检查 Chat 后再检查该 epoch；详情/tracing 的 `_assemble` 在读前和返回前调用。`_turn_snapshot` 也捕获 epoch。reset 会增加 Session.context_epoch，因此 A reset 后，B 的旧 snapshot 会冲突。
- **F4/单条 DELETE：成立。** `runner/api.py:2060` 传 expected_chats，manager 贯穿到 repository；`chat_repository.py:631` 在 Chat 行锁内比较 user/channel/external_session_key。合法 ownership rebind 后，旧删除请求不能再按原授权提交。
- 原 F1/context usage、F2/HTTP patch 的修复仍保留；但 HTTP patch 的保护不能自动覆盖所有内部更新方法。

## 剩余问题

### R1 — P2：compact/prune 不改变 context_epoch，共享 Session 在途读取仍可能返回已隐藏消息

新校验只在 Session.context_epoch 改变时拦截共享 Session 变化。`archive.py:255` 的 `_prune` 校验 occurrence 后，经 `collection_queries.py` 的 PRUNE 将 current_visible/in_context 置 0，没有增加 context_epoch。归档/消息安装更新的是相关 Chat 的 history_revision；另一共享 Chat B 的行可以保持不变。

可达交错：A、B 共享 Session；B 已查询并 pin 一批在线消息，暂停 NAS 读取；A compact/prune 提交，隐藏其中消息；B 恢复读取。B 自身 Chat 版本和 Session.context_epoch 均未变，新 `_validate_snapshot` 仍通过，返回已隐藏的消息。

pin 只保证物理正文不被回收，不保证 current_visible。建议对所有改变共享在线可见性的提交维护统一版本，或返回前批量重验 occurrence；不能只为 reset 增加版本。回归应分别覆盖 reset、compact、普通 recovery prune 的共享 Chat 交错。

### R2 — P2：batch-delete 未贯穿授权快照，原 F4 仍存在于批量入口

`runner/api.py:1479` 起逐条 get_chat 和 `_authorize_chat`，但 `:1486` 仅将 authorized_ids 传入 mgr.delete_chats，没有 expected_chats。

可达交错：Alice 批量请求已经授权某 Chat；合法管理/内部调用将 Chat 转移给 Bob 并提交；批量删除随后进入 repository，查询到新关联且未提供 expected，仍可 tombstone Bob 的 Chat。

前提是受支持的合法管理/内部 ownership 转移；普通 Alice API 不能自行把 user 改成 Bob。此项不是任意跨用户删除，而是旧授权在并发转移后仍生效。建议批量入口收集并传递完整授权快照，同单条入口处理 ConflictError。

### R3 — P2：内部自动标题保存仍可能用旧完整 spec 覆盖并发 meta

`runner/runner.py:3747` 实际调用 ChatManager.update_chat_name 保存标题和 session_title_generated。`runner/manager.py:471` 读取完整 spec，修改标题/meta 后，`:485` 调用 update_chat_if_exists(spec)，没有 expected_chat。repository 再取当前 revision，随后安装传入的完整旧 metadata。

多实例交错：Pod A 标题流程读取旧 spec；Pod B 提交 meta 更新；A 进入 repository 读取 B 提交后的 revision，用旧 meta 加新标题成功提交，覆盖 B 的修改。A 的进程内 manager 锁无法保护 Pod B。

因此原 F2 的 HTTP 修复有效，内部标题路径仍有同一类陈旧整对象覆盖。建议标题/meta patch 在锁定当前行上合并，或保留读取时 expected_chat 并调用条件更新。应验证真实自动标题调用，而不只测试 HTTP patch。

## 本轮新增覆盖及判断

路径除特别说明外均相对于 `src/swe/app/conversation_storage/`。

| 范围 | 实际代码保证及边界 |
| --- | --- |
| 旧 NAS 只读解析 | `migration/legacy.py:47` 在临时工作副本解析，pending ledger 修复不写原件；safe_files 拒绝 symlink/非普通对象。符合生成新 bundle 的迁移目标 |
| v3 ledger/checkpoint v2 | `legacy.py:75/163` 选择 generation 及完整配套文件，逐 epoch 检查 committed_bytes、边界数量和端点，不仅导主 JSON |
| 备份集合合并 | `backup_set.py:44` 拒绝重复 scope、schema 不一致、冲突的 legacy_share/实体集合；共享 live bundle 比较内容，不静默择一覆盖 |
| 隔离恢复 | `backup.py:1203/1272` 检查服务 NAS 映射、目标空且不重叠、隔离 schema、空七表及 token collation |
| 恢复原子安装与验证 | `backup.py:1350` 后同事务插入、正式 reader 验证和 authority 安装；验证失败回滚 SQL，不授权半验证数据 |
| 恢复执行权 | `backup.py:1088/1152` 增 generation、清 owner/lease，保留待 settling Turn；needs_settlement 未解决不宣称 restore_ready，不重跑 Agent |
| IO 取消与 pins | `publications.py:202`、`retention.py:75/98` 等待 NAS worker 真正结束再释放保护或抛 UnknownCommit，避免后台 IO 与清理竞态 |
| GC/dependency | `gc.py:349/392` 锁下重验保护→deleting→物理删除→reclaimed；新 pin 不接受 deleting；`retention.py:490/537` 限同 scope、更早 publication，source reclaimed 后才释放依赖 |
| 未知结果 | `publications.py:1179` 要求 owner_stopped/expected_generation，对账原 operation，不重新执行模型/工具 |

在上述已读正常链路中，本轮未确认新的迁移主流程或备份恢复确定性缺陷。但旧格式任意畸形组合、全部业务调用方和全部故障时序未穷举。

## 测试与未验证边界

辅助定向回归：`test_history.py`、`test_chat_repository.py`、`tests/unit/app/test_chat_api_update.py`：**46 passed，0 failed，0.66 秒**。这不覆盖上述所有交错，因此不改变问题判断。

仍保留以下交付边界：业务 NAS 的 fsync/hard-link 耐久语义、真实 MySQL/TDSQL、多 Pod 故障、最小权限、完整部署恢复操作未在本轮实测；retained_history 缺释放路径；隔离 restore 失败后 NAS 可能已有已复制文件，须换新目标或按操作单处理；备份失败可能保留 fence/pin，须有显式检查与释放流程。

高信心结论是“具体修复部分成立，但同类路径仍有遗漏”，而不是“整个系统已经正确完备”。本轮没有修改这些问题。
