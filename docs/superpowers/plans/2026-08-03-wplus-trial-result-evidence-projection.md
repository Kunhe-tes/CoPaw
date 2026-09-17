# W+ SOP 预跑结果与证据投影修复计划

## 问题与边界

`AwaitingTrialFeedback` 已经证明预跑完成事件成功持久化，但当前 Session 快照只投影首个结果列表，丢弃预跑计划步骤、摘要、警告和能力；完成事件也没有更新已确认事实与未知项。因此页面刷新、GET 或 SSE 重连后，主区与右侧证据栏仍为空。

本次只修复持久化事件到 Session API 的投影，不从实时文本、Markdown 或前端内存推导业务状态，也不保存原始客户响应。

## 验收要求

- `trial_execution_completed` 可携带脱敏的累计已确认事实与明确未知项，并更新 Session 投影。
- Session API 从当前 `run_id` 对应的持久化计划和运行事件恢复步骤、摘要、警告、时间与结果表。
- 能力证据来自当前预跑计划实际引用的能力；只有完成且 schema 校验通过才标记为已验证。
- 页面刷新或 SSE 重连后仍显示相同结果与右侧证据。
- 旧事件缺少新增字段时仍可读取，保持向后兼容。

## 实施单元

1. **完成事件契约与投影**
   - 文件：`src/swe/app/wplus_sop/models.py`、`src/swe/app/wplus_sop/service.py`
   - 测试：`tests/unit/app/wplus_sop/test_models.py`、`tests/unit/app/wplus_sop/test_service.py`
   - 场景：完成事件保存事实/未知项；旧载荷默认空列表；重载 store 后字段仍存在。

2. **运行快照序列化**
   - 文件：`src/swe/app/wplus_sop/service.py`
   - 测试：`tests/unit/app/wplus_sop/test_service.py`
   - 场景：计划步骤、进度、完成摘要、警告、时间、结果列行和能力证据全部进入 Session；非当前 run 事件不得污染当前快照。

3. **Agent 完成事件约束**
   - 文件：`src/swe/app/wplus_sop/runtime.py`
   - 测试：`tests/unit/app/wplus_sop/test_runtime.py`
   - 场景：预跑命令明确要求完成事件提交脱敏的累计事实与未知项，禁止原始客户数据。

4. **回归验证**
   - 后端 W+ model/service/runtime/router 单测。
   - 前端 W+ 工作台单测和构建，确认现有 `TrialPanel`、`EvidenceRail` 能直接消费补齐后的 API。
   - Ruff、Prettier、diff check 与 GitNexus `detect_changes`。

## 风险控制

- 新字段仅允许字符串摘要；结果列表继续使用现有递归敏感字段和值校验。
- 能力证据不把目录元数据标签冒充执行证据：未完成或 schema 未通过时不得标记为 verified。
- 新字段使用默认值兼容已落盘的旧 Session。
