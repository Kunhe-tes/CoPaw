## MODIFIED Requirements

### Requirement: 查询级自动重试
系统 SHALL 在 `query_handler` 层面捕获瞬时错误并自动重试 Agent 执行；当重试耗尽且最终失败属于 Console Chat 主对话模型调用失败时，系统 SHALL 将最终失败尝试交给 `model-call-error-detail` 能力生成用户可见失败详情。

#### Scenario: 网络超时后重试成功

- **WHEN** Agent 执行过程中抛出 `asyncio.TimeoutError`
- **AND** 查询重试功能已启用
- **AND** 重试次数未达到上限
- **THEN** 系统等待退避时间后重建 Agent 实例
- **AND** 从持久化的会话状态恢复上下文
- **AND** 重新执行查询并返回成功结果

#### Scenario: 432 Token 限制后重试成功

- **WHEN** Agent 执行过程中抛出 `APIStatusError(status_code=432)`
- **AND** 错误消息包含 "输入Token数已达到每分钟上限"
- **AND** 查询重试功能已启用
- **THEN** 系统识别为可重试错误并执行重试

#### Scenario: 连接中断后重试成功

- **WHEN** Agent 执行过程中抛出 `ConnectionResetError`
- **AND** 查询重试功能已启用
- **THEN** 系统识别为可重试错误并执行重试

#### Scenario: 不可重试错误不重试

- **WHEN** Agent 执行过程中抛出 `ValueError`
- **THEN** 系统直接向上传播异常，不执行重试

#### Scenario: 用户取消不重试

- **WHEN** Agent 执行过程中抛出 `asyncio.CancelledError`
- **THEN** 系统直接向上传播异常，不执行重试

#### Scenario: 重试次数耗尽

- **WHEN** Agent 执行过程中抛出可重试错误
- **AND** 已达到最大重试次数
- **THEN** 系统向上传播最后一次异常

#### Scenario: 模型调用重试耗尽生成原始错误详情

- **WHEN** Console Chat 主对话的模型调用失败经过查询级重试后仍然失败
- **AND** 最终失败符合 `model-call-error-detail` 的模型调用失败范围
- **THEN** 系统使用最后一次失败尝试生成 `model_call_failed` 用户可见失败详情
- **AND** 重试过程中的临时通知不包含在最终原始错误详情中
