# NAS 会话事务完整性设计

**状态：** 已确认
**日期：** 2026-08-25

## 1. 目标与范围

修复 task session 中手动提问后，user 与 assistant 历史被整段重复写入的问题；同时修复
删除 `sessions/*.json` 后，进程内存又将旧内容写回的问题，以及同一份历史多次读取时展示
消息 ID 不稳定的问题。

本阶段继续以 NAS 上的 JSON session 文件作为持久化真源，以 NAS 支持的跨 Pod POSIX
`flock` 作为唯一互斥机制。

本阶段不包含：

- Redis 锁、MySQL 会话事件表或任何其他会话存储迁移；
- Chat 删除、archive 删除或历史数据自动清理；
- 新增运行日志、指标或埋点；
- 对模型调用、工具调用等外部副作用提供 exactly-once 保证。

## 2. 已确认的问题根因

1. ReMe manager 以 `chat_id` 缓存并直接复用可变 `memory.content`。session 文件不存在时，
   加载路径只是跳过，未清空这份内存；下一次普通请求会重新将旧内容写入 JSON。
2. cron 请求标记 `skip_history=True`，不加载持久化历史，却可能得到上述共享的完整 memory。
   保存路径将 persisted content 与 current full memory 直接拼接，必然重复历史前缀。
3. 历史读取将原始 `Msg` 转为新的 `ChatMessage` 时重新生成外层 ID；前端按这个不稳定 ID
   不能可靠 reconcile 同一条持久化消息。
4. 当前文件锁只保护单次 read/modify/write，未覆盖“加载状态 -> 运行 Agent -> 提交状态”全过程。
   两个 Pod 仍可基于同一个旧快照并发运行。

## 3. 方案选择

采用“请求级 memory lease + NAS 文件执行事务 + cron 增量补丁”的方案。

```text
普通请求 / cron execution
  -> 获取 sessions/.<user>_<session>.json.lock 的 LOCK_EX
  -> 读取一次 JSON snapshot(revision)
  -> 创建本请求独占的 ReMe memory
  -> 运行 Agent 与同请求 retry
  -> regular replace 或 cron append 的单次提交
  -> 释放 LOCK_EX
```

对同一 session，锁从 Agent 运行开始持有到 session JSON 提交完成。不同 session 不互相阻塞。

### 3.1 NAS 前提

所有 Pod 必须挂载同一个 NAS 文件系统和同一绝对路径；该 NAS 必须在跨客户端场景支持
POSIX advisory `flock`。生产切换前必须用实际 StorageClass 做两 Pod 争抢同一个 lock 文件、
Pod 崩溃释放、并发连续写入和原子替换可见性的验证。

若验证失败，应用必须拒绝写 session，不能降级为无锁写入；此时该阶段方案不成立。

## 4. 持久化模型

session 文件保留既有顶层字段，并增加兼容字段：

```json
{
  "schema_version": 2,
  "revision": 17,
  "agent": { "memory": { "content": [] } },
  "task_runs": []
}
```

- 缺少 `schema_version` 视为 `1`；缺少 `revision` 视为 `0`。
- 每个成功的 session commit 将 revision 加一。
- 旧 reader 应忽略根级未知字段，故不需要数据迁移。
- JSON 继续通过同目录临时文件、文件 `fsync`、`os.replace` 写入；替换后同步父目录。
- lock 文件与会被替换的数据文件分离，锁文件始终是 `.session.json.lock`。

`sessions/*.json` 是本阶段的当前对话真源；`dialog/<chat_id>/` 仍是 checkpoint/archive evidence。
手动删除 session JSON 后，新请求不会恢复旧 memory，但 archive 中的旧证据仍按既有归档策略保留。

## 5. SessionExecution 事务

`SafeJSONSession` 新增异步上下文管理器 `execution()`，产出 `SessionExecution`。它打开一次
`AsyncSessionFileLock`，维护内存中的 state snapshot，并提供不再取锁的读写方法：

```python
async with session.execution(session_id, user_id, timeout_seconds) as tx:
    state = await tx.read_state()
    await tx.commit_regular(agent_state, hook_overlay)
```

事务内禁止调用会再次取锁的 `load_session_state()`、`save_session_state()`、
`mutate_session_state()`。所有同请求 session 更新都修改 `tx.state`，仅由最终 commit 写文件。

请求入口必须先建立 `execution()`，再派生同请求的 Agent、retry 或 cleanup 子任务，并显式传递
同一个 `SessionExecution`。会话层会拒绝当前任务上下文中对短锁 API 的重入；对于事务建立前就
创建且没有可观察父子关系的 asyncio task，运行时无法可靠地区分它与独立请求，因此不得让该类任务
调用短锁 API。Task 2 通过请求级 transaction 传递落实这项约束，独立请求仍按文件锁正常排队。

锁策略：

