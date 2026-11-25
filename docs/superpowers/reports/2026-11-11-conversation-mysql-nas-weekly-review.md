# NAS / MySQL 会话迁移最近一周检视报告

日期：2026-11-11。范围：2026-11-04 至 2026-11-11，工作树 `.worktrees/conversation-mysql-nas`，固定 HEAD `50adbce04fbc3f08bb4dc77e5646ce5d00622f4e`。首轮由主代理与两个子代理检查；追加审计由三个子代理分别检查迁移链路、运行时发布/并发、API/SQL 投影，主代理交叉核对证据。检视前工作树干净；本轮仅新增本报告，未执行迁移或操作现场数据。

## 结论

本周变更收敛了多项实际风险：SQL 展示投影、批量查询、checkpoint 完整读取、generation fencing、workspace 正文隔离、迁移 workflow 兼容、旧分享兼容和恢复验证。追加的三路代码与设计逐项审计发现 **2 项逻辑问题：在线 context usage 未更新 SQL 投影，以及 Chat patch 可能覆盖并发修改**，详见下文。单元测试通过不能覆盖这些问题，也不构成生产放行结论。

当前实现是“元数据以 MySQL 为权威，历史正文迁移生成新 NAS bundle”的首次整体停机迁移。用户已明确确认生成新 bundle 是预期目标，不要求历史正文零复制；当前迁移方式符合这一目标。生产数据库升级、真实 NAS / 多实例故障验证和恢复切换操作仍有待完成。

## 本周重点提交

| 日期 | 提交 | 主要变化与检视判断 |
| --- | --- | --- |
| 11-05 | `a1f7bae75`、`e7422898b`、`e720e95b5` | summary/context 查询走 MySQL，批量 locator/reference 校验，减少展示查询 NAS IO 与 SQL 往返 |
| 11-05 | `f66a603ba` | checkpoint 完整读取及提交计划容量校验，避免大 checkpoint 截断 |
| 11-05 | `f4d400194` | soft lease 与 generation fencing；不能用旧执行者继续发布过期状态 |
| 11-09 | `f0d54b33e`、`e7798fa49` | 减少可重建迁移 artifact，按租户 mtime 边界检查源变化；后者依赖外部冻结措施 |
| 11-10 | `517042a3c`、`37bce2990` | SQL Chat metadata / context usage 投影，复用 summary 查询；空内容元数据已有纯 SQL 分支 |
| 11-10 | `9d078ca70` | 拒绝符号链接迁移元数据 |
| 11-10 | `7144571c3`、`7a81f0bc1`、`f981c8f50` | workspace bundle 隔离及旧 publication ticket、legacy share scope 兼容 |
| 11-10 | `a89c7248d` | 修复恢复验证链路；此前报告的恢复失败不能直接当成当前仍存在的缺陷 |
| 11-11 | `ef55b7a73` | 以 workflow 区分同为 version=3 的旧清单与 direct-v3 路由，保留旧清单兼容 |
| 11-11 | `7d3c95f77` | 分享迁移及最终 schema 契约修正；仍须遵守收紧 SQL 的人工门禁 |
| 11-11 | `9b72c860b`、`9cf34d992`、`8bed4a6a2` | 发布后目录 fsync 故障注入纠正，active turn summary 状态覆盖 |
| 11-11 | `d69039f5a` | 将正文复制、数据库升级、分享门禁和现场验收边界写入正式手册 |

## 追加代码审计：设计预期与实际调用链

用户指出上一轮过度依赖测试结果后，重新启动三个子代理，分别实读迁移链路、运行时发布/并发、API/SQL 投影；主代理交叉阅读源文件。本节判断来自分支条件、SQL 写入和调用链推导，不以单测通过作依据。

设计基准为 accepted ADR 0038/0039/0044/0045、`2026-10-29-db-nas-conversation-storage-design.md` 的发布与接口契约，以及当前 direct-v3 runbook。旧 staging/RENAME 流程不作为当前入口要求；用户已确认生成新 bundle，因此后续 metadata-only/legacy resolver 草案不作为此次历史正文迁移验收条件。

