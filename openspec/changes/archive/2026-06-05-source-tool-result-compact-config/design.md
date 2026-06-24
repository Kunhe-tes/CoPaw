## Context

当前工具结果长度控制分布在两条链路：

- `read_file` 等工具即时返回时，通过 `current_recent_max_bytes` 控制返回给模型的预览长度。
- 记忆压缩 hook 在历史消息进入上下文检查前读取 `agent_config.running.tool_result_compact`，并委托 ReMeLight 将过长 tool result 压缩为短预览，同时把完整结果保存到 toolresult 文件。

这些配置目前属于 Agent runtime 配置，适合单租户或单 Agent 调整，但不适合按 source 接入系统统一治理。现有 `source-system-config` 已经提供 current-source raw config API、effective config、默认值合并、默认值裁剪和 Console 页面权限保护，因此本变更应复用该基础设施。

## Goals / Non-Goals

**Goals:**

- 在 `system-config-page` 中为当前 source 提供工具结果压缩配置入口。
- 支持配置 `enabled`、`recent_n`、`old_max_bytes`、`recent_max_bytes`、`retention_days`。
- 保持 source 显式覆盖语义：没有 source 配置时继续使用现有 Agent runtime 配置。
- 让工具即时截断和历史 tool result 压缩使用同一份合成配置。
- 保存时保留未知 source 配置键，并裁剪与默认基线一致的显式覆盖。

**Non-Goals:**

- 不迁移或删除现有 Agent Config 中的 `tool_result_compact` 配置。
- 不改变 ReMeLight 的 toolresult 文件写入格式、文件路径或清理实现。
- 不新增跨 source 管理页面，本次仍只操作当前请求 source。
- 不把 systemconfig 页面变成任意 JSON 编辑器。
- 不动态改变工具注册表或模型工具列表。

## Decisions

### 决策 1：source 配置作为显式覆盖，而不是替代 Agent Config

新增 source 配置路径：

```json
{
  "tool_result_compact": {
    "enabled": true,
    "recent_n": 2,
    "old_max_bytes": 3000,
    "recent_max_bytes": 50000,
    "retention_days": 5
  }
}
```

运行时合成规则：

```text
Agent runtime tool_result_compact
  < source raw config.tool_result_compact（仅已显式配置字段）
```

理由：

- 现有部署已经可能依赖 Agent Config 中的阈值，不能让默认 source config 无条件覆盖它。
- source 配置表达“系统接入方统一策略”，只有管理员显式保存后才应影响该 source。
- 未配置 source 时保持现有行为，降低上线风险。

备选方案：

- 把 `tool_result_compact` 加入 source 默认 effective config，并始终覆盖 Agent Config。实现更简单，但会让既有 Agent Config 页面配置突然失效。
- 只配置 `recent_max_bytes`。改动更小，但无法覆盖真正写入 toolresult 文件的历史压缩链路，也不能配置保留天数。

### 决策 2：新增 typed registry，而不是继续只支持 boolean switch

后端当前 `SourceSystemConfigSwitch` 偏向布尔开关。工具结果压缩包含多个 int 字段和一个 bool 字段，需要扩展为可注册的 typed setting，或新增独立注册结构。

建议最小结构：

```python
SourceSystemConfigSetting(
    key="tool_result_compact.recent_max_bytes",
    path=("tool_result_compact", "recent_max_bytes"),
    default_value=50000,
    value_type="int",
    ge=1000,
)
```

理由：

- 校验、默认值构造、默认值裁剪和前端渲染都需要字段元数据。
- 后续 source system config 继续新增数值或字符串配置时，可以复用同一模式。

备选方案：

- 对 `tool_result_compact` 写专用校验逻辑。短期更快，但会让注册表继续只支持布尔开关，后续每个配置都要重复实现。

### 决策 3：提供统一解析 helper，避免运行时散读 JSON

新增 helper 负责把 source 覆盖合成到 Agent runtime 配置：

```python
resolve_tool_result_compact_config(
    base_config: ToolResultCompactConfig,
    source_config: Any | None,
) -> ToolResultCompactConfig
```

