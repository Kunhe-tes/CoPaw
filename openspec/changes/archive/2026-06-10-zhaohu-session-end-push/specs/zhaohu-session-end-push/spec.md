## ADDED Requirements

### Requirement: 招乎渠道配置支持会话结束推送开关
`ZhaohuConfig` SHALL 包含 `session_end_push_enabled` 布尔字段，默认值为 `False`。

#### Scenario: 默认关闭
- **WHEN** 新建招乎渠道配置且未设置 `session_end_push_enabled`
- **THEN** 该字段值为 `False`，不触发会话结束推送

#### Scenario: 手动开启
- **WHEN** 管理员在招乎渠道配置页将"会话结束推送"开关设为开启
- **THEN** 配置保存后 `session_end_push_enabled` 值为 `True`

### Requirement: 前端招乎渠道配置页显示推送开关
招乎渠道配置表单 SHALL 显示"会话结束推送"开关组件，绑定 `session_end_push_enabled` 字段。

#### Scenario: 开关组件渲染
- **WHEN** 用户打开招乎渠道配置抽屉
- **THEN** 表单中显示"会话结束推送"Switch 组件，位于已有表单项之后

#### Scenario: 开关状态回显
- **WHEN** 已保存的招乎配置中 `session_end_push_enabled` 为 `True`
- **THEN** 开关组件显示为开启状态

### Requirement: 推送开关支持分发
`session_end_push_enabled` SHALL 包含在招乎渠道的分发字段列表中，与其他配置字段一同分发到目标租户。

#### Scenario: 分发包含推送开关
- **WHEN** 管理员对招乎渠道执行分发操作
- **THEN** `session_end_push_enabled` 字段值随 `robot_open_id`、`client_id`、`client_secret` 一起分发到目标租户

### Requirement: 会话结束时触发推送
当 `session_end_push_enabled` 为 `True` 时，`ZhaohuChannel` SHALL 在会话完成后自动调用招乎 API 推送结果通知。

#### Scenario: 开关开启时推送
- **WHEN** 会话完成且 `session_end_push_enabled` 为 `True`
- **THEN** 系统调用 `send()` 方法推送包含会话结果的通知

#### Scenario: 开关关闭时不推送
- **WHEN** 会话完成且 `session_end_push_enabled` 为 `False`
- **THEN** 系统不触发推送

#### Scenario: 推送失败不影响会话结果
- **WHEN** 会话完成且推送开关开启，但推送 API 调用失败
- **THEN** 异常被捕获并记录日志，会话结果不受影响
