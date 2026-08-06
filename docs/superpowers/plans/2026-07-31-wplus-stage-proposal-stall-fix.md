# W+ SOP 环节提案卡住修复计划

## 目标

修复 W+ SOP 会话长期停留在 `GeneratingStageProposal`、页面只显示
“正在生成环节”的问题。

## 已确认原因

1. 后台 Miner 的普通流式输出由内部订阅器消费，工作台只接受持久化的
   `Structured Interaction Envelope`；只输出 Markdown 不会推进状态。
2. Miner 的状态文档使用 `stage_queue[].id`，而 `stage_proposal` 事件实际
   要求 `stages[].stage_id`。当前后台命令没有携带精确事件契约，Agent
   无法稳定构造首个结构化事件。
3. `Generating*` 状态已持久化，但 Agent 任务只存在于内存 `TaskTracker`。
   进程重启或任务丢失后，没有机制把孤儿运行转为 `RecoverableFailure`。

## 边界

- 保持 ADR 0013 的状态机和“持久化 Session 是唯一事实来源”不变。
- 不解析 Markdown，不让前端推断环节队列。
- 不放宽 Session ownership、状态版本或运行身份校验。
- 本次只修首轮环节提案契约和孤儿运行恢复。

## 任务

### 1. 先写失败测试

- `tests/unit/app/wplus_sop/test_runtime.py`
  - `propose_stage_queue` 命令必须携带 `stage_proposal` 的精确最小 payload
    示例，字段为 `stage_id`、`name`、`description`、`status`。
  - 命令必须明确禁止只返回 Markdown。
- `tests/unit/app/wplus_sop/test_service.py`
  - 持久化生成态已超过宽限期且 `TaskTracker` 为 idle 时，必须原子转为
    `RecoverableFailure`，并保存原生成态作为重试目标。
  - 活跃任务和宽限期内的新任务不得误判。
- 对应路由测试证明 GET/SSE 读取会触发安全恢复。

### 2. 实现最小修复

- 在 `src/swe/app/wplus_sop/runtime.py` 为 `propose_stage_queue` 注入精确、
  可机器执行的事件契约。
- 在 Miner 的 `SKILL.md` 与 `references/demand-routing.md` 中区分普通 Chat
  Markdown 展示和 CoPaw 工作台 `stage_proposal` 提交。
- 在 `WPlusSopService` 增加孤儿生成运行检查；只在任务已 idle 且超过宽限期
  时转为可恢复失败。
- 在 Session GET 和 SSE 循环中调用该检查。

### 3. 验证

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/unit/app/wplus_sop/test_runtime.py tests/unit/app/wplus_sop/test_service.py tests/unit/app/wplus_sop/test_router.py -q
& .\.venv\Scripts\python.exe -m pytest tests/unit/app/wplus_sop tests/unit/agents/tools/test_emit_wplus_sop_event.py tests/unit/routers/test_console_wplus_sop_entry.py -q
git diff --check
node .gitnexus/run.cjs detect-changes -s all -r CoPaw
```

## 验收标准

- 新会话首轮 Agent 获得无歧义的 `stage_proposal` payload 契约。
- 合法事件把状态推进到 `AwaitingQueueConfirmation`。
- 后端重启或内存任务丢失后，页面不会永久停留在生成态，而会显示可重试失败。
- 正常运行中的后台任务不会被误判或重复启动。

## 审查加固

- 重试目标和失败 run 谱系只从持久化 Session 推导，不信任客户端参数。
- 任务注册与孤儿恢复使用按 Chat 隔离的生命周期锁；阻塞式 Store I/O
  在线程中执行，不占用全局 TaskTracker 锁。
- 恢复事件、投影变化和 run 终态在一次 Store 保存中提交。
- `PendingExit` 中丢失的任务按暂停或终止语义收敛。
- 服务端拒绝首轮非 `pending` 的环节状态。