接入点：

- `MemoryCompactionHook.__call__()`：用合成配置决定是否调用 `compact_tool_result`，以及传入 `recent_n/old_max_bytes/recent_max_bytes/retention_days`。
- `SWEAgent.reply()`：用合成配置的 `recent_max_bytes` 设置 `current_recent_max_bytes`，影响 `read_file` 即时截断长度。
- `summary_memory()` 和 `dream_memory()` 若继续为总结工具设置 `recent_max_bytes`，也应使用同一 helper，避免总结链路和对话链路不一致。

理由：

- 一个 helper 可以集中处理脏数据、缺失字段、默认值和类型转换。
- 运行时接入点只关心最终配置，不需要理解 source system config 的结构。

### 决策 4：前端用专用配置卡片展示，不混入布尔开关列表

`system-config-page` 当前只有“受控功能开关”卡片。工具结果压缩配置应单独展示为“工具结果压缩配置”卡片，字段形态参考 Agent Config 中已有 `ToolResultCompactCard`：

- `enabled`：Switch
- `recent_n`：Slider 或 InputNumber，范围 1-10
- `old_max_bytes`：InputNumber，最小 100
- `recent_max_bytes`：InputNumber，最小 1000，并要求大于等于 `old_max_bytes`
- `retention_days`：Slider 或 InputNumber，范围 1-10

理由：

- 这组字段是策略配置，不是简单功能开关。
- 单独卡片可以放清楚“未保存时继承 Agent Config，保存后覆盖当前 source”的说明，降低误操作。

### 决策 5：保存继续走 current-source raw config 并保留未知键

页面保存流程沿用现有模式：

```text
GET /api/source-system-config/current
  -> 修改 draftConfig.tool_result_compact
  -> PUT /api/source-system-config/current
  -> loadEffectiveConfig(activeSourceId)
```

保存时必须：

- 只修改注册字段，不覆盖未知键。
- 与默认基线一致的显式字段可被裁剪。
- 裁剪后为空对象时删除 current source 配置记录。

这里的“默认基线”用于裁剪 source 配置，不等于运行时 Agent Config 回退值。运行时未配置 source 时仍以 Agent Config 为准。

## Risks / Trade-offs

- [Risk] 用户可能误以为删除 source 配置会恢复为系统内置默认值，而实际会回退到 Agent Config。Mitigation: 页面文案明确“未保存时继承 Agent 配置”。
- [Risk] `recent_max_bytes` 同时影响工具即时返回和近期历史压缩，配置过大可能增加上下文压力。Mitigation: 前端和后端保留最小值校验，并在说明中标注成本影响。
- [Risk] source config 的默认值裁剪基线和 Agent Config 运行时回退基线不同，语义容易混淆。Mitigation: helper 和测试明确区分“存储裁剪默认值”和“运行时回退配置”。
- [Risk] 多实例环境中 source 配置不是瞬时全局生效。Mitigation: 沿用 source system config 短 TTL + version 探测策略，并定义为下一轮请求生效。

## Migration Plan

1. 扩展 source system config registry，支持 typed setting 注册、默认值生成、规范化和裁剪。
2. 注册 `tool_result_compact` 五个字段，并补充模型校验测试。
3. 新增 `resolve_tool_result_compact_config()` helper 及单元测试。
4. 将 `MemoryCompactionHook`、`SWEAgent.reply()`、`summary_memory()` 和 `dream_memory()` 的读取点切换到 helper。
5. 扩展 `system-config-page` 注册与 UI，新增工具结果压缩配置卡片和保存测试。
6. 运行相关 Python 与 Console 测试。

Rollback:

- 删除 current source 中的 `tool_result_compact` 配置即可恢复当前 source 使用 Agent Config。
- 如需代码回滚，可移除页面卡片和 helper 接入点，保留数据库中的未知键不会影响旧代码。

## Open Questions

- 页面是否需要显示当前 Agent Config 的继承值，还是只提示“未保存时继承 Agent 配置”。实现复杂度上，首版建议只提示继承语义，不拉取 Agent Config 做对比展示。
