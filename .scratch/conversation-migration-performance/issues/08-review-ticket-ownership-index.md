# 08: 失败 source 自动重审复用票据归属分析

**What to build:** 一次 migrate 对多个失败 source 自动重审时，复用有界票据归属分析，避免逐 source 全扫作业，仍严格保护部分提交和已发布数据。

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] 在同次受锁保护的重审中建立有界磁盘归属索引或等价分析，完整覆盖实体、批次、分享和 retention 等现有票据规则。
- [x] 维持零业务数据、零迁移票据才可修订证据；已有部分提交且证据未变可续跑，证据改变继续阻断。
- [x] 保留 legacy share、runtime ID、归属不明及孤儿业务行处理，不因索引漏项而放行。
- [x] 写入、证据修订、映射替换或 owner 改变后正确更新或失效；不跨命令沿用证明，不读取已发布 source 旧输入。
- [x] 通过自动重审入口验证多个坏 source、正常同租户 source、部分提交、输入变化和共享故障，重审次数与部分成功语义不变。
- [x] 计数证明多个候选不再各自全扫作业票据，磁盘和内存受预算限制且异常时正确清理。


## Answer

- 在同次受锁保护的只读 candidate-retention 阶段，用现有 DiskMap/IndexPolicy 建立磁盘 owner 集合；ticket 按 1000 行流式读取一次，多候选按 owner 查询。实体、workspace 前缀、batch、share、publication、retention 归属仍调用原解析与 legacy 证明逻辑。
- 每候选保留业务行、orphan、legacy publication/retention guard 检查；runtime_id 仍不阻断。已有票据的候选保留旧证据，并返回 tenant_evidence_locked；其他候选继续修订。
- 生命周期限定于 _retain_committed_failures，无 SQL 写入；finally 关闭临时索引，最终事务另行重读 SQL。SQL owner task 不同直接拒绝；DB 或 frozen mapping 对象替换重新建立索引。索引不跨 review 或命令复用，证据修订和恢复发生时已销毁。
- 首个 RED：四个失败 source 的自动重审入口实测触发 4 次全作业 ticket 扫描，期望 1；实现后同一用例只触发 1 次。另一个 RED 证明 task 继承 ContextVar 可错误复用，现已拒绝。
- 验证：conversation_storage unit suite 1660 passed（57.02s）；补充 task-owner 与完整 ticket-kind 后，聚焦 retry/index/legacy suite 38 passed。覆盖预算耗尽、共享 EIO/数据库异常透传、临时索引清理、mapping 替换、review 后新 ticket 重新检查、legacy guard、未归属 ticket。
- 本任务不连接远程数据库；真实 MySQL 集成和集中性能对比由集成分支统一执行。本地测试计数证明减少重复扫描，不宣称 NAS 或墙钟倍数收益。
