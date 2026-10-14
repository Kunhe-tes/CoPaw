# 事件循环与 worker 执行边界

适用于工具输出、checkpoint、Provider 配置和 S3 备份相关的延迟排查。阶段 A 设计见 [专项方案](../../docs/superpowers/specs/2026-10-13-event-loop-hotspots-design.md)。

## 当前入口

| 工作 | 异步入口 | 执行位置 |
|------|----------|----------|
| 即时及历史工具输出压缩 | `compact_tool_result_messages_async` | 独立输出 executor，进程级最多 4 个已提交任务 |
| Shell 完整输出解码及格式化 | `run_output_work` | 与压缩共用输出 executor；实时小块读流仍在 loop |
| 请求内存绑定 | `ReMeLightMemoryManager.prepare_request_memory` | 现有 runtime-state worker |
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

阶段 A 尚未解决全历史 artifact 重读、Shell 无界输出积累、恢复重复枚举和默认 runtime-state executor 的容量隔离。Provider 副本捕获后稳定；既有 builtin Provider 逐字段刷新仍不提供捕获时的事务快照。
