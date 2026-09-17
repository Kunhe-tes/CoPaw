## Context

`/api/internal/cron/callback` 在普通任务路径中会解析 `jobParam`、获取 runtime scope 的 `CronManager`，再调用 `CronManager.run_job()` 创建后台任务。当前单个 job 有 `max_concurrency` semaphore，但 job 定义读取和部分 cron 系统任务文件处理仍会在事件循环上执行同步文件 I/O 与 JSON 处理。

`JsonJobRepository` 当前在 async 方法中直接调用 `Path.read_text()`、`json.loads()`、`model_validate()`、`Path.write_text()` 和 `shutil.move()`。当大量 callback 同时调用 `get_job()` 时，每次都会完整读取并校验 `jobs.json`。dream cron 路径也会同步读取 `dream_logs.json`，归档维护函数由同步函数直接执行。

`MultiAgentManager.get_agent()` 当前在全局 `self._lock` 内完成缓存检查、配置读取、`Workspace` 创建和 `await instance.start()`。这保证了简单的单实例语义，但一个慢 workspace 冷启动会阻塞其他 tenant/agent 的首次加载。GitNexus impact 显示该方法风险为 HIGH，直接影响 Routers、App、Config 多处入口。

## Goals / Non-Goals

**Goals:**

- cron repository 文件读写和大 JSON 处理不阻塞事件循环。
- cron callback 高频 `get_job()` 查询在 `jobs.json` 未变化时复用内存快照。
- dream cron 同步文件读取和归档维护从事件循环移到 worker thread。
- `get_agent()` 保持懒加载和缓存语义，同时允许不同 cache key 的 workspace 并发启动。
- 同一个 cache key 的并发 `get_agent()` 只启动一个 workspace，其他调用等待同一个 inflight 结果。

**Non-Goals:**

- 不引入新的外部队列、Redis semaphore 或 callback dispatcher。
- 不改变 `/api/internal/cron/callback` 的响应协议。
- 不改变 `jobs.json` 文件格式或 cron job schema。
- 不重构 `Workspace.start()`、`ServiceManager` 或 cron 执行主流程。
- 不处理全局 cron 执行并发上限；该项后续单独设计。

## Decisions

### Decision 1: 使用 `asyncio.to_thread` offload repository 读写

`JsonJobRepository.load()` 将同步读取和 `JobsFile.model_validate()` 放到一个同步 helper 中，通过 `asyncio.to_thread()` 调用。`save()` 将目录创建、`model_dump()`、JSON 序列化、临时文件写入和原子替换也放到一个同步 helper 中。

Rationale:
- 当前项目已在 session、backup、workspace zip 等路径使用 `asyncio.to_thread()` 处理文件 I/O，符合现有风格。
- `jobs.json` 读写不仅是磁盘 I/O，还包含 JSON parse/dump 和 pydantic 校验，全部 offload 更能降低 event loop lag。
- 不新增 aiofiles 依赖，也避免 aiofiles 只能覆盖文件 I/O、不能覆盖 JSON CPU 处理的问题。

Alternatives considered:
- 使用 aiofiles：只能解决文件读写，JSON 和 pydantic 仍在 event loop。
- 迁移到数据库：收益更大但超出本次范围，涉及数据迁移和跨进程一致性。

### Decision 2: `JsonJobRepository` 使用 mtime/size 快照缓存和 job 索引

`JsonJobRepository` 增加进程内快照字段：文件签名、`JobsFile` 快照和 `dict[job_id, CronJobSpec]` 索引。`get_job()` 先读取 `stat()` 签名；签名未变化时直接从索引返回。签名变化或缓存为空时走 `load()` 刷新快照。`save()` 成功后同步更新快照，避免同进程写后读再次读取文件。

Rationale:
- callback 的普通 job 路径只需要按 id 读取一个 job，完整读取和线性扫描是高频浪费。
- mtime/size 能兼容同一文件被本进程或其他进程替换的情况。
- 缓存仅作为读取优化，不改变 `jobs.json` 作为事实来源。

Alternatives considered:
- 永久内存表：跨进程或外部修改无法感知，风险较高。
- 每次仍调用 `load()`：offload 后 event loop 不阻塞，但仍会增加线程池和 CPU 压力。

### Decision 3: 缓存一致性以“文件签名变化即刷新”为边界

文件签名使用 `st_mtime_ns`、`st_size`，必要时包含 path 存在性。文件不存在时缓存空 `JobsFile(version=1, jobs=[])`。读取或校验失败不得污染旧缓存；异常应按现有行为向上暴露。保存失败不得更新缓存。

