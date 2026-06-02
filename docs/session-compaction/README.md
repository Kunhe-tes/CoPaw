# 会话压缩与输出截断说明

本文档面向 Swe 的普通使用者和配置维护者，说明项目里几类“压缩”和“截断”分别在什么时候生效、会影响什么结果、应该如何配置，以及遇到大输出时怎么判断该调哪一组参数。

本文只讲使用语义和配置规则，不展开源码和内部实现。

## 一句话理解

Swe 会同时处理两类问题：

1. 单次工具输出太大，当前轮次不适合把全文都直接放进对话。
2. 整段会话越积越长，后续请求接近模型上下文上限。

因此，项目里会同时用到三组能力：

| 能力 | 作用对象 | 典型场景 |
|------|----------|----------|
| Historical Tool Result Compaction | 历史工具结果 | 旧的工具输出太长，需要缩短后再继续保留在会话里 |
| File Read Truncation | 当前轮文件读取结果 | `read_file` 返回的内容太长，不适合一次性全给模型 |
| Context Compaction | 整体历史消息 | 整个会话快撑满上下文，需要把旧消息整理成摘要 |

要点是：

- `Historical Tool Result Compaction` 处理“已经在会话里的历史工具结果”。
- `File Read Truncation` 处理“当前这一轮刚返回的大文本”。
- `Context Compaction` 处理“整段会话历史”。

它们不是一回事，也不是同一个开关。

## 先看整体流程

一次普通请求里，大致会经过下面的顺序：

```text
用户发起请求
  -> 模型开始本轮处理
  -> 如果调用 read_file，先按 File Read Truncation 决定当前轮最多返回多少文本
  -> 本轮结束前，系统检查历史工具结果是否需要做 Historical Tool Result Compaction
  -> 如果整段会话仍然过长，再决定是否触发 Context Compaction
  -> 后续轮次继续在“摘要 + 最近消息 + 近期工具结果”的结构上推进
```

可以把它理解成两层防线：

- 第一层是“当前轮立即截断”，避免刚返回的大文本立刻把上下文撑爆。
- 第二层是“历史压缩”，避免会话累积后越来越重。

## 四个核心概念

### 1. Historical Tool Result Compaction

这是“历史工具结果压缩”。

它不会改变工具第一次返回时的行为，而是在这些结果进入会话历史后，再根据新旧程度和字节阈值进行收缩。

它主要解决：

- Shell、读取文件、搜索、外部工具等结果已经很多轮了
- 模型不需要永远保留完整原文
- 但又不希望完全删掉上下文线索

### 2. File Read Truncation

这是“文件读取截断”。

它只影响同一轮里 `read_file` 返回给模型和会话的文本长度，不影响文件本身，也不限制底层文件是否存在。

它主要解决：

- 某次 `read_file` 读取到了很大的文件
- 当前轮只需要先给模型一个片段
- 不希望一下子把整段内容都塞进对话

如果文件读取结果被截断，系统会给出继续读取的提示，通常可以继续按提示使用 `read_file` 读取后续部分。

### 3. Context Compaction

这是“会话摘要压缩”。

它不只是压工具结果，而是会在整段对话接近上下文预算时，把更早的消息整理成摘要，只保留最近的一部分消息继续直接参与后续推理。

它主要解决：

- 会话已经进行了很多轮
- 最近内容还重要，但更早的细节可以变成摘要
- 需要在连续对话和上下文上限之间做平衡

## 默认行为

如果你没有做 source 级显式覆盖，可以按下面理解：

| 项目 | 默认行为 |
|------|----------|
| Historical Tool Result Compaction | 默认开启 |
| File Read Truncation | 默认沿用历史工具结果的近期字节阈值 |
| Context Compaction | 默认开启 |

这里最容易误解的是：

1. `File Read Truncation` 默认不是“关闭”，而是继续沿用历史工具结果里的近期阈值。

## 配置位置

项目里有两类常见配置入口：

1. Agent 运行配置
2. Source System Configuration

推荐这样理解：

- Agent 运行配置决定“这个 Agent 的通用默认行为”。
- Source System Configuration 决定“某个外部接入来源是否覆盖这些默认行为”。

如果某个 source 没有显式接管某一项能力，就继续沿用默认行为。

## Agent 运行配置

### `running.max_input_length`

| 默认值 | 含义 |
|--------|------|
| `131072` | 运行配置认为的上下文预算基准，单位是 token |

它会影响 Context Compaction 的触发时机。

使用建议：

- 配得过大：压缩可能触发过晚，容易在真实模型上超长。
- 配得过小：压缩可能触发过早，影响上下文连续性。

