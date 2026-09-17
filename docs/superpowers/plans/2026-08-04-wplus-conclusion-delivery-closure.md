# W+ SOP 结论交付闭环实施计划

> 2026-08-04 纠偏：本文原先设计的 Agent 根目录 `MEMORY.md` 写入已废止。W+ 记忆必须
> 使用 Miner 的 `scripts/memory_store.py --approved` 写入分层 JSONL。当前计划见
> `2026-08-04-wplus-jsonl-memory-policy-correction.md`。

## 目标与产品边界

把最终结果生成后的流程改成可恢复、可审计的交付闭环：结果持久化后先进入
`OutputReview`，工作台立即提供 Markdown/HTML 安全预览和三种结果文件下载；用户明确
确认结果后才进入记忆处理。记忆候选展示完整脱敏内容、Agent 范围和目标 `MEMORY.md`；
批准动作通过 Workspace 的 Memory Manager 幂等写入，持久化写入回执。所有候选被批准、
拒绝或跳过后才进入 `Completed`。

本次不自动调用 `wplus-skill-builder`，不允许前端直接写文件，也不把未确认的结果或记忆
候选当作完成。

## 状态与一致性

```text
FinalizingOutputs
  -> OutputReview (sop_result + memory_candidates 已持久化)
  -> MemoryReview (用户确认结果且存在候选)
  -> Completed (所有候选已解决)

OutputReview -> Completed (用户确认结果且候选为空)
MemoryReview -> MemoryReview (待处理或写入失败仍存在)
```

- `confirm_outputs` 使用 `command_request_id`、预期状态版本和现有 Store receipt 保证会话命令
  幂等。
- 每个批准候选使用稳定的 `memory_id = wplus-sop/<session>/<candidate>`。Memory Manager
  在 `MEMORY.md` 中写入不可见标记，重试先查标记再追加，覆盖“文件已写入但 Session
  commit 未完成”的双写窗口。
- 写入成功后候选保存 `memory_id`、目标文件、写入时间和是否复用既有写入；失败保存
  `failure_reason`，保持 `MemoryReview` 并允许再次批准重试。
- 拒绝与跳过只写审计状态，不触碰 Memory Manager。

## 实施单元

1. **领域模型与状态机**
   - 文件：`src/swe/app/wplus_sop/models.py`
   - 测试：`tests/unit/app/wplus_sop/test_models.py`
   - 增加 `OutputReview`、记忆目标与写入回执；候选值继续接受 JSON，但拒绝联系方式和
     原始响应类字段。

2. **Memory Manager 幂等写入**
   - 文件：`src/swe/agents/memory/base_memory_manager.py`
   - 测试：`tests/unit/agents/test_authorized_memory_write.py`
   - 原子更新 Workspace 根目录 `MEMORY.md`，返回稳定回执；相同 `memory_id` 重试不重复
     追加。

3. **服务端结果确认与记忆写入**
   - 文件：`src/swe/app/wplus_sop/service.py`
   - 测试：`tests/unit/app/wplus_sop/test_service.py`
   - `memory_candidates` 终态事件进入 `OutputReview`；新增 `confirm_outputs`；批准候选调用
     Memory Manager，成功/失败结果进入持久化候选状态；Session API 投影预览、完整候选
     和回执。

4. **前端交付体验**
   - 文件：`console/src/api/types/wplusSop.ts`、
     `console/src/pages/WPlusSopWorkspace/index.tsx`、`index.module.less`
   - 测试：`console/src/pages/WPlusSopWorkspace/index.test.tsx`、`sessionView.test.ts`
   - `OutputReview` 提供 Markdown 文本预览、sandbox HTML iframe、下载和结果确认；
     `MemoryReview` 展示完整候选内容、范围、目标、失败重试和成功回执。

5. **持久契约文档**
   - 文件：`CONTEXT.md`、`docs/adr/0013-...md`、工作台设计规格。
   - 固化“结果生成不等于完成”“批准等于真实写入成功授权”及双写幂等边界。

## 验收与验证

- 先运行新增测试并确认因缺少状态/方法/UI 而失败，再做最小实现。
- 后端：W+ models/service/router/runtime/store 全套测试，Memory Manager 定向测试。
- 前端：W+ 页面与 API 测试、TypeScript、ESLint。
- 安全：HTML 只进入 sandbox iframe，不使用 `dangerouslySetInnerHTML`；候选值通过现有敏感
  值检测；所有读取、下载和写入继续复用 Session ownership。
- 完成前运行 `git diff --check` 和 GitNexus `detect_changes`；不提交代码。
