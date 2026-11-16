# 04: 扩展身份票据批量分配

**What to build:** 将消息票据已验证的批量恢复协议扩展到 Turn、Session、Chat 和满足 scope 核对要求的 Publication，使会话身份导入同样减少逐条事务。

**Blocked by:** 03 — 消息票据批量分配与安全续跑。

**Status:** ready-for-agent

- [ ] 按依赖顺序接入 Turn、Session、Chat 的有界分配，不改变原有实体关系、稳定位置及发布顺序。
- [ ] Publication 最后接入；逐项核对 scope、scope kind、operation key 与正文定位，并兼容已有可恢复票据。
- [ ] 保留单条分配及旧 manifest 的行为，不更改 schema、票据或 bundle 格式，不跨 source 合并事务。
- [ ] 混合新旧票据、scope 冲突、非法身份及缺失恢复信息必须明确拒绝，不静默重绑。
- [ ] 集成验证包含多 Session/Chat/Turn、归档、分享、事件与 checkpoint 的导入、恢复核对和独立发布。
- [ ] SQL/事务计数显示已接入实体按块分配，提交不确定仍全局停止，已发布 source 在线新增身份不受影响。