除特别注明外，下表代码路径均相对于 `src/swe/app/conversation_storage/`。

| 设计预期 | 实际代码与逻辑推导 | 判断 |
| --- | --- | --- |
| 先耐久正文，再使 SQL 索引可见 | `bundle.py:396` 的 publish 写临时文件后在 `:450` fsync 文件、`:451` hard link 不覆盖发布、`:458` fsync 目录；`publications.py:412` 等 publish 返回才标 durable；`:869` commit 拒绝非 durable 对象，inspect 后在事务内安装索引并改 committed | 符合代码顺序；NAS 是否兑现耐久保证另需实测 |
| 发布结果未知只能对账原 operation，不能重跑模型/工具 | `publications.py:445` confirm_bundle 确认原路径，`:1174` reconcile 要求 owner 停止及 expected_generation，继续结算原 operation；`_nas_io:202` 取消后等待 NAS worker 停止再返回 UnknownCommit | 符合；已发布但未引用 bundle 是跨存储协议允许的中间态 |
| Session 单活动 Turn，lease 超时不授权自动重放 | `execution.py:126` reserve_admission 锁 Session，同 question 复用 admission，其他 active Turn 返回 busy；`:597` 校验 generation/owner/active_turn，`:620` start 不允许 running 再次启动；`publications.py:674` 提交时再次验权 | 符合；soft lease 是心跳，不是自动接管授权 |
| 发布失败后停止进一步模型/工具推进 | `semantic_runtime.py:55` 在 acting 前后执行发布边界；`:107` 保存 sticky error，`:63` 后续检查抛错；定时 flush 失败取消 producer；`session_adapter.py:143` 有 pending_operation 时拒绝再次提交 | 已读链路符合；不承诺撤回已经发生的外部副作用 |
| scope 隔离同时覆盖 NAS 与 SQL 关联 | `bundle.py:244/274/292` 从可信 scope 生成并反验 locator；`publications.py:586` 核对 service/tenant/source/agent 与 Session/Chat/Turn 关联；`runtime.py:260` 的 workspace_storage 在 mysql authority 未就绪时抛错，JSON 分支仅用于 legacy authority | 符合，未发现数据库故障后自动回退文件写入 |
| checkpoint 不得静默截断首 4096 条 | `checkpoint_reader.py:386` full 固定 high 后循环至 has_more=False；`:243` 检查范围连续与数量；超过事件/字节预算显式抛 StorageUnavailable；`archive_runtime.py:131` 调用 full | 符合，完整读取与无限内存不是同一承诺 |
| 轻量 Chat 元数据纯 SQL，保留 CAS/锁/备份 fence | `chat_repository.py:670` 无 content 调用 `:748` SQL 事务，不预留 publication；复用 association locks、写 fence、pending 检查；`chat_mutations.py:298/314` 检查 revision 并同步 external_session_key | 符合；空 Chat 总写空 bundle 的旧报告判断已经过时 |
| 完整旧恢复模块、消息 occurrence 与分享旧八字段保全 | `migration/verify.py:237` 对比完整恢复 state，`:275` 比较消息数量、顺序、正文及 occurrence，`:344` 比较 Chat metadata/binding；`direct_import.py:101` 在分享行锁内逐项比较旧八字段后仅回填 locator，未知已有扩展拒绝覆盖 | 已读正常冻结链路符合；并非仅比较行数或正文文件存在 |
| 先 ready 后启动，不能混用服务/库/NAS 凭证 | `runtime.py:224` configure_runtime 调 validate_authority；`migration/authority.py:93` 核对凭证与 manifest、SQL job ready、verification receipt、server_uuid/schema/NAS roots；`:260` 未准备好拒绝 workspace 访问 | 符合；连续停写仍由部署维护措施保证，程序不能证明外部 writer 已停止 |
| 在线恢复根提交同时维护 SQL context usage 快照 | Runner 将新 usage 合入 state，Session adapter 发布 recovery，但 publication 安装只改 recovery locator/state_revision；HTTP 则只读 SQL usage 列 | **不符合，见 F1** |

