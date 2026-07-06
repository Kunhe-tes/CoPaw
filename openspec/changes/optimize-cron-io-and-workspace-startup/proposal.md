## Why

凌晨大量外部调度回调会集中调用 `/api/internal/cron/callback`，当前 cron job 读取、状态文件处理和 workspace 冷启动路径存在事件循环同步阻塞与全局锁串行化风险。该变更先收敛两个高收益点：把 cron 相关同步文件 I/O 移出事件循环，并让不同 agent/workspace 的冷启动互不阻塞。

## What Changes

- 将 `JsonJobRepository.load/save` 的文件读取、JSON 解析、JSON 序列化和原子替换写入移到 worker thread，避免在 event loop 上执行同步磁盘与 CPU 密集 JSON 操作。
- 为 `JsonJobRepository.get_job` 增加 mtime/size 驱动的内存快照索引，常见 callback 查询不再每次完整读取和校验 `jobs.json`。
- 将 dream cron 中的 `dream_logs.json` 同步读取和归档维护调用移出事件循环，避免 dream 系统任务与普通 cron 洪峰互相放大 lag。
- 调整 `MultiAgentManager.get_agent` 的锁粒度：全局锁只保护缓存字典，workspace 启动在 per-cache-key inflight 控制下执行，使不同 tenant/agent 可并行冷启动，同一个 tenant/agent 只启动一次。
- 保持现有 HTTP API、cron job 数据格式和 workspace 缓存语义不变。

## Capabilities

### New Capabilities

- `cron-repository-nonblocking-io`: 约束 cron job 仓库和 dream cron 文件处理不得在事件循环上执行同步文件 I/O 或大 JSON 处理，并要求 job 查询复用有效快照。
- `workspace-startup-concurrency`: 约束 workspace 运行时按 tenant/agent 独立启动，避免单个冷启动阻塞其他 workspace 获取。

### Modified Capabilities

- 无。

## Impact

- Affected code:
  - `src/swe/app/crons/repo/json_repo.py`
  - `src/swe/app/crons/repo/base.py`
  - `src/swe/app/crons/manager.py`
  - `src/swe/app/multi_agent_manager.py`
  - 相关 cron、lazy loading、workspace、dream 任务单元测试
- Runtime behavior:
  - `/api/internal/cron/callback` 在读取 job 定义和 dream 系统任务处理时减少 event loop lag。
  - 多个不同 tenant/agent 首次被 callback 命中时可以并行启动 workspace。
  - 同一个 tenant/agent 并发命中时仍只创建一个 workspace 实例。
- Dependencies:
  - 使用标准库 `asyncio.to_thread`、`stat` 信息和现有 `ThreadPoolExecutor` 配置，不引入新外部依赖。
- Risk:
  - `JsonJobRepository` GitNexus impact 为 LOW。
  - `CronManager._load_dream_logs` GitNexus impact 为 LOW。
  - `MultiAgentManager.get_agent` GitNexus impact 为 HIGH，涉及 Routers、App、Config 多处直接调用；实现必须通过并发回归测试保护缓存语义、异常传播和单实例启动语义。
