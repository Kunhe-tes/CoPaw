# W+ Agent 执行最终交付与记忆写入实施计划

## 已确认边界

- 平台只拥有 Session 状态、可信 run/attempt 身份、结果确认、逐候选批准、幂等和审计。
- 最终产物由绑定原 Chat 的 Agent 回合生成；平台不在下载路由中临时拼接文件。
- Agent 使用 Miner 脚本校验和渲染，通过 `copy_file_to_static` 逐个交付四个文件；
  `sop_result` 只提交工具返回的静态文件元数据、预览内容和校验证据。
- 记忆候选仍由最终化 Agent 提交，但写入发生在用户逐项批准后的独立 Agent 回合。
- 获批记忆回合只允许针对服务端绑定的候选调用
  `scripts/memory_store.py ... --approved`；平台不直接执行脚本，也不把批准权交给模型。
- 技能包审查在代码完成后进行，只输出问题和建议，不修改 `skills/wplus-sop-miner`。

## TDD 实施单元

1. **产物事件契约**
   - 修改 `tests/unit/app/wplus_sop/test_models.py`、`test_service.py`、`test_runtime.py`。
   - 固定四个产物、静态路径、校验证据和 `example_result.html` 必需性。
   - 删除“平台合成下载内容”和布尔值自证校验的预期。

2. **Agent 最终化回合**
   - 修改 `src/swe/app/wplus_sop/models.py`、`runtime.py`、`service.py`、`router.py`。
   - 提示 Agent 生成文件、执行 Miner 脚本、调用 `copy_file_to_static`，再提交
     `sop_result` 与 `memory_candidates`。
   - Session API 返回真实静态产物元数据；W+ 下载端点只做已持久化路径重定向或删除。

3. **批准后记忆 Agent 回合**
   - 修改服务命令和运行时契约，使 `resolve_memory(approve)` 先创建可信运行并进入
     `WritingMemory`，而不是在请求线程写文件。
   - Agent 使用受约束 shell 调用 Miner `memory_store.py --approved`，随后提交
     `memory_write_completed` 或 `memory_write_failed`。
   - 服务端验证事件属于当前批准候选、目标类型/路径匹配、回执只能是
     `appended|duplicate`，再更新审计状态。

4. **工作台**
   - 更新 API 类型和结果/记忆状态展示；写入中禁用重复审批，失败后允许重试。
   - 四个真实产物均可预览或打开，缺失产物不得显示“已交付”。

5. **文档与验证**
   - 同步 ADR、规格和上下文术语。
   - 后端 W+ 全套、Console 入口、前端 Vitest、TypeScript、lint/format、
     `git diff --check`、GitNexus `detect_changes`。

## 安全验收

- 用户批准前不能启动记忆写入回合。
- Agent 不能伪造批准候选、目标路径、写入结果或跨候选复用 event key。
- 缺少匿名 `user_scope` 时不能提出或写入 `user_wplus_usage`。
- `memory/**` 的直接写入不得成为正式成功路径；只有批准回合中脚本的结构化回执
  能推进状态。
- 产物必须来自 `copy_file_to_static` 的返回路径，不能由模型手写静态地址。
