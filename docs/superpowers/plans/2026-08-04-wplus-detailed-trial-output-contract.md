# W+ SOP 详细预跑输出契约 P0 计划

## 问题与边界

当前预跑运行时只要求 `trial_execution_completed` 提交脱敏摘要、事实、未知项、
计数、schema 校验和警告，没有明确什么是“足够详细”的结果。Agent 因此可能只复述
前序环节和目标，未给出实际发现、建议动作或可核验明细。

本次 P0 只增强新预跑与预跑重试的 Agent 命令契约，不改变状态机、事件 schema、
持久化模型或前端布局。历史预跑结果不会自动补写。

## 验收要求

- 完成摘要必须包含执行范围、实际关键发现、可执行建议和证据限制，不能只复述环节名、
  输入或目标。
- 存在可枚举业务对象或分组时，必须通过 `result_lists` 给出脱敏明细；每行包含对象分组、
  关键发现、建议动作、判断依据和影响数量等适用字段。
- 每个结果列表必须提供可读列名，并正确填写 `total_count` 与 `truncated`。
- 部分数据、降级、schema 偏差进入 `warnings`；仍未确认的业务信息进入 `unknowns`；
  已由本轮证据确认的事实进入 `confirmed_facts`。
- 不得为了满足详细度编造结果；无法取得证据时应提交失败事件，或明确记录警告与未知项。
- 继续遵守现有脱敏约束，不持久化原始客户响应、账号值、联系方式或自由文本备注。

## 实施与验证

1. 在 `tests/unit/app/wplus_sop/test_runtime.py` 添加契约回归测试，先验证失败。
2. 在 `src/swe/app/wplus_sop/runtime.py::_build_trial_command_contract` 增加详细度要求和
   合法的 `trial_execution_completed` 示例。
3. 运行 runtime 定向测试、W+ 后端测试集、Ruff/编译检查和 `git diff --check`。
4. 使用 GitNexus `detect_changes` 核对最终影响范围；不提交代码。

