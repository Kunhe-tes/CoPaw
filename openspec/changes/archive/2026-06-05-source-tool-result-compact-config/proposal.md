## Why

工具调用结果过长时，系统会截断返回并把完整结果压缩保存到 toolresult 文件，但相关长度阈值目前只能通过 Agent 运行配置调整。不同 source 接入系统对上下文成本、可读预览长度和 toolresult 文件保留策略的要求不同，需要在当前 source 的 systemconfig 页面中提供统一配置入口。

## What Changes

- 在当前 source 系统配置中新增工具结果压缩配置，支持管理员配置是否启用、近期消息数量、旧结果预览长度、近期结果预览长度和 toolresult 文件保留天数。
- 配置采用 source 级显式覆盖语义：未配置时继续使用现有 Agent runtime `tool_result_compact` 配置，配置后当前 source 下所有请求使用 source 覆盖值。
- 后端提供统一解析 helper，将 source 覆盖与 Agent runtime 配置合成，供工具即时截断和历史 tool result 压缩链路复用。
- Console 的 `system-config-page` 增加工具结果压缩配置卡片，保存时继续保留未知配置键，并对默认值进行裁剪。
- 保存当前 source 配置后刷新 effective config store，确保下一轮请求使用新的截断和压缩阈值。

## Capabilities

### New Capabilities

- `source-tool-result-compact-config`: 当前 source 可配置工具结果截断、压缩和 toolresult 文件保留策略。

### Modified Capabilities

- None.

## Impact

- 后端：
  - 扩展 source system config 注册与校验逻辑，支持布尔与数值型配置项。
  - 新增工具结果压缩配置解析 helper，并接入 `MemoryCompactionHook` 与 `SWEAgent.reply()` 的 `recent_max_bytes` 上下文绑定。
  - 保持现有 Agent Config 作为未配置 source 时的回退来源。
- Console：
  - 扩展 `system-config-page` 的配置注册和渲染能力，新增工具结果压缩配置表单。
  - 增加前端数值校验，避免提交不符合后端约束的长度和保留天数。
- 测试：
  - 新增 source 配置合成、默认值裁剪、运行时接入和页面保存的回归测试。
