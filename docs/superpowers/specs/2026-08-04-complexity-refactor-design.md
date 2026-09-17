# 三处高复杂度函数的分层重构设计

## 目标

在不改变外部行为的前提下，将以下函数的圈复杂度降至 15 或以下：

- `MemoryCompactionHook._apply_checkpoint_budget_stage`
- `run_command_path`
- `ConversationArchiveStore._recover_evidence`

行为兼容包括入口签名、异步产出顺序、消息文本、异常处理、锁范围、epoch 隔离与预算阶段语义。

## 架构方案

保留三个现有入口作为薄编排层，不引入新的公共接口或策略类。每个入口只负责准备共享上下文并路由到职责单一的私有协作函数。

### 上下文预算

将配置有效性和请求上下文解析提取为同步 helper；将治理阶段的水位线去重、异步任务登记及失败清理提取为独立 helper；将 active/emergency 的候选安装、重新测量和降级安装提取为统一 helper。入口仍使用 `decide_context_budget` 的原有阶段判定，返回值规则不变。

### 命令分派

将请求字段和 chat id 解析提取为 context helper。daemon、control、conversation 三条路径分别由异步 helper 处理，保留 daemon > control > conversation 的优先级。各 helper 继续产出 `(Msg, True)`，并保留现有错误消息和日志行为。

### 证据恢复

将引用、关键词、种类和时间范围规范化提取为查询对象或 helper；将单条消息的 epoch、引用、文本、kind 和时间匹配提取为纯函数；将边界遍历与结果上限控制保留在锁内的薄循环中。当前 epoch 检查、legacy epoch-one 兼容和跨 chat 隔离保持不变。

## 测试与验证

先为每条路径的关键行为编写或补充单测，并确认重构前测试能正确捕获目标行为。实现后运行相关单测、全量 Python 单测（若耗时允许）以及项目现有复杂度检查。提交前运行 GitNexus `detect_changes`，确认仅影响预期符号和执行范围。

## 非目标

- 不修改公共 API、数据格式或持久化文件格式。
- 不改变日志级别、错误文本、异步任务生命周期或文件锁策略。
- 不进行与复杂度目标无关的模块移动或命名重构。