### `running.context_compact`

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `context_compact_enabled` | `true` | 是否允许把更早的消息整理成摘要 |
| `memory_compact_ratio` | `0.75` | 接近多大比例的上下文预算时开始考虑压缩 |
| `memory_reserve_ratio` | `0.1` | 压缩后保留多少比例的近期上下文 |
| `compact_with_thinking_block` | `true` | 是否把思考块也纳入压缩考虑 |
| `token_count_model` | `"default"` | token 估算使用的模型标识 |
| `token_count_use_mirror` | `false` | tokenizer 镜像选项 |
| `token_count_estimate_divisor` | `4` | 估算 token 时使用的近似参数 |

调参建议：

| 目标 | 建议 |
|------|------|
| 更早触发摘要压缩 | 降低 `memory_compact_ratio` |
| 更晚触发摘要压缩 | 提高 `memory_compact_ratio`，但不要超过真实模型能力 |
| 压缩后容易丢失当前任务细节 | 提高 `memory_reserve_ratio` |
| 想完全保留长历史不做摘要 | 不建议只靠关闭它，应同时检查工具结果压缩和输出截断策略 |

### `running.tool_result_compact`

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | `true` | 是否启用历史工具结果压缩 |
| `recent_n` | `2` | 最近多少段相关消息按“近期结果”规则处理 |
| `old_max_bytes` | `3000` | 更早工具结果保留的最大字节数 |
| `recent_max_bytes` | `50000` | 近期工具结果保留的最大字节数 |
| `retention_days` | `5` | 工具结果文件的保留天数 |

注意点：

- `recent_max_bytes` 应该大于等于 `old_max_bytes`。
- `recent_max_bytes` 还会影响默认的 `File Read Truncation` 行为。

调参建议：

| 目标 | 建议 |
|------|------|
| 最近几轮工具结果希望更完整 | 提高 `recent_n` 和 `recent_max_bytes` |
| 更早的工具结果太占上下文 | 降低 `old_max_bytes` |
| 不想做历史工具结果压缩 | 设置 `enabled=false`，但要接受上下文更快变长 |
| 续读文件保留太久 | 降低 `retention_days` |

### `running.memory_summary`

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `memory_summary_enabled` | `true` | 是否允许生成额外的记忆总结能力 |

它和会话里的 `compressed summary` 不是同一个概念。对普通使用者来说，如果你只关心当前会话是否会被整理成摘要，重点先看 `context_compact`。

## Source System Configuration

Source 级配置用于“只对某个接入来源覆盖默认行为”。

适合的场景：

- 某个 source 常常读取大文件
- 某个 source 常常调用返回超长文本的外部工具
- 不想影响其他 source 的默认行为

### Source 级可配置项

```json
{
  "tool_result_compact": {
    "enabled": true,
    "recent_n": 2,
    "old_max_bytes": 3000,
    "recent_max_bytes": 50000,
    "retention_days": 5
  },
  "file_read_truncation": {
    "enabled": true,
    "max_bytes": 50000
  }
}
```

### Source 级覆盖规则

#### `tool_result_compact`

- 只覆盖你显式写出来的字段。
- 没写的字段继续沿用 Agent 默认值。

例如：

```json
{
  "tool_result_compact": {
    "recent_max_bytes": 120000
  }
}
```

表示只把近期历史工具结果阈值调大，其他项仍沿用 Agent 默认值。

#### `file_read_truncation`

- 只有显式配置了这一段并带 `enabled`，才算这个 source 真正接管了文件读取截断。
- 如果整段缺失，或者没有 `enabled`，就继续走默认继承语义。

例如：

```json
{
  "file_read_truncation": {
    "enabled": true,
    "max_bytes": 12000
  }
}
```

表示这个 source 独立控制文件读取截断，不再沿用历史工具结果的近期阈值。

```json
{
  "file_read_truncation": {
    "enabled": false
  }
}
```

表示这个 source 显式关闭文件读取截断，不应再自动回退到另一套阈值。

### 一个重要规则：是否接管，要看 `enabled`

对 `file_read_truncation`，建议始终显式写出 `enabled`。

推荐写法：

```json
{
  "file_read_truncation": {
    "enabled": true,
    "max_bytes": 12000
  }
}
```

不推荐依赖下面这种写法表达接管：

```json
{
  "file_read_truncation": {
    "max_bytes": 12000
  }
}
```

在项目当前语义里，没有 `enabled` 的对象应视为“未完成接管表达”，不建议作为正式配置方式。

