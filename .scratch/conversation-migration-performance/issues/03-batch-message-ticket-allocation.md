# 03: 消息票据批量分配与安全续跑

**What to build:** migrate 按受限消息批次分配持久票据，减少逐消息事务，同时正确恢复已有与缺失票据混合的作业。

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] 增加有界批量分配能力并接入 Message 导入调用链，保留现有单条接口及 SQL owner 限制。
- [x] 一个受限事务内检查和锁定已有票据、插入缺失票据、按完整唯一键重读真实 ID、回填并核对 target_id=id。
- [x] 保持稳定源 key、kind、operation key 和旧票据语义；禁止推算连续自增 ID、忽略冲突或预分配整个 source。
- [x] 事务成功后才更新内存镜像；回滚、取消、连接故障及提交响应丢失不得留下虚假成功映射，UnknownCommit 仍全局停止。
- [x] 覆盖全新、全已有、混合、重复和冲突请求、自增间隙及其他合法身份分配，真实 MySQL 验证身份映射。
- [x] 从迁移入口验证进程重启和原 manifest 续跑不重复导入；票据 SQL/事务计数按受限块增长，并保留 source 隔离和独立发布。


## Answer

- 新增仅支持 Message 的 allocate_many；保留单条 allocate 兼容性，固定 SQL owner，不预分配整个 source。正文与归档消息通过 DirectImporter / ParallelWorkspaceImporter 的受限消息批次接入；owner router 仅传递 detached 参数与结果。
- 每块最多 100 行，同时受 256 KiB 与物理租约 max_allowed_packet 安全预算限制。一个事务内锁定已有票据、prepared 多行插入缺失票据，按 migration_id + entry_kind + source_key 重读真实 ID，以 target_id=id 集合回填并全量核对，不使用 last-insert-ID 推算。
- 保留原 source key、kind、operation key。重复请求身份明确拒绝；已有、混合、映射冲突、packet 超限、回滚、取消及 UnknownCommit 重启恢复有回归，提交确认前不写入镜像。
- TDD 证据：新增初始测试 5 failed（allocate_many 缺失）→ 5 passed；真实连接门面 packet 回归 1 failed（Connection 无 packet 属性）→ 8 passed。
- 提交：f5dd43151（批量票据）、1ac41c86f（真实导入调用链）、93cdc0ead（物理租约 packet 预算）。三个提交均运行并通过全部项目 pre-commit hooks，未绕过。已合并集成 tip 5c7fe8879。
- 验证：会话存储全量单测 1613 passed（packet 回归新增前），最新相关回归 81 passed；新增真实 MySQL test_batch_tickets_mysql.py，现有 test_v3_migration_mysql.py 负责真实迁移入口中断、manifest 重载和续跑。两项在本地因未配置隔离 MySQL 而 skipped，不作为 MySQL 验收证据。
- 限制：真实 MySQL 身份映射、并发合法分配及完整 source 独立发布验收由集成阶段统一执行；本 ticket 未改 Turn / Session / Chat / Publication 批量分配和 ticket 04。
