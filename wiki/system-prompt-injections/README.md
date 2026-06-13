# 系统提示词注入

本文说明 source 级和请求级 `system_prompt_injections` 如何配置、合并，并在一次 Agent 请求中进入最终 system prompt。

## 适用场景

`system_prompt_injections` 适合保存和 source 或一次请求强相关的运行规则，例如：

- 某个业务来源的固定作答约束。
- 某次 chat 请求临时附加的运行说明。
- 不适合写进全局 `system_prompt_files`，但需要在 Agent system prompt 中生效的补充内容。

它不是用户输入过滤器，也不是权限隔离机制。不要把不可信用户内容直接作为系统提示词注入。

## 两个来源

### Source 系统配置

Source 级配置字段是：

```json
{
  "system_prompt_injections": [
    "优先使用当前 source 的业务口径回答。",
    "涉及敏感操作时先说明风险。"
  ]
}
```

后端注册和规范化入口：

| 文件 | 职责 |
| --- | --- |
| `src/swe/app/source_system_config/registry.py` | 定义 `SYSTEM_PROMPT_INJECTIONS_PATH`、默认值、规范化和默认裁剪规则 |
| `src/swe/app/source_system_config/runtime.py` | 暴露 `get_system_prompt_injections()`，从当前绑定的 source config 读取注入列表 |
| `console/src/pages/SystemConfigPage/registry.ts` | Console 表单读写、去重和 textarea 文本转换 |
| `console/src/pages/SystemConfigPage/index.tsx` | 在系统特性配置页展示和保存该字段 |

规范化规则：

- 字段必须是数组。
- 每个元素会转成字符串并 `trim()`。
- 空字符串会被丢弃。
- 重复内容只保留第一次出现的值。
- 空列表会在保存时从显式配置中删除，运行时仍按默认空列表处理。

### 请求级注入

Chat 请求也可以携带本次请求级注入：

```json
{
  "input": [...],
  "session_id": "session-a",
  "user_id": "tenant-a",
  "system_prompt_injections": [
    "这次回答只返回三条建议。"
  ]
}
```

请求级字段在这些位置透传：

| 文件 | 职责 |
| --- | --- |
| `console/src/api/types/agent.ts` | `AgentRequest.system_prompt_injections?: string[]` |
| `src/swe/app/routers/console.py` | `_extract_session_and_payload()` 把字段写入 native payload 的 `meta` |
| `src/swe/app/runner/runner.py` | `_request_system_prompt_injections()` 从 request 或 `channel_meta` 读取 |

如果请求级 payload 不是数组，runner 会记录 warning 并忽略这部分注入，不中断请求。

## 合并和生效位置

一次请求进入 `AgentRunner.stream_query()` 后，runner 会先构造基础 `env_context`，再合并 source 级和请求级注入：

```text
source config system_prompt_injections
  + request system_prompt_injections
  -> 去重并保留首次出现顺序
  -> 追加到 env_context
  -> SWEAgent._build_sys_prompt()
  -> 最终 system prompt
```

最终追加格式固定为：

```text
[System prompt injections]
<第一段注入>

<第二段注入>
```

关键实现：

- `_merge_system_prompt_injections()`：按 source 级优先、请求级其次的顺序合并并去重。
- `_with_system_prompt_injections()`：把合并后的内容追加到 `env_context`。
- `build_env_context()` 仍负责 tenant、source、workspace 等基础运行上下文。

## 与 `system_prompt_files` 的区别

| 能力 | 来源 | 生效粒度 | 典型用途 |
| --- | --- | --- | --- |
| `system_prompt_files` | Agent 配置文件 | Agent / tenant 配置 | 长期、稳定、通用的系统提示词文件 |
| source 级 `system_prompt_injections` | Source 系统配置 | tenant + source | 某个业务来源的可运营配置 |
| 请求级 `system_prompt_injections` | 单次请求 payload | 单次请求 | 临时运行规则或一次性约束 |

## 排查入口

如果注入未生效，按下面顺序查：

1. Console 保存后的 source config 中是否存在 `system_prompt_injections`。
2. 当前请求是否绑定了正确的 source config；入口在 `src/swe/app/source_system_config/middleware.py` 和 `runtime.py`。
3. 请求级字段是否真的传到了 `AgentRequest` 或 `channel_meta`。
4. `runner.py` 中 `_merge_system_prompt_injections()` 合并后是否为空。
5. 最终 system prompt 是否包含 `[System prompt injections]` 块。

## 覆盖测试

重点测试文件：

- `tests/unit/app/test_source_system_config.py`
- `tests/unit/app/test_runner_system_prompt_injections.py`
- `tests/unit/app/test_console_chat_system_prompt_injections.py`
- `console/src/pages/SystemConfigPage/registry.test.ts`
- `console/src/pages/SystemConfigPage/index.test.tsx`
