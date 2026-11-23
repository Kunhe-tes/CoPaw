# Tracing 写入确认、有界队列与关闭

适用于 Span 缺失、trace 过早完成、数据库变慢时内存增长，以及关闭阶段挂起的排查。实现入口为 `src/swe/tracing/writer.py`，管理器装配位于 `manager.py`，SQL 位于 `store.py`。设计见 [专项方案](../../docs/superpowers/specs/2026-10-16-tracing-bounded-writer-design.md)。

## 确认边界

`emit_span` / `update_span` 成功返回表示该版本已被 writer 接纳。队列满时，生产者等待容量，可以取消。单个 writer 持有排队、正在写入和待重试的数据，写入确认或放弃后释放容量。

`end_trace` 捕获该 trace 已接纳的版本，包括正在 INSERT 的 Span 及其后续更新；只有这些版本确认后才更新 trace 状态。超时或数据库失败不会把 active trace 标为完成。调用者取消 flush 等待不会取消共享 writer。屏障之后才接纳的新版本不属于该次屏障，调用方仍需按先写 Span、后结束 trace 的顺序使用。

技能检测收尾可能补写 Span，因此 `end_trace` 在封闭该 trace 的接纳入口前调用 `_end_skill_detection`。排查写入重试时，若失败的 Span 版本已被更新，`_retry_failed_batch` 会重置失败次数并把新版本留在队列中。

批量 INSERT 使用稳定 `span_id` 的可重复 upsert，官方 aio 驱动的多行 prepared 传输块放在同一事务中；未知提交结果可重试。MySQL affected rows 可能为 0、1 或 2，不能用它判断确认了多少 Span。UPDATE 失败同样保留所有权，按最新接纳版本重试。writer 使用空 Context 启动，不继承请求的数据库事务或租户上下文，来源标识保存在 Span 本身。

## 容量与超时

| 配置 | 默认值 | 边界 |
|---|---|---|
| `batch_size` | 100 | 每批最多行数 |
| `max_batch_bytes` | 256 KiB | 每批 payload 的保守估算预算 |
| `max_queue_spans` | 10000 | 未确认 Span 数，包含正在写入与重试 |
| `max_queue_bytes` | 8 MiB | 未确认数据的保守估算预算 |
| `flush_interval` | 5 秒 | 未触发行数/字节阈值时唤醒 writer 的间隔 |
| `write_timeout` | 30 秒 | flush / end_trace 的确认等待 |
| `shutdown_timeout` | 30 秒 | close 的排空等待 |

单条超大 Span 只在队列无其他 Span 时接纳，并单独写入；这是字节预算的显式例外，保留原 payload，不做静默截断。接纳时深拷贝输入，避免调用者后续修改绕过预算。估算包含 JSON Unicode 转义及 SQL 转义余量，可能明显高估；不是 RSS 上限，调用方等待中的输入、对象开销和一个批次快照另计。

close 停止接纳、唤醒等待容量的生产者，然后等待排空。manager 的共享关闭任务不会被单个调用者取消。超过期限后取消 writer，额外等待最多 `min(shutdown_timeout, 1 秒)` 的取消宽限期；使用 `asyncio.wait`，避免 `wait_for(task)` 在超时后继续等待取消清理。仍未退出则保留未确认记录并报告数量/估算字节及 `writer still running after cancellation`，不继续阻塞 close。manager 在后台等待 writer 真正退出后才关闭存储，避免连接池 close 再次等待同一个卡住的连接；晚到的清理异常会记录日志。协作式取消无法强杀不响应的协程，该任务和资源可能持续存活至退出或进程被终止。内存数据没有持久化 spool，Pod 被强制终止仍可能丢失。

## 日志与排查顺序

单条和批量插入都按 `VARCHAR(256)` 保留 Span 名称的前 256 个字符。旧库若仍使用 `VARCHAR(128)`，部署前需将该列扩到至少 256 个字符。

1. 旧版本出现 `Tracing write failed; retaining batch` 时，失败批次会被放回队首并持续退避重试。若底层为 `1406 (22001): Data too long for column 'name'`，核对 Pod 镜像、`swe_tracing_spans.name` 的实际列定义及 Span 名称长度。队列写满后，其他请求可能在调用模型前等待 Span 接纳。
2. 当前版本出现 `Tracing batch failed; isolating individual writes` 时，writer 将批次拆为单条写入。单条写入失败三次后记录 `Dropping tracing span after ... failed write attempts`，释放该条容量并标记对应 trace 未确认。`Tracing writes remain unconfirmed` 可能来自等待超时，也可能来自丢弃。
3. `Tracing shutdown timed out: ... unconfirmed spans`：排空未完成，关闭向上抛出 `TimeoutError`；不要把此日志解释为正常落库完成。
4. `Database transaction rollback failed` / `Database background operation failed`：数据库取消后的回滚或清理失败。适配器保留原始异常/取消，无法确认的连接隔离，清理实际完成前仍占容量；检查随后是否出现 `Database pool close left ... unconfirmed connection(s)`。shutdown 失败的连接保留隔离槽位，同一对象拒绝重连，需排查驱动/网络并按进程生命周期回收。
5. `Tracing writer failed during cancellation cleanup`：writer 在取消宽限期内以异常退出。close 会读取任务异常并记录原 traceback，最终仍向调用方报告关闭超时及未确认数量；不能只调用 `asyncio.wait` 而不消费完成任务的异常。宽限期之后退出的异常由 manager 的延后关闭任务记录。

持续出现非法 payload 或数据库故障时，重试仍可能降低队列吞吐并触发背压。JSON 构造、深拷贝、UTF-8 与官方驱动二进制编码仍消耗 loop CPU，分块只限制普通批次工作量；单条超大数据仍可能产生长停顿。核心驱动现使用 mysql.connector.aio，Span prepared 路径不再做 SQL 参数转义。见 [核心驱动设计](../../docs/superpowers/specs/2026-10-16-mysql-driver-migration-design.md) 和 [数据库接入](../../docs/database-access.md)。prepared 缓存按物理连接最多4种形状，数据不进入 SQL。

## 验证

专项测试通过 Event 控制 INSERT/UPDATE、取消和关闭顺序，覆盖正在写入时的屏障、未知提交重试、更新失败、容量、超大行、Context 隔离及 rollback 失败。使用项目虚拟环境运行 `tests/unit/tracing` 与相关 SDK/runner/API 测试；另补数据库池/事务/协议契约测试；迁移扩大回归共581项通过，1项隔离库测试默认跳过，修改文件静态检查通过。未做真实 MySQL 联调或生产并发压测，不能据此推断吞吐或 p99 收益。
