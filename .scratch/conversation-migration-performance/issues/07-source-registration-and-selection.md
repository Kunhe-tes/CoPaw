# 07: 消除 source 注册与选择阶段的重复工作

**What to build:** prepare 与 migrate 在注册、自动重审后选择和跳过已发布 source 时减少重复查询及全列表过滤，使多个小 source 的固定开销更低。

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] 区分初次注册与自动重审后的差异核对，避免无差异的完整重复注册，保留 immutable job binding 和证据一致性检查。
- [ ] 对选择及重审所需状态进行有界批量读取，不把缓存状态代替发布时的权威 SQL 核对。
- [ ] source 视图使用预算内只读分组索引，证据修订后更新或失效，不持有无界重复数据。
- [ ] 全部发现失败、部分已发布、证据修订、新出现冲突和旧 tenant 级作业均保持既有行为。
- [ ] 通过现有 CLI 入口验证正常 source 继续、失败者记录、已发布者不重读旧输入且不覆盖新数据。
- [ ] 小 source 数量增长时，计数证明消除重复完整注册与逐 source 状态查询，报告预算和结果一致性。
