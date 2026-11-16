# 03: 消息票据批量分配与安全续跑

**What to build:** migrate 按受限消息批次分配持久票据，减少逐消息事务，同时正确恢复已有与缺失票据混合的作业。

**Blocked by:** None (can start immediately).

**Status:** claimed

- [ ] 增加有界批量分配能力并接入 Message 导入调用链，保留现有单条接口及 SQL owner 限制。
- [ ] 一个受限事务内检查和锁定已有票据、插入缺失票据、按完整唯一键重读真实 ID、回填并核对 target_id=id。
- [ ] 保持稳定源 key、kind、operation key 和旧票据语义；禁止推算连续自增 ID、忽略冲突或预分配整个 source。
- [ ] 事务成功后才更新内存镜像；回滚、取消、连接故障及提交响应丢失不得留下虚假成功映射，UnknownCommit 仍全局停止。
- [ ] 覆盖全新、全已有、混合、重复和冲突请求、自增间隙及其他合法身份分配，真实 MySQL 验证身份映射。
- [ ] 从迁移入口验证进程重启和原 manifest 续跑不重复导入；票据 SQL/事务计数按受限块增长，并保留 source 隔离和独立发布。
