# W+ JSONL 记忆策略纠偏实施计划

> 已由 `2026-08-04-wplus-agent-owned-delivery-and-memory.md` 取代。原计划中的
> 服务端 memory store adapter 不再实施；批准后改由独立 Agent 回合调用脚本。

## 问题

当前结论阶段把获批候选追加到 Agent 根目录 `MEMORY.md`。这与
`wplus-sop-miner/references/memory-policy.md` 冲突。W+ 记忆必须按候选类型写入
专用 JSONL，并且必须通过技能内 `scripts/memory_store.py --approved` 的隐私和
去重检查。

## 正确边界

- `common_wplus_knowledge` → `memory/common-wplus-knowledge.jsonl`
- `user_wplus_usage` → `memory/users/{user_scope}/wplus-usage-preferences.jsonl`
- `sop_case` → `memory/cases/sop-cases.jsonl`
- 候选必须包含 `type`、非空对象 `content` 和准确对话 `evidence`。
- `user_scope` 只从调用方结构化元数据取得并持久化；不得从 `user_id`、员工号、姓名、
  邮箱或消息正文推导。缺失时不得生成或写入 `user_wplus_usage`。
- 用户批准只授权该候选调用一次脚本；脚本返回 `appended` 或 `duplicate` 后才标记
  approved。拒绝、跳过或脚本失败不绕过脚本写文件。
- 不再调用通用 Memory Manager，也不修改 Agent 根目录 `MEMORY.md`。

## 实施单元

1. 先修改模型与服务测试，固定候选类型、内容、证据、目标 JSONL、缺失 user scope、
   脚本失败重试和重复写入回执。
2. 新增 W+ memory store adapter：解析有效 Miner 技能目录，以无 shell 子进程调用
   `memory_store.py <target> <candidate> --approved`，限制目标在当前 Agent workspace，
   删除临时候选文件并解析结构化回执。
3. 从 Console `channel_meta.user_scope` 捕获可选匿名范围，经入口提议持久化到 Session；
   不从任何身份字段回填。
4. 删除 `BaseMemoryManager.write_authorized_memory` 及其专用测试。
5. 更新工作台候选展示：类型、完整内容、准确证据、真实 JSONL 目标及脚本回执。
6. 同步运行时最终化契约、CONTEXT、ADR 和工作台规格。

## 验证

- 新测试先在错误实现上失败。
- 后端 W+ 全套、Console 入口、memory adapter 隐私/去重/路径测试。
- 前端 W+ 测试、TypeScript、ESLint、Prettier。
- Ruff、Python 编译、`git diff --check`、GitNexus `detect_changes`。