### F1 — P2：在线 context usage 未写入 SQL 投影

设计依据：主设计第 10.3 节要求 `context_usage_text + context_usage_invalid` 与恢复根同提交；同一设计第 3 节规定轻查询不读完整恢复正文。该要求不依赖是否采用历史正文零复制。

实际链路与触发条件：

1. MySQL authority 下执行一次正常问答，Runner 捕获 context usage。`src/swe/app/runner/runner.py:6972` 将新 snapshot 合入 state_modules，随后通过 session_execution.commit_state 保存。
2. `session_adapter.py:143` → `:327` `_save_state` 序列化完整 state，预留 `CommitPlan(recovery_block="recovery")`，写 bundle 并 commit。
3. `publications.py:772` 安装恢复根时，仅更新 recovery_publication_id/offset/length、state_revision 和 updated_at，未更新 usage 投影。对全 `src/swe` 搜索写入口，`context_usage_text` 仅由离线 `migration/importer.py:980` 写入；`archive.py:296` 仅在 reset 时将 invalid 置 1，不能补上新快照。
4. `history.py:580` 的 context_usage API 只读取 SQL 两列，`:598` raw 为 NULL 直接返回 unavailable，不从恢复 bundle 获取新值。

因此新建会话即使恢复状态已成功保存 usage，接口仍返回 unavailable；迁移过来的会话可能持续显示迁移时旧值，执行结束后还可能被标成非 stale。reset 后 invalid 也缺少在线成功采集后清除的路径。影响是 usage 显示正确性，不是消息正文丢失。

建议修复方向：在有效 recovery publication 的同一安装事务内，按 state revision 原子安装已校验的 usage 快照/invalid 状态；失败采集保留旧值并标 invalid。补“Runner 保存 → 真实 publication 安装 → History SQL 读取”的贯通回归，不能只给查询 fake 预置 usage。

### F2 — P2：Chat patch 在锁外合并，可能覆盖并发属性

设计依据：`2026-11-06-conversation-metadata-only-adjustment-design.md:99` 明确要求 patch 在锁定的当前行上合并，避免旧整份对象覆盖并发属性。这是 Chat 更新要求，与该草案的历史正文零复制部分分别判断。此问题属于现存逻辑缺口，不断言由本周提交首次引入。

`src/swe/app/runner/api.py:2008` 先获取 existing，`:2017` 调用 `_merge_chat_update` 生成整份 spec，然后才调用 manager。`runner/manager.py:411` 的进程内锁只能保护后半段，锁内重读并未重新应用 patch；`chat_repository.py:795` 又读取数据库当前行，以当前 metadata_revision 安装传入的旧 spec。CAS 能发现 repository 读行之后的竞争，却不能发现 API 读旧值到 repository 读新 revision 之间的竞争。

可达交错：A、B 同时在 API 读到旧 Chat；B 先提交一个 meta 字段修改；A 只修改另一个字段，但其整份 spec 仍包含旧 meta；A 进入 repository 后读到 B 提交后的 revision，并成功用该 revision 写回旧 meta，覆盖 B 的修改。即使同一进程的 manager 锁串行化调用，API 锁外读取仍允许该交错；多实例也无进程内共享锁。

建议在 repository 的行锁/事务内对当前值应用 patch，或者将读取时的版本贯穿到提交并明确返回冲突。回归须控制两个请求的交错，验证不相干字段都被保留，不能仅测试 CAS helper 拒绝手工构造的旧 revision。

### 静态审计的边界

源变化检测依赖外部冻结前提。普通文件删除会因父目录 mtime 被阻断，整个 workspace 删除后严格路径解析会失败；不能仅凭 `freshness.py` 跳过不存在路径便断言正常删除会静默漏迁。但保留 mtime 的源替换/回滚超出了该防线，verify 也不是对所有已分配 ticket 与当前源对象集合做反向等值证明，故强冻结仍是必要前提。

本节没有修改实现；F1、F2 尚未修复。先前测试结果仍是事实，但不得继续引用“未发现缺陷”作为追加审计结论。

## 仍需处理的交付风险