## 大输出时，系统会怎么处理

### 场景一：`read_file` 返回太长

如果当前 source 没有独立配置 `File Read Truncation`，系统会优先使用 `tool_result_compact.recent_max_bytes` 作为当前轮的读取上限。

被截断后：

- 当前轮只把片段返回给模型
- 会附带继续读取提示
- 你可以继续按提示使用 `read_file`

### 场景二：历史消息还是太长

即使你已经做了当前轮截断，随着对话继续增长，系统仍可能触发：

- Historical Tool Result Compaction
- Context Compaction

因此，“当前轮截断”不是“从此不会再压缩”的保证，而是降低当前轮对上下文的瞬时冲击。

## 常见调参策略

### 策略一：最近几轮工具结果尽量完整

适合：

- 最近几轮的搜索、文件、外部工具结果需要尽量保真

建议：

```json
{
  "running": {
    "tool_result_compact": {
      "recent_n": 5,
      "recent_max_bytes": 120000,
      "old_max_bytes": 3000
    }
  }
}
```

### 策略二：只让某个 source 读取更多文件内容

适合：

- 只有某个接入来源会频繁读大文件

建议：

```json
{
  "file_read_truncation": {
    "enabled": true,
    "max_bytes": 12000
  }
}
```

### 策略四：临时排查“是不是压缩影响了判断”

适合：

- 想快速确认是否因为历史工具结果压缩过多，导致模型判断变差

建议：

```json
{
  "running": {
    "tool_result_compact": {
      "enabled": false
    }
  }
}
```

注意：

- 这样会让上下文增长更快。
- 不代表 Context Compaction 也会同步关闭。

## 使用注意点

### 1. 关闭一种能力，不等于关闭全部压缩

最常见的误解是“我把某个开关关了，就不会再发生压缩或截断”。

实际上：

- 关闭 `Historical Tool Result Compaction`，不等于关闭 `Context Compaction`
- 关闭 `File Read Truncation`，不等于关闭历史工具结果压缩

### 2. 外部工具自己的截断，不归 Swe 控制

如果外部工具在返回给 Swe 之前就已经把结果裁掉了，那么 Swe 只能处理“已经收到的那部分内容”。

因此：

- Swe 能控制“收到之后如何保留”
- 不能控制“外部工具自己返回了多少”

### 3. 调大阈值不是越大越好

阈值越大：

- 当前轮更完整
- 但会更快消耗上下文预算
- 也更容易把问题推迟到后续轮次

因此推荐先小步调整，再观察效果。

## 常见现象与建议

| 现象 | 优先检查 |
|------|----------|
| 文件读取结果总是太短 | 是否被 `file_read_truncation` 接管；否则看 `tool_result_compact.recent_max_bytes` |
| 最近几轮工具结果不够完整 | 提高 `recent_n` 或 `recent_max_bytes` |
| 历史消息还是太快变成摘要 | 检查 `memory_compact_ratio`、`memory_reserve_ratio` 和工具结果阈值 |
| 关闭某个截断后仍觉得上下文变短 | 可能是 `Context Compaction` 仍在工作 |
| 某个 source 调整了配置但看起来没生效 | 检查该 section 是否显式写了 `enabled` |

## 推荐配置示例

### 默认稳妥型

```json
{
  "running": {
    "tool_result_compact": {
      "enabled": true,
      "recent_n": 2,
      "old_max_bytes": 3000,
      "recent_max_bytes": 50000,
      "retention_days": 5
    },
    "context_compact": {
      "context_compact_enabled": true,
      "memory_compact_ratio": 0.75,
      "memory_reserve_ratio": 0.1
    }
  }
}
```

### 大文件读取友好型 source

```json
{
  "file_read_truncation": {
    "enabled": true,
    "max_bytes": 20000
  }
}
```

### 最近结果更完整、旧结果更精简型

```json
{
  "running": {
    "tool_result_compact": {
      "enabled": true,
      "recent_n": 5,
      "recent_max_bytes": 120000,
      "old_max_bytes": 2000,
      "retention_days": 5
    }
  }
}
```

## 最后怎么判断该调哪一组配置

可以用下面的简单判断：

- 问题发生在 `read_file` 当轮返回太短：先看 `File Read Truncation`
- 问题发生在“几轮之后历史工具结果被收缩”：看 `Historical Tool Result Compaction`
- 问题发生在“整段对话越聊越短，只剩摘要”：看 `Context Compaction`

如果你只记住一句话：

`File Read Truncation` 管“当前轮”，`Historical Tool Result Compaction` 和 `Context Compaction` 管“历史”。
