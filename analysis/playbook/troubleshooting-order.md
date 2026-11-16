# 排查顺序

目标是先拿到最短闭环证据，再收敛范围，而不是一开始就全仓搜索。

## 会话迁移 source 选择与注册

- 先按阶段指标区分 registration、automatic_review、selection；自动重审首次注册后恢复 automatic_review 阶段，避免把重审耗时归入注册。
- 选择与预览的状态读取每块最多256个完整 source/tenant 身份；601个对象应为3次状态SQL，而最终发布仍依赖原来的权威SQL核对。
- 同命令自动重审已注册或原子修订证据后，执行前仍完整核对job binding，但不再做第二轮完整注册；新冲突应在读取输入前失败。
- TenantManifest 的分组位置索引共享控制索引磁盘预算；证据revision、集合替换或长度变化后重建，命令退出时关闭。容量不足须明确失败，不能退回无界内存缓存。回归入口为 test_registration_performance.py 与 test_tenant_orchestration.py。

## 会话迁移 binding 与 manifest IO

- 先看 binding_serializations / binding_serialized_bytes / binding_serialization_seconds，判断完整作业绑定编码的实际成本；嵌套服务、workspace、tenant证据、cutoff和target仍须与SQL不可变绑定精确核对，不能凭集合身份或revision跳过。
- manifest_write_attempts 统计尝试，manifest_writes / manifest_written_bytes 只统计完成原子替换及目录fsync的检查点；manifest_write_seconds 包含失败尝试的耗时。失败写入可能已经替换文件但目录fsync未完成，不能把未计为完成理解为文件必然未改变。
- 当前没有放宽持久化频率或跨命令缓存。回归入口为 test_migration_progress.py 的写盘故障与UTF-8计量测试，以及 test_v3_journal.py 的嵌套绑定变化/重新加载检查；小型本地fixture不能替代真实NAS和完整迁移耗时验收。
