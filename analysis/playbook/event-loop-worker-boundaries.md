# 事件循环与 worker 执行边界

适用于工具输出、checkpoint、Provider 配置和 S3 备份相关的延迟排查。阶段 A 设计见 [专项方案](../../docs/superpowers/specs/2026-10-13-event-loop-hotspots-design.md)。

## 当前入口

| 工作 | 异步入口 | 执行位置 |
|------|----------|----------|
| 即时及历史工具输出压缩 | `compact_tool_result_messages_async` | 独立输出 executor，当前进程级最多 8 个已提交任务（用户调整） |
| Shell 流式落盘、完整输出解码及格式化 | `run_shell_spool_work` / `run_output_work` | 与压缩共用输出 executor；Unix pipe 每 4 KiB 读流仍在 loop |
| 请求内存绑定 | `ReMeLightMemoryManager.prepare_request_memory` | 独立 runtime-state executor，最多 8 个已提交任务，Chat 锁内仅读 epoch |
| Query 模型配置准备 | `prepare_model_config_async` | 现有 Provider executor；模型客户端仍在 loop 构造 |
| S3 构造、分页及选择 | `run_backup_io` | 独立备份 executor，进程级最多 4 个已提交任务 |

## 取消与并发规则

- 已提交的线程任务不能由协程取消停止。必须在线程真实完成时释放并发许可；提前释放会使运行任务数超过预算。
- 提交前等待容量，避免 ThreadPoolExecutor 的内部队列无限积累。等待协程数量仍受请求并发影响。
- 通过 `copy_context()` 传播请求的租户、来源和 tracing 上下文。
- shield 后的 Future 要消费异常，否则请求取消后工作失败会产生 `Future exception was never retrieved`；正常 await 仍应收到原异常。
- 输出压缩在 worker 内复制内容，返回 loop 后应用。取消不应用结果；没有变化的内容保持原对象。请求应独占消息内容，不能在 worker 执行时原地修改同一内容。
- 备份初始化 await 放在任务互斥锁内、409 检查之后；保存任务到启动任务之间没有 await，避免初始化取消留下未启动的 PENDING 任务。TaskStore 原有判忙范围仍是 RUNNING。

## 验证与解释结果

线程边界测试应记录线程 ID，并用 `threading.Event` 控制阻塞、取消与完成顺序。Provider 测试同时验证客户端在 loop 构造、构造时不重新读取配置；checkpoint 测试验证绑定和工具注册复用同一 epoch。

扩大测试失败时，在相同虚拟环境中运行基线源码，区分已有失败与本次回归。2026-10-13 分支基线存在 10 个 Shell/安全规则测试失败，涉及引号断言、日志捕获和网络传输规则；本次保留原语义。

worker 可以降低同步 I/O 对 loop 的阻塞，但线程中的 Python CPU 工作仍可能竞争 GIL。应测量 loop 延迟、排队时间、运行时间及 RSS，不能仅凭线程 ID 宣称吞吐提升。

历史 artifact 阶段 B 已采用有限头尾读取与展示缓存，容量常量位于 `tool_output_compaction.py`：`_DISPLAY_CACHE_MAX_ENTRIES=128`、`_DISPLAY_CACHE_MAX_BYTES=4*1024*1024`。文件 metadata 与恢复引用参与缓存键，缓存之前必须验证 artifact 仍位于 resolved workspace 内；只检查 resolved tool_result 父目录不足以拒绝整个目录指向外部的 symlink。

清理常量为 `_CLEANUP_INTERVAL_SECONDS=300`、`_CLEANUP_MAX_ENTRIES=128`，按目录与 retention_days 隔离；超出记录容量的冷目录可能提前重扫。显式同步清理不节流。

Unix Shell 在启用工具压缩的调用上下文使用有限缓冲与流式 spool，完整格式化 artifact 复用 canonical 截断引用。每条 pipe 原始缓冲最多 budget，另计 pipe、64 KiB 解码缓冲和其他对象开销；Windows、未启用压缩、磁盘失败回退仍为全输出。取消后必须等待真实 spool worker 结束再关闭文件，重复取消也遵守此规则。

checkpoint 绑定在 Chat 锁内只读 epoch；record/events 的损坏校验由完整状态消费者执行，写入/fsync 和持久化保证保留。runtime-state 使用独立 8 线程预算，避免默认 executor 饱和阻塞状态读取。SSE 历史入队与消费每 64 条让出 loop，锁仍覆盖完整重放，不减少队列内存。

`runtime_diagnostic` 日志包含 loop p95/p99、样本数、RSS 采样峰值和 `performance_metrics`。worker 排队/执行分位数来自最近 2048 次真实完成任务；完成次数、checkpoint 读取字节/调用、S3 分页尝试次数是本进程累计。loop/RSS 则是两次日志之间的窗口；原诊断采样周期 10 秒，采样峰值不等于瞬时峰值。checkpoint 计量限 active-state epoch/record/events，S3 计量限 list_backups 的 list_objects_v2 尝试（不含 SDK 内部重试）。无租户/路径标签，Pod 之间的分位数不能直接平均。

专项脚本与原始结果见 [性能记录](../../docs/superpowers/benchmarks/2026-10-14-event-loop-followups.md)。恢复计划复用由用户明确排除本轮。Provider 副本捕获后稳定；既有 builtin Provider 逐字段刷新仍不提供捕获时的事务快照。
