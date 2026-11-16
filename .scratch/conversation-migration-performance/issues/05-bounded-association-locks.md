# 05: 收窄消息关联锁并实现集合加锁

**What to build:** 导入长会话时，每个消息批次仅锁实际使用的关联行，并使用有界集合查询减少数据库往返，保持逐行关联和执行状态保护。

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] 消息批次只声明必要 Session 与本批实际引用的 Chat、Turn，避免每批传入整个 Session 的 Turn 集合。
- [x] 集合查询保持固定表顺序和确定 ID 组织，受行数和参数预算限制；缺失 ID 在结果中显式处理。
- [x] 保留每行 scope、Session/Chat/Turn 关系、活跃执行及离线权限检查，不因缩小集合漏掉隐含关联。
- [ ] 在真实 MySQL 验证执行计划、现有行与缺失行锁定、并发冲突和回滚行为，不以 ORDER BY 或假数据库代替锁验收。
- [x] 长 Session、多消息批次及交叉关联场景证明查询量随实际引用集合分块增长，不随全部 Turn 数乘以批次数放大。
- [ ] 通过现有迁移入口验证坏 source 隔离、完整会话结果、续跑及 source 独立发布。

## Answer

- 提交 `5344dc8c5`：消息批次仅声明本批实际引用的 Chat/Turn 和必要 Session；锁按 Session → Chat → Turn、ID 升序组织，每查询最多 100 个 ID，受 256 KiB、服务器 packet 安全预算及参数上限约束。缺失 ID 显式缓存 None；原逐行 scope、关系、活跃执行及离线权限校验保留。
- 旧作业兼容：仅消息批次续跑既有 durable/committed/recovered bundle 时生成精确旧版候选，原 import_plan 必须与新版或完整旧版候选逐字节相同。行、更新、身份、scope、schema 和 publication 不放宽；保留原计划字节和验证/提交逻辑，拒绝任意锁超集。ParallelWorkspaceContext 增加受限 NAS-only IO 能力，新写入不增加兼容读取。
- TDD：最初两项分别因逐行 SQL、整个会话关联声明失败后通过；兼容性两项先因缺少 retained_plan 失败后通过。覆盖 packet 分块、缺失行、跨 source/关系/活跃执行拒绝、prepared/committed 旧计划续跑及精确候选拒绝。
- 项目完整提交 hooks（mypy/black/flake8/pylint 等）通过，无绕过。合并最新集成分支 `b802c1f96` 后相关回归 186 passed。MySQL 新用例 2 skipped，未配置数据库，不作为锁验收。
- 新增真实 MySQL `test_migration_association_locks_mysql.py`：现有 Turn UPDATE、缺失 Turn INSERT 争锁 timeout，持有方 rollback 后重试成功，并记录 EXPLAIN。真实锁、执行计划及 source 独立发布验收由集成阶段统一执行，上方对应两项仍未勾选。
- 稳定合并后的完整 `tests/unit/app/conversation_storage`：1663 passed in 67.28s；隔离 MySQL 未配置，新增两项再次明确 skipped。最终工作树干净，不推送。
- 2026-11-16 独立复核修正验收用例：集中隔离 MySQL 红灯明确为两项 `DatabaseSession.transaction` AttributeError。事务改由已 acquire 固定连接内的 `db.transaction()` / `other.transaction()` 管理；保留 errno 1205 冲突断言及持有方 rollback 后写入成功断言。缺失行场景另放置无关 Turn，EXPLAIN 对已有主键探针执行同形查询并严格要求 PRIMARY，避免空表或不存在常量被优化成无索引计划而虚假通过；缺失 ID 的实际锁保护仍由 INSERT 阻塞与释放后成功证明，不宣称该探针证明缺失行执行计划或精确锁顺序。未改生产代码。修正后本地关联锁回归 10 passed、真实 MySQL 2 skipped；集中真实 MySQL 重跑待集成执行，上方锁验收项仍不勾选。
