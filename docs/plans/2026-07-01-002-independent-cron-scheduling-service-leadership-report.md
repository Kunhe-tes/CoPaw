# 独立定时调度服务工作说明

## 结论

批量定时任务的调度职责已经从 SWE 执行进程和 Monitor 观测进程中拆出，放到新的顶层 `scheduler` 服务。SWE 只负责收到内部 callback 后执行对应任务；Monitor 只负责存储和展示 cron/execution/dispatch 相关记录。

## 本次解决的问题

- 外部调度平台 callback 不再误触发 batch-managed 任务。
- 调度分发和 worker 数量调整拆开。
- 任务完成后可以立即补发下一条任务，不必等待下一轮容量调整。
- 失败重试和调度日志有结构化落库。
- 后续迁移所有定时任务时，有清晰的新服务边界。

## 当前交付

- 新增顶层 `scheduler` 服务。
- `CronSchedulingService` 和 `CronDispatchIntentService` 迁入 Scheduler。
- Monitor 不再启动调度 loop。
- SWE callback 增加 `callback_source=dispatch_service` 来源判断。
- 批量任务的外部 callback 默认跳过。
- Scheduler callback 会把 intent/batch 信息写入 SWE execution meta。
- SWE dispatch-managed execution feedback 会发送到 Scheduler。
- Scheduler 持久化 execution 后更新 intent，并立即尝试补发下一条任务。
- 普通定时任务旧路径保留，本次不迁移。

## 风险和后续

- 新服务目前接管的是 batch dispatch 骨架，还没有接管所有 cron due-time 计算。
- 如果 Scheduler 多实例运行，需要补 leader lease。
- 普通定时任务迁移要单独做方案，不能和本次 batch dispatch 混在一起。

## 对外说明话术

这次不是单纯调大 worker 数，而是把调度职责从 SWE 执行进程和 Monitor 观测进程中拆出来。新的 Scheduler 服务决定什么时候发、发几个、失败后什么时候重试；SWE 只负责执行；Monitor 只负责记录和展示。这样后续不管是广播任务还是普通定时任务，都可以逐步进入同一个可观测、可控制、可回滚的调度体系。
