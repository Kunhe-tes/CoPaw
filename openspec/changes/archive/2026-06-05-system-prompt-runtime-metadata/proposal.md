## Why

当前运行时会把环境上下文追加到 SystemPrompt，但时间信息只精确到日期，模型在处理“刚刚”“今天稍后”“现在几点”这类请求时缺少可靠的当前时刻基准。同时，`source_id` 已经是运行时隔离和 source 配置解析的核心身份，但 SystemPrompt 不暴露该字段，模型无法直接感知当前请求属于哪个 source。

这两个缺口已经开始影响 prompt 的一致性：一方面时间粒度不足会削弱基于当前时刻的判断，另一方面 source 感知缺失会让模型难以在多 source 运行时准确理解当前上下文。现在补齐这部分运行时元信息，可以在不改变现有业务能力边界的前提下提升 prompt 可用性。

## What Changes

- 把当前追加到 SystemPrompt 的日期信息从“日期”提升为“日期 + 时间 + 时区 + 星期”。
- 在 SystemPrompt 的运行时环境上下文中加入当前 `source_id`，让模型可直接读取当前 source 身份。
- 明确 `source_id` 缺失时的回退展示方式，避免 prompt 出现歧义或隐式伪造 source。
- 为 SystemPrompt 运行时元信息补充回归测试，覆盖时间展示和 `source_id` 展示场景。

## Capabilities

### New Capabilities

- `system-prompt-runtime-metadata`: 规范 SystemPrompt 必须暴露当前运行时时间戳与当前 source 身份。

### Modified Capabilities

- None.

## Impact

- Affected code:
  - `src/swe/app/runner/utils.py`
  - `src/swe/agents/react_agent.py`
  - `src/swe/agents/prompt.py`
  - `tests/unit/app/`
  - `tests/unit/workspace/`
- No external API contract changes are expected.
- No database, migration, or dependency changes are expected.