Rationale:
- 保持当前错误语义：损坏的 `jobs.json` 仍应失败，而不是静默返回旧数据。
- 原子替换写入后 mtime/size 会变化，适合当前 `tmp -> move` 模式。

### Decision 4: dream 日志同步函数拆成 async wrapper + sync helper

将 `_load_dream_logs()` 改为 async 方法，内部通过 `asyncio.to_thread()` 调用 `_load_dream_logs_sync()`。`run_dream_archive_maintenance(workspace_dir, actor=...)` 这类同步归档维护调用也通过 `asyncio.to_thread()` 执行。调用点 `_load_dream_record_ids()`、`_dual_write_dream_records()` 调整为 async 并显式 await。

Rationale:
- dream cron 与普通 cron 共享事件循环，系统任务中的同步文件处理同样会放大凌晨 lag。
- 保留同步 helper 便于单元测试覆盖 JSON 损坏、文件不存在等边界。

Alternatives considered:
- 只 offload `Path.read_text()`：JSON parse 仍可能阻塞 event loop。

### Decision 5: `get_agent()` 使用 per-cache-key inflight task

`MultiAgentManager` 增加 `_agent_start_locks` 或 `_agent_start_tasks`，按 `cache_key` 管理正在启动的 workspace。推荐实现为：

1. 在全局锁内检查 `self.agents`；命中则直接返回。
2. 在全局锁内为当前 `cache_key` 创建或复用一个启动 task/future。
3. 释放全局锁后等待该 task。
4. 启动 task 内部读取配置、创建并启动 workspace。
5. 启动成功后在全局锁内二次检查缓存；若缓存仍为空则写入并返回；若已有实例则停止新实例并返回已有实例。
6. 启动失败时清理 inflight 记录并向所有等待者传播异常。

Rationale:
- 全局锁只保护共享字典，慢启动不阻塞其他 cache key。
- 同一 cache key 并发请求共享同一个启动结果，保留单实例语义。
- 二次检查可以处理 reload/remove 等并发边界。

Alternatives considered:
- per-key `asyncio.Lock`：实现简单，但需要小心锁对象生命周期；inflight task 更容易让并发调用共享同一异常/结果。
- 完全无锁并行启动后 CAS：可能重复启动重资源 workspace，失败清理复杂。

## Risks / Trade-offs

- [Risk] `get_agent()` 是 HIGH 影响面符号，锁粒度调整可能改变异常传播或缓存行为。→ Mitigation: 先补并发回归测试，覆盖同 key 单启动、不同 key 并行、启动失败后可重试、缓存命中不创建 task。
- [Risk] `JsonJobRepository` 缓存可能在极端文件系统时间精度或同尺寸快速替换下误判未变化。→ Mitigation: 使用 `st_mtime_ns + st_size`；所有本进程 `save()` 后主动更新缓存；必要时可扩展为 inode/signature。
- [Risk] offload 到线程池会增加线程池压力。→ Mitigation: 该变更减少 event loop 阻塞但不解决总吞吐；后续全局 cron 队列需要单独限流。测试应关注 event loop 不被阻塞，而不是无限提升吞吐。
- [Risk] async 化 `_load_dream_logs()` 会影响私有调用点。→ Mitigation: GitNexus impact 为 LOW，调用点集中在 `CronManager` 内；同步 helper 保留原边界行为。
- [Risk] repository 缓存返回同一 model 对象可能被调用方意外修改。→ Mitigation: 当前 `CronJobSpec` 以 pydantic 模型传递，若发现调用方会原地改动，应在索引返回前 `model_copy(deep=True)` 或明确只读约束；优先用测试确认现有调用方式。

## Migration Plan

1. 添加回归测试，先覆盖当前阻塞/串行行为的目标语义。
2. 实现 `JsonJobRepository` offload 和快照索引，运行 cron repository 与 cron callback 相关测试。
3. async 化 dream 日志读取与归档维护调用，运行 heartbeat/dream/cron manager 测试。
4. 实现 `MultiAgentManager.get_agent()` per-cache-key inflight，运行 lazy loading、tenant workspace 和 agent router 相关测试。
5. 使用 `detect_changes()` 检查影响范围，确认只触及预期符号和流程。

Rollback:
- repository 改动可回退到每次 `load()`，不涉及数据迁移。
- `get_agent()` 改动可回退到全局锁串行启动，外部 API 无兼容问题。
