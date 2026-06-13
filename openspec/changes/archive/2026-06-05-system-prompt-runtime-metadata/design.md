## Context

当前 `SWEAgent._build_sys_prompt()` 的最终 SystemPrompt 由三层内容拼接而成：

1. `build_system_prompt_from_working_dir()` 读取工作区内的静态 markdown prompt 文件；
2. `build_multimodal_hint()` 注入模型能力提示；
3. runner 侧通过 `build_env_context()` 生成请求级环境上下文，并作为 `env_context` 追加到最终 prompt。

时间信息当前位于第 3 层，只输出 `Current date: YYYY-MM-DD TZ (Day)`。这会丢失小时、分钟、秒，无法稳定支撑依赖“当前时刻”的任务。与此同时，`source_id` 已经在 request、trace、hook、scope 隔离等路径中作为一等身份使用，但 `build_env_context()` 尚未将它暴露给模型，因此模型拿到的 SystemPrompt 仍然缺少 source 维度。

本次变更的约束是：只增强最终 SystemPrompt 中的运行时元信息，不改动 prompt 文件加载顺序，不引入新的 source 解析来源，也不改变现有 source-scoped runtime isolation 规则。

## Goals / Non-Goals

**Goals:**

- 让最终 SystemPrompt 明确包含当前日期、当前时间、时区和星期，粒度至少到秒。
- 让最终 SystemPrompt 明确包含当前请求的 `source_id`。
- 在 `source_id` 缺失时提供稳定、无歧义的占位展示，避免把默认值误当作真实 source。
- 把行为收敛到可回归测试的 helper / prompt 组装层，避免后续 prompt 演进时退化。

**Non-Goals:**

- 不修改 AGENTS.md / SOUL.md / PROFILE.md / MEMORY.md 等静态 prompt 文件内容。
- 不新增或修改 source system config、scope 解析、trace 存储等运行时身份规则。
- 不向 SystemPrompt 继续扩展更多身份字段（如 `bbk_id`、`tenant_name`、组织信息）。
- 不改变 task progress、hook context、multimodal hint 的现有拼接语义。

## Decisions

### 决策 1：运行时元信息继续由 `build_env_context()` 负责输出

`source_id` 和当前时间都属于请求级上下文，不属于工作区静态 prompt 文件，也不属于 agent 固有身份。因此继续放在 runner 构造的 `env_context` 层最合适，只需要扩展 `build_env_context()` 的入参与输出格式，再由现有 `SWEAgent._build_sys_prompt()` 拼接即可。

这样做的原因：

- 维持静态 prompt 和动态上下文分层，避免 `build_system_prompt_from_working_dir()` 开始承担请求态职责。
- 复用现有时区解析和环境上下文格式，变更范围集中。
- 降低对 workspace prompt 测试的影响，重点回归 runner / agent 拼接链路。

备选方案：

- 直接把时间和 `source_id` 写进 `build_system_prompt_from_working_dir()`：会把请求态信息混入静态 prompt builder，不利于复用和测试。
- 在 `_build_sys_prompt()` 里额外手工拼接一段 `[Request Context]`：功能可行，但会形成与 `build_env_context()` 重叠的第二套运行时上下文格式。

### 决策 2：时间字段统一升级为 date-time，而不是额外追加独立时间行

现有 prompt 已经有日期行，用户要求是在原有日期信息上明确到时间。最小改动方式是把这行升级为单一的 date-time 表达，例如 `Current time: 2026-05-21 14:30:45 Asia/Shanghai (Thursday)`，而不是保留日期行再额外添加一行时间。

这样做的原因：

- 避免 prompt 中出现语义重复的日期/时间两行。
- 保持模型只需要读取一个权威时间字段。
- 能与现有 `get_current_time` 工具的时间格式保持接近，减少理解成本。

备选方案：

- 保留 `Current date` 并追加 `Current time`：信息重复，且更容易在后续维护中出现两个字段不一致。
- 输出 ISO 8601 UTC 时间戳：机器友好，但对模型和人工阅读都不如当前的本地时区格式直观。

### 决策 3：`source_id` 缺失时显式输出占位文案，不隐式回退到 `"default"`

虽然部分内部链路会在追踪或兼容逻辑中把缺失 `source_id` 回退为 `"default"`，但 SystemPrompt 里的上下文应表达“当前请求真实提供了什么”，不应伪造一个 source 身份。因此当请求未提供 `source_id` 时，环境上下文应输出明确占位值，例如 `(not provided)`。

这样做的原因：

- 避免模型把兼容性默认值误解为真实业务 source。
- 与 source-scoped 规范中“source identity 应显式传入”的方向一致。
- 让测试可以区分“真实 source=default”和“调用方未提供 source”。

备选方案：

- 始终展示 `"default"`：会混淆真实 source 与缺失 source 两种状态。
- 省略 `Source ID` 行：模型无法判断是“字段不存在”还是“系统忘记注入”。

## Risks / Trade-offs

- [Risk] 现有测试或日志断言依赖 `Current date:` 旧文案。
  Mitigation: 同步更新受影响的单元测试，只收敛到新的统一文案。

- [Risk] 某些非 source-scoped 调用路径没有 `source_id`，新增字段后可能暴露大量 `(not provided)`。
  Mitigation: 这是有意暴露真实上下文，测试中覆盖该场景，避免后续重新退回隐式默认值。

- [Risk] 时间精度提升到秒后，若测试直接断言完整字符串，容易变得脆弱。
  Mitigation: 通过 monkeypatch `datetime.now` / helper 返回值，或只断言格式和关键字段。

## Migration Plan

这是纯 prompt 文本变更，无需数据迁移。

部署步骤：

1. 扩展 `build_env_context()` 的 `source_id` 入参与时间输出格式。
2. 在 runner 调用 `build_env_context()` 时传入当前请求 `source_id`。
3. 为 env context 和最终 SystemPrompt 增加回归测试。

回滚策略：

- 若变更导致 prompt 兼容性问题，可直接回退相关 helper 与测试修改，不涉及状态修复。

## Open Questions

- None.
