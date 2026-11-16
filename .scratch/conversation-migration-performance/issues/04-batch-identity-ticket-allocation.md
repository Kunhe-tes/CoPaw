# 04: 扩展身份票据批量分配

**What to build:** 将消息票据已验证的批量恢复协议扩展到 Turn、Session、Chat 和满足 scope 核对要求的 Publication，使会话身份导入同样减少逐条事务。

**Blocked by:** 03 — 消息票据批量分配与安全续跑。

**Status:** resolved

- [x] 按依赖顺序接入 Turn、Session、Chat 的有界分配，不改变原有实体关系、稳定位置及发布顺序。
- [x] Publication 最后接入；逐项核对 scope、scope kind、operation key 与正文定位，并兼容已有可恢复票据。
- [x] 保留单条分配及旧 manifest 的行为，不更改 schema、票据或 bundle 格式，不跨 source 合并事务。
- [x] 混合新旧票据、scope 冲突、非法身份及缺失恢复信息必须明确拒绝，不静默重绑。
- [x] 集成验证包含多 Session/Chat/Turn、归档、分享、事件与 checkpoint 的导入、恢复核对和独立发布。
- [x] SQL/事务计数显示已接入实体按块分配，提交不确定仍全局停止，已发布 source 在线新增身份不受影响。


## Answer

- 扩展 SQL journal 的有界 allocate_many 到 Session、Chat、Turn 和 Publication；保留行数、字节、packet 及唯一 SQL owner 限制，不跨 source 合并事务。
- Publication 逐项核对 scope、scope_kind、operation key 和 bundle 相对路径；缺失旧 details 可在显式可信 scope 下事务回填，混合旧/新票据仍按完整唯一键重读真实 ID。非法整数身份和身份行不一致明确拒绝；提交不确定不更新 manifest 镜像。
- 导入器按现有依赖接入有界 Session、同 Session 的 Chat、Turn 分配；仅为同 scope 且依赖等价的 Turn identity / recovery publication 组批量预分配，publication 的业务写入及发布顺序不变。旧 manifest 继续按首次使用分配身份；未修改关联锁声明。
- 验证：新增测试先失败，覆盖五种身份、混合恢复、非连续自增 ID、scope/kind/path/operation 冲突、旧 details 回填、非法身份、UnknownCommit、多 Session/Chat/Turn 关联与重试，以及旧 manifest 首次分配顺序。完整 conversation_storage 单元测试 1671 项通过（追加兼容顺序回归后复验见提交记录）；所有配置提交 hooks 正常执行，无绕过。
- 隔离 MySQL 集成测试已扩展五种身份的自增间隙及重启混合恢复；本工作树未运行真实 MySQL，由集成分支集中执行。真实 NAS 和现场性能不在本票交付范围，不宣称墙钟加速倍数。
- 本分支完成前合入集成分支 33a7daa65。
