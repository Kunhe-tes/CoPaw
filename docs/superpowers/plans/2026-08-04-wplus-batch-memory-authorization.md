# W+ SOP 批量记忆授权与单回合写入计划

## 目标

把当前“逐候选授权、逐候选启动 Agent”的记忆流程改为：用户一次性为每个未决候选选择写入或不写入，统一提交后最多启动一个 Agent 回合写入全部获批候选。启动前必须确认所属 Chat 的上一轮 Agent 已完全释放。

## 已确认语义

- 工作台必须收齐所有未决候选的决定后才能提交。
- 全部拒绝时直接完成，不启动 Agent。
- 至少一个批准时只创建一个 `WritingMemory` run。
- 同一个 Agent 回合按服务端绑定的候选及目标逐项调用 Miner `memory_store.py`，不得处理未批准候选。
- Agent 最后提交一个批量结果事件；成功项记录 appended/duplicate 回执，失败项记录失败原因。
- 批次存在失败时回到 `MemoryReview`，只对失败项重新收集决定并再次批量提交；全部成功或拒绝后完成。
- 前端仅在 `runtime_ready=true` 时允许统一提交；服务端仍在持久化新 run 前调用 `_wait_for_owning_chat_idle()`，超时不得改变授权状态。
- 保留旧单候选字段和事件的读取兼容，避免既有 `.sop/wplus-sop.json` 无法加载；新流程只产生批量协议。

## 实施任务

1. 模型与事件
   - 在 `src/swe/app/wplus_sop/models.py` 增加批量写入结果模型和 active candidate IDs。
   - 为既有单候选持久化状态提供兼容校验，不允许同一批次漏项、重复项或目标漂移。
2. 服务端状态机
   - 在 `src/swe/app/wplus_sop/service.py` 让 `resolve_memory` 接收完整 `decisions` 数组并原子应用。
   - 全拒绝不启动 run；有批准时一次进入 `WritingMemory`，运行 payload 包含全部获批候选。
   - 批量结果事件必须与服务端绑定的候选集合、目标和脚本结果逐项一致。
   - 增加“上一轮仍运行时等待；等待超时不落授权状态”的记忆批次测试。
3. Agent 命令合同
   - 在 `src/swe/app/wplus_sop/runtime.py` 将 WritingMemory 合同改为批量候选、单回合、单个批量终态事件。
   - 更新事件顺序测试和 `skills/wplus-sop-miner` 的记忆授权说明。
4. 工作台
   - 在 `console/src/pages/WPlusSopWorkspace/index.tsx` 增加按候选保存的决策草稿和统一提交按钮。
   - 未选完、请求中、`runtime_ready=false` 或 WritingMemory 时禁止提交。
   - 显示批量写入中、逐项成功回执和逐项失败状态。
5. 文档
   - 更新 `CONTEXT.md` 和 ADR-0013，把单候选独立 run 改为批量授权、单 Agent run。
6. 验证
   - 后端模型、服务、runtime、store/router 相关测试。
   - 前端工作台测试与 TypeScript 检查。
   - Miner 技能合同测试、格式检查、GitNexus `detect_changes()`。

## TDD 验收场景

- 两个候选分别批准/拒绝，一次命令只启动一个 run，payload 只含批准项。
- 两个候选均批准，一次 run 绑定两个候选，单个批量事件生成两份回执。
- 所有候选拒绝时直接完成且不调用 Agent。
- 少一个决定、重复 candidate、未知 candidate 或篡改目标时原子拒绝且不修改 Session。
- 上一轮 Agent 未完成时等待；变为 idle 后只启动一次。
- 等待超时不把候选改为 writing，也不创建新的 run。
- 批量部分失败时成功项保持 approved，失败项可再次批量决策。
- 页面未选完或 runtime 未 ready 时统一提交按钮不可用。
