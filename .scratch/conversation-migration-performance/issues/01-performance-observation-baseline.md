# 01: 补齐迁移性能观测与可复现基线

**What to build:** 运维人员通过现有 prepare → migrate 入口获得可解释的阶段、数据库与正文 IO 开销，并可在相同输入和资源条件下比较优化前后结果。

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] 区分逻辑数据库调用、实际 SQL 分块、事务开始/提交/回滚，说明各计数口径及是否重叠，不把批量门面调用误当作一次真实 SQL。
- [x] 输出阶段墙钟耗时、处理记录数、bundle 打开及索引解析次数；并发累计 IO 时间与墙钟时间明确区分。
- [x] 指标不含正文、凭据、敏感路径或 SQL 参数，失败及取消后仍保留可解释的进度。
- [x] 复用现有 CLI/编排集成测试边界，提供固定输入与资源条件的本地目录、隔离 MySQL 对照运行方式，不新增迁移人工阶段。
- [x] 基线覆盖多个小 source、单个多消息 source 和部分完成后续跑，记录数据量、预算和环境；不要求万级或真实 NAS 基线。
- [x] 验证观测不会改变 SQL owner、source 隔离、退出语义或迁移结果，并更新指标说明。

## Answer

- TDD: SQL/chunk、事务、阶段计时3项先红；IO观察线程及实际多块reader分别先红0再绿1。观察上下文不传SQL session到IO线程。
- 实现c474c90bd、f07163fea、cb6430e73及ad8fe7bd6；正常hooks均通过。独立merger检视01基础实现并合入；bundle接线纳入最终独立复核。
- 本地全storage/CLI/database回归1724 passed；合入06后观测/bundle/prefetch/database targeted128 passed。
- 真实隔离MySQL代表性prepare→migrate：2 passed in491.26s；3source/3workspace/128消息，正常及坏source修复续跑达到期望发布结果，父/子临时库已清理。无NAS/万级/生产验收。
- 可复现命令、指标口径及基线见docs/superpowers/plans/2026-11-16-conversation-migration-performance-acceptance.md。最终对照由10承担。基线bundle指标0明确标为未观测。
