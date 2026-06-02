# Tool Result 截断定位

当生产工具返回中出现 `<<<TRUNCATED>>>` 时，优先按下面路径排查。

## 截断点

1. `read_file` 首次返回截断

   入口位于 `src/swe/agents/tools/file_io.py`。`read_file` 读取文件后，会用当前上下文的 `recent_max_bytes` 截断返回给模型的文本；如果上下文没有设置，则回退到 `src/swe/agents/tools/utils.py` 的 `DEFAULT_MAX_BYTES = 50 * 1024`。

2. 历史 `tool_result` 压缩截断

   入口位于 `src/swe/agents/hooks/memory_compaction.py`，最终委托 ReMe 的 `ToolResultCompactor`。当工具输出超过阈值时，ReMe 会把完整内容保存到 `tool_result/<uuid>.txt`，消息里只保留前缀内容和 `<<<TRUNCATED>>>` 续读提示。

3. MCP 工具返回

   `src/swe/app/mcp/__init__.py` 和 `src/swe/app/mcp/stateful_client.py` 只负责调用 `session.call_tool(...)`、转换 MCP content 为 AgentScope `ToolResponse`。MCP 层本身没有单独字节截断；MCP 返回进入消息历史后，仍会被同一套 `tool_result_compact` 策略处理。

## 当前默认值

应用层默认值在 `src/swe/config/config.py`：

```json
{
  "running": {
    "tool_result_compact": {
      "enabled": true,
      "recent_n": 2,
      "old_max_bytes": 3000,
      "recent_max_bytes": 50000,
      "retention_days": 5
    }
  }
}
```

- `recent_max_bytes`：近期工具结果和 `read_file` 首次返回的主要截断阈值。
- `old_max_bytes`：历史工具结果再次压缩时的阈值。
- `recent_n`：至少保留最近 N 条 tool_result 使用 `recent_max_bytes`。

## 临时调大方案

优先按 source 配置做临时覆盖，避免批量改 tenant / agent 文件。写入当前 source 或指定 source 的 `tool_result_compact`：

```json
{
  "tool_result_compact": {
    "enabled": true,
    "recent_n": 5,
    "old_max_bytes": 50000,
    "recent_max_bytes": 200000,
    "retention_days": 5
  }
}
```

推荐通过管理 API 写入，确保服务端缓存被刷新：

```text
PUT /api/source-system-config/current
PUT /api/source-system-config/sources/<source_id>
```

请求需要携带正常生产身份头，至少包括 `X-Tenant-Id`、`X-Source-Id` 和 `X-User-Role: manager` 或 `admin`。如果绕过 API 直接改 `swe_source_system_config` 表，已有进程最多可能继续使用约 30 秒缓存。

如果没有启用 source 系统配置，或需要按 agent 固定生效，则修改对应文件：

```text
~/.swe/<tenant_id>/workspaces/<workspace_id>/agent.json
```

在 `running.tool_result_compact` 下调大同样字段。注意 `recent_max_bytes` 必须大于等于 `old_max_bytes`；数值越大，模型上下文和 token 消耗越高。
