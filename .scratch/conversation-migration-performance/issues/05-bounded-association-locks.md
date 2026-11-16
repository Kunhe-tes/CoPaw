# 05: 收窄消息关联锁并实现集合加锁

**What to build:** 导入长会话时，每个消息批次仅锁实际使用的关联行，并使用有界集合查询减少数据库往返，保持逐行关联和执行状态保护。

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] 消息批次只声明必要 Session 与本批实际引用的 Chat、Turn，避免每批传入整个 Session 的 Turn 集合。
- [ ] 集合查询保持固定表顺序和确定 ID 组织，受行数和参数预算限制；缺失 ID 在结果中显式处理。
- [ ] 保留每行 scope、Session/Chat/Turn 关系、活跃执行及离线权限检查，不因缩小集合漏掉隐含关联。
- [ ] 在真实 MySQL 验证执行计划、现有行与缺失行锁定、并发冲突和回滚行为，不以 ORDER BY 或假数据库代替锁验收。
- [ ] 长 Session、多消息批次及交叉关联场景证明查询量随实际引用集合分块增长，不随全部 Turn 数乘以批次数放大。
- [ ] 通过现有迁移入口验证坏 source 隔离、完整会话结果、续跑及 source 独立发布。
