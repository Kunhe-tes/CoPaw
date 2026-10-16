# Tracing 写入确认、有界队列与关闭

适用于 Span 缺失、trace 过早完成、数据库变慢时内存增长，以及关闭阶段挂起的排查。实现入口为 `src/swe/tracing/writer.py`，管理器装配位于 `manager.py`，SQL 位于 `store.py`。设计见 [专项方案](../../docs/superpowers/specs/2026-10-16-tracing-bounded-writer-design.md)。

## 确认边界

`emit_span` / `update_span` 成功返回表示该版本已被 writer 接纳；队列满时等待容量，可以取消。它们不等待数据库提交。单个 writer 持有排队、正在写入和待重试的数据，写入成功之前不释放容量。

`end_trace` 捕获该 trace 已接纳的版本，包括正在 INSERT 的 Span 及其后续更新；只有这些版本确认后才更新 trace 状态。超时或数据库失败不会把 active trace 标为完成。调用者取消 flush 等待不会取消共享 writer。屏障之后才接纳的新版本不属于该次屏障，调用方仍需按先写 Span、后结束 trace 的顺序使用。

批量 INSERT 使用稳定 `span_id` 的可重复 upsert，aiomysql 内部分拆的 SQL 放在同一事务中；未知提交结果可重试。MySQL affected rows 可能为 0、1 或 2，不能用它判断确认了多少 Span。UPDATE 失败同样保留所有权，按最新接纳版本重试。writer 使用空 Context 启动，不继承请求的数据库事务或租户上下文，来源标识保存在 Span 本身。

## 容量与超时

| 配置 | 默认值 | 边界 |
|---|---|---|
| `batch_size` | 100 | 每批最多行数 |
| `max_batch_bytes` | 256 KiB | 每批 SQL 文本的保守估算预算 |
| `max_queue_spans` | 10000 | 未确认 Span 数，包含正在写入与重试 |
| `max_queue_bytes` | 8 MiB | 未确认数据的保守估算预算 |
| `flush_interval` | 5 秒 | 未触发行数/字节阈值时唤醒 writer 的间隔 |
| `write_timeout` | 30 秒 | flush / end_trace 的确认等待 |
| `shutdown_timeout` | 30 秒 | close 的排空等待 |

单条超大 Span 只在队列无其他 Span 时接纳，并单独写入；这是字节预算的显式例外，保留原 payload，不做静默截断。接纳时深拷贝输入，避免调用者后续修改绕过预算。估算包含 JSON Unicode 转义及 SQL 转义余量，可能明显高估；不是 RSS 上限，调用方等待中的输入、对象开销和一个批次快照另计。

close 停止接纳、唤醒等待容量的生产者，然后等待排空。manager 的共享关闭任务不会被单个调用者取消。超过期限后取消 writer，额外等待最多 `min(shutdown_timeout, 1 秒)` 的取消宽限期；使用 `asyncio.wait`，避免 `wait_for(task)` 在超时后继续等待取消清理。仍未退出则保留未确认记录并报告数量/估算字节及 `writer still running after cancellation`，不继续阻塞 close。manager 在后台等待 writer 真正退出后才关闭存储，避免连接池 close 再次等待同一个卡住的连接；晚到的清理异常会记录日志。协作式取消无法强杀不响应的协程，该任务和资源可能持续存活至退出或进程被终止。内存数据没有持久化 spool，Pod 被强制终止仍可能丢失。

## 日志与排查顺序

1. `Tracing write failed; retaining batch`：检查后续数据库异常；writer 按 0.1 秒到 5 秒的封顶退避重试，不静默丢弃数据。
2. `Tracing writes remain unconfirmed`：确认屏障超时；检查数据库可用性、超大 payload 和前方失败批次。超时不等于数据库一定未提交。
3. `Tracing shutdown timed out: ... unconfirmed spans`：排空未完成，关闭向上抛出 `TimeoutError`；不要把此日志解释为正常落库完成。
4. `Failed to roll back cancelled transaction`：aiomysql 可能在取消查询后已关闭连接，rollback 再次失败。数据库适配器必须保留原 `CancelledError`，否则 writer 会误判为可重试错误，使关闭期限失效。
5. `Tracing writer failed during cancellation cleanup`：writer 在取消宽限期内以异常退出。close 会读取任务异常并记录原 traceback，最终仍向调用方报告关闭超时及未确认数量；不能只调用 `asyncio.wait` 而不消费完成任务的异常。宽限期之后退出的异常由 manager 的延后关闭任务记录。

持续非法 payload 或永久数据库错误会阻塞后续批次并最终触发背压/超时；本轮没有新增丢弃、死信或磁盘补偿策略。JSON 构造、深拷贝和 aiomysql 参数转义仍消耗 loop CPU，分块只限制普通批次工作量；单条超大数据仍可能产生长停顿。数据库迁移保持暂停。

## 验证

专项测试通过 Event 控制 INSERT/UPDATE、取消和关闭顺序，覆盖正在写入时的屏障、未知提交重试、更新失败、容量、超大行、Context 隔离及 rollback 失败。使用项目虚拟环境运行 `tests/unit/tracing` 与相关 SDK/runner/API 测试；本轮共 285 项通过，修改文件 pre-commit 检查通过。未做真实 MySQL 联调或生产并发压测，不能据此推断吞吐或 p99 收益。
