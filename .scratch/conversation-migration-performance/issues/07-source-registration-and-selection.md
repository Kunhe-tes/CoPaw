# 07: 消除 source 注册与选择阶段的重复工作

**What to build:** prepare 与 migrate 在注册、自动重审后选择和跳过已发布 source 时减少重复查询及全列表过滤，使多个小 source 的固定开销更低。

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] 区分初次注册与自动重审后的差异核对，避免无差异的完整重复注册，保留 immutable job binding 和证据一致性检查。
- [x] 对选择及重审所需状态进行有界批量读取，不把缓存状态代替发布时的权威 SQL 核对。
- [x] source 视图使用预算内只读分组索引，证据修订后更新或失效，不持有无界重复数据。
- [x] 全部发现失败、部分已发布、证据修订、新出现冲突和旧 tenant 级作业均保持既有行为。
- [x] 通过现有 CLI 入口验证正常 source 继续、失败者记录、已发布者不重读旧输入且不覆盖新数据。
- [x] 小 source 数量增长时，计数证明消除重复完整注册与逐 source 状态查询，报告预算和结果一致性。

## Answer

- 实现 c95b1defb；正常提交 hooks 包括 mypy、black、flake8、pylint 全通过。基于集成 54aaff00b，完成前合入最新集成 33a7daa65（merge 25f47bfee）。
- TDD 先红：批量状态接口缺失、601 个已发布 source 仍构建输入视图、40 个 source 重复扫描40次、自动重审后注册2次、跨命令已关闭索引仍复用；实现后均绿。
- 状态读取按最多256个完整身份分块，仅保留单块状态；601 source/tenant 均为3次 SQL。选择、自动重审和只读预览使用此路径；最终状态转换和发布仍执行原 SQL 权威核对。
- 自动重审保留初次注册及审计修订事务，执行前继续完整核对 immutable job binding，省去第二遍无差异完整注册。失败全量作业、旧 tenant 作业和冲突保护保留。
- 分组索引只存集合位置，证据不复制到索引；与其他控制索引共享磁盘预算，读取每块最多256位置。40 source 的每个集合仅扫描1次；64KiB预算耗尽明确失败。集合替换、长度或 evidence revision 变化及命令退出关闭后重建。
- 本地目录 storage 与 CLI 回归：1709 passed in 78.98s；包含正常继续、失败记录、已发布 source 跳过、证据修订及旧作业测试。最终隔离 MySQL、真实 NAS 和生产验收由10集中执行，本票未访问远程数据库。