以下为现有设计限制或上线门禁，不冒充本轮新发现的代码 bug。

1. **新 bundle 的容量和迁移耗时需要实测。** `migration/direct_import.py:174` 的 DirectImporter 继承 ConversationImporter；`migration/importer.py:443` 的发布流程创建安装计划并写新 bundle（`:501`），符合用户确认的迁移目标。上线前须测量新增 NAS 容量、文件数、停机耗时与临时盘峰值，并核对生成内容的完整性。
2. **分享 finalize SQL 带破坏性清理。** `scripts/sql/conversation_share_service_unit_finalize.sql:22` 删除四个新增定位字段全 NULL 的行，会使旧链接失效。当前 runbook 选择保留全部旧分享，要求此类行及部分回填/不匹配行均为零；必须先验证再执行，不能靠删除修复导入失败。文档门禁降低风险，但脚本本身不代替源分享集合完整性校验。
3. **mtime 不证明内容不可变。** `migration/freshness.py:13` 仅检查晚于 cutoff 的 mtime 和符号链接。保留 mtime 的改写不能据此排除，不能用该检查代替停旧 writer、只读快照/挂载和一致源边界。不能据此宣称已出现数据丢失。
4. **新建表 SQL 不等于现网增量升级。** 本周新增 Chat 投影列；已有 MySQL 权威部署不能重放 CREATE 或走首次空库导入。须基于现场表结构制定 ALTER/backfill/验证操作。
5. **灾备和 HA 切换不是开箱即用的统一 CLI。** `backup.py:64` 对恢复目标有隔离 schema 限制；原库 server_uuid 重绑定、应用备份恢复后的 runtime manifest 安全落盘和部署切换，需要现场驱动及演练。不能把 restore API 存在等同于完整故障切换方案。
6. **真实环境证据仍缺失。** 本轮未验证真实 MySQL/TDSQL、最小权限账号、业务 NAS fsync 行为、Kubernetes 多实例、既有 workspace/secret 启动或发布镜像完整 CLI 依赖。此前 trace_sdk 缺失记录须在最终镜像中通过 CLI 冒烟关闭，单测 fakes 不构成替代。

## 本轮验证

主代理执行：

```bash
/Users/shixiangyi/code/Swe/venv/bin/python -m pytest \
  tests/unit/app/conversation_storage \
  tests/unit/cli/test_conversation_storage_cmd.py \
  tests/unit/cli/test_conversation_storage_discovery_cmd.py \
  tests/unit/scripts/test_rehearse_conversation_storage.py -q
```

结果：**1081 passed，0 failed，55.11 秒**。独立 `test_summaries.py`：19 passed。迁移子代理定向五组测试：74 passed，与主范围重叠，不累加。

运行时子代理单独运行 storage 全目录：**1025 passed、1 failed**，失败为 `test_summaries.py::test_summary_endpoint_does_not_take_over_existing_chat_id`（预期 200，得到 500）；该单例独立复测通过，主代理全目录组合与独立文件均通过。当前不能确认稳定产品 bug，须保留为可能的测试顺序/共享状态污染信号，不能隐去该不一致或声称所有测试组合无条件通过。

本轮未执行真实数据库集成测试；没有以历史 1087 项结果代替本轮执行结果。

## 建议验收顺序

1. 按已确认的“历史正文迁移生成新 bundle”路线验收，核对源数据到新 bundle 的完整性、容量与迁移耗时。
2. 固定代码、SQL、手册与镜像；分别确认首次迁移与已有 MySQL 部署升级路线。
3. 在最终镜像中验证完整 CLI，再以最小权限账号和代表性旧数据执行 import → resume → verify → 分享 schema 收紧 → finalize → 单实例启动 → 多实例扩容。
4. 在真实 NAS 验证发布中断、目录 fsync、未知 SQL 提交、进程重启、源冻结及隔离；记录容量和停机耗时。
5. 实测一致备份恢复与部署切换，覆盖新写入后的保数据恢复；同时复现并定位上述偶发测试失败。

满足这些门槛后再决定生产放行，不能仅以单元测试通过替代现场验收。