| 调用方 | 获取锁等待 | 锁忙行为 |
| --- | --- | --- |
| 手动对话 | 5 秒 | 拒绝本次请求，不创建 Agent |
| cron | `min(30 秒, job timeout / 3)` | 以原 execution key 作为可重试执行退出 |
| cron 清理 | 既有 5 秒 | 跳过本轮 |

## 6. 请求级 memory lease

`ReMeLightMemoryManager` 不再按 `chat_id` 返回缓存的可变会话 memory。它提供每次调用均新建的
request memory；该 memory 绑定当前 Chat archive，但其 `content`、compressed summary、动态
method wrapper 均只属于当前请求。

普通请求从 `tx.state["agent"]` 恢复此 memory。cron 读取同一 snapshot 作为提交基线，但不将
基线 memory 放入模型上下文。

重试仅在本请求内用上一次 Agent 的 state snapshot 恢复新 Agent，不落盘、不取共享 memory。

memory compaction、`/clear`、`/new` 与 `/compact` 必须直接操作当前 Agent memory。manager 的
archive/evidence 操作可以访问 Chat archive store，但不得通过 `chat_id` 找回另一个请求的在线 memory。

## 7. regular 与 cron 提交

`SessionExecution` 提供两个唯一的业务提交入口。

### 7.1 普通会话

`commit_regular()`：

1. 保留受 session 管理的 snapshot 字段；
2. 替换 `agent` 为本次 Agent 的完整 state；
3. 应用既有内部 follow-up 剔除与 external approval 去重；
4. 写入或移除 hook overlay；
5. revision 加一并原子提交。

模型失败信息、skill snapshot、command dispatch 状态也必须加入当前 `tx.state`，不能在请求运行中
独立调用 `mutate_session_state()`。

### 7.2 cron

cron request 带稳定的：

```text
execution_key = <job-id>:<scheduled-fire-time-or-external-execution-id>:<target-session-id>
```

`scheduled-fire-time` 不能用 worker 本地 `now()` 生成。task run 保留用于 UI 的随机 `run_id`，并新增
只用于幂等判断的 `execution_key`：

```json
{
  "run_id": "task-run-uuid",
  "execution_key": "job-42:2026-08-25T09:00:00Z:task-session-7",
  "memory_start": 12,
  "memory_end": 16
}
```

`commit_cron_append()`：

1. 从 request memory 取得本次新增 content，剔除内部 follow-up；
2. 若 persisted `task_runs` 已有相同 execution key，直接幂等成功；
3. 否则将 delta append 到基线 memory，创建对应 `task_run`，并只更新允许的 hook overlay；
4. revision 加一并原子提交。

必须删除全量 `existing_memory + current_memory` 合并语义。cron 不得用 fresh Agent state 覆盖普通会话
写入的非 cron 字段。

## 8. 历史 ID 与前端

历史 API 的 `ChatMessage.id` 必须等于原始 `Msg.id`，同时保留 `metadata.original_id`。只有没有原始
ID 的遗留 entry 才生成确定性 `legacy:<sha256(session_id, position, timestamp, role, content)>` ID。

Console 的历史加载按此稳定 ID 替换或去重卡片；流式期间的临时卡片可使用本地 ID，但持久化历史到达后
必须收敛到服务端 ID。

## 9. 失败、读写和发布语义

- session history 读取不等待长执行锁；原子替换保证读取到前一次或后一次完整 snapshot。稳定 ID 使
  前端能够从旧 snapshot 收敛到新 snapshot。
- 流式回复结束但 commit 失败时，向当前请求给出“未持久化”终态；不自动重跑模型。
- NAS 提交结果不确定时，重新读取 JSON。cron 通过 execution key 确认是否已提交；普通请求只确认
  revision，不能自动重跑模型。
- 新旧版本不能混跑：旧版本会在执行后按旧逻辑写回。发布必须暂停 cron、排空旧请求、缩容旧 Pod 至零，
  再启动新版本。
- 已有重复数据不自动去重；本阶段只停止新重复。存量修复只能在未来用离线预览工具单独处理。

## 10. 验收标准

1. 两 Pod 对同一 NAS lock 文件竞争时，仅一方进入临界区；锁持有 Pod 退出后另一方可获得锁。
2. 删除 session JSON 后的下一次普通对话只保存新 turn，不恢复旧 memory content。
3. 基线 `A,B` 的 task session 运行生成 `C,D` 后，结果严格为 `A,B,C,D`。
4. 相同 cron execution key 提交两次，结果只有一份 `C,D` 和一个 task run。
5. 手动对话与 cron 并发时，只有持锁者启动 Agent。
6. retry 不产生中间 JSON 写入，最终只提交一次。
7. `/clear`、`/new` 与 memory compaction 操作当前 request memory。
8. 同一 JSON 连续读取两次，返回消息 ID 完全一致。
