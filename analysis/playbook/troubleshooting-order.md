# 排查顺序

目标是先拿到最短闭环证据，再收敛范围，而不是一开始就全仓搜索。

## 会话迁移 source 选择与注册

- 先按阶段指标区分 registration、automatic_review、selection；自动重审首次注册后恢复 automatic_review 阶段，避免把重审耗时归入注册。
- 选择与预览的状态读取每块最多256个完整 source/tenant 身份；601个对象应为3次状态SQL，而最终发布仍依赖原来的权威SQL核对。
- 同命令自动重审已注册或原子修订证据后，执行前仍完整核对job binding，但不再做第二轮完整注册；新冲突应在读取输入前失败。
- TenantManifest 的分组位置索引共享控制索引磁盘预算；证据revision、集合替换或长度变化后重建，命令退出时关闭。容量不足须明确失败，不能退回无界内存缓存。回归入口为 test_registration_performance.py 与 test_tenant_orchestration.py。
