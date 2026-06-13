# 静态文件访问网络

本文说明 `copy_file_to_static` 如何按办公网或业务网生成静态文件访问 URL，以及 Console 如何把当前页面网络环境传给后端。

## 适用场景

同一个静态文件在不同网络环境下可能需要不同域名：

- 办公网访问：使用办公网域名。
- 业务网访问：使用业务网域名。
- 本地开发：未配置域名时回退到 `http://localhost:8088`。

该能力只影响生成给用户点击或下载的静态文件 URL，不改变文件实际落盘位置。

## 网络类型

当前只支持两个规范值：

| 值 | 含义 |
| --- | --- |
| `office` | 办公网 |
| `business` | 业务网 |

入口函数是 `src/swe/config/context.py`：

- `normalize_file_url_network(value)`：未知值回退到 `office` 并写 warning。
- `set_current_file_url_network(value)`：把本次请求的网络类型绑定到 ContextVar。
- `resolve_file_url_base(network)`：按网络类型解析实际 URL base。

## 域名配置

静态文件域名通过环境变量配置：

| 环境变量 | 用途 |
| --- | --- |
| `FILE_URL_OFFICE` | 办公网静态文件域名 |
| `FILE_URL` | 旧办公网域名配置，`FILE_URL_OFFICE` 缺失时使用 |
| `FILE_URL_BUSINESS` | 业务网静态文件域名 |

解析规则：

1. `office` 优先使用 `FILE_URL_OFFICE`，其次使用 `FILE_URL`，最后回退到 `http://localhost:8088`。
2. `business` 优先使用 `FILE_URL_BUSINESS`。
3. 如果请求 `business` 但没有配置 `FILE_URL_BUSINESS`，会记录 warning 并回退到办公网域名。
4. 域名会去掉尾部 `/`，避免拼接出双斜杠。

示例：

```bash
FILE_URL_OFFICE=https://office.example
FILE_URL_BUSINESS=https://business.example
```

## 请求链路

Console 会根据当前页面 hostname 推断网络：

| 文件 | 规则 |
| --- | --- |
| `console/src/pages/Chat/fileUrlNetwork.ts` | hostname 包含 `paas.cmbchina.cn` 时使用 `business`，否则使用 `office` |
| `console/src/pages/Chat/index.tsx` | 发送 chat 请求时写入 `file_url_network` |
| `src/swe/app/routers/console.py` | `_extract_session_and_payload()` 把字段写入 native payload 的 `meta` |
| `src/swe/app/runner/runner.py` | `_request_file_url_network()` 从 request 或 `channel_meta` 读取并绑定 ContextVar |

runner 会在 `_stream_query_after_preflight()` 中设置当前请求的 `file_url_network`，并在 finally 中 reset，避免并发请求之间互相污染。

## `copy_file_to_static` 输出

工具入口是：

```text
src/swe/agents/tools/copy_file_to_static.py
```

它会把文件复制到当前 workspace 的 `static` 目录，然后生成 URL：

```text
<resolved_file_url_base>/static/<runtime_scope_id>/<agent_id>/<file_name>
```

返回的工具输出是结构化 JSON：

```json
{
  "ok": true,
  "path": "![report.html](https://business.example/static/scope/default/report.html)",
  "url": "https://business.example/static/scope/default/report.html",
  "network": "business",
  "message": "已返回 Markdown 格式的访问链接"
}
```

说明：

- `url` 是前端下载卡片优先使用的结构化 URL。
- `path` 保留 Markdown 兼容格式，供旧渲染或文本场景使用。
- `network` 表示最终实际使用的网络类型；业务网缺少域名配置时会返回 `office`。
- 文件实际仍在 `<workspace_dir>/static`，网络类型只影响展示 URL。

## 前端渲染

`console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/customToolRenders/CopyFileToStatic.tsx` 会解析工具输出：

1. 优先读取结构化 `url`。
2. 如果没有 `url`，再从 `path` 的 Markdown 链接里解析 URL。
3. 用 `DownloadFileCard` 展示下载卡片。
4. HTML auto-preview 链接仍走现有点击追踪逻辑。

## 排查入口

如果用户看到的静态文件链接域名不对，按下面顺序查：

1. Console 当前 hostname 是否命中 `paas.cmbchina.cn`。
2. 请求 payload 是否带了 `file_url_network`。
3. `runner.py` 是否从 request 或 `channel_meta` 读到了该字段。
4. 环境变量 `FILE_URL_OFFICE`、`FILE_URL`、`FILE_URL_BUSINESS` 是否配置。
5. `copy_file_to_static` 输出中的 `network` 是否和预期一致。

## 覆盖测试

重点测试文件：

- `tests/unit/agents/tools/test_copy_file_to_static.py`
- `tests/unit/app/test_runner_file_url_network.py`
- `tests/unit/app/test_console_chat_file_url_network.py`
- `console/src/pages/Chat/fileUrlNetwork.test.ts`
- `console/src/components/agentscope-chat/AgentScopeRuntimeWebUI/customToolRenders/CopyFileToStatic.test.ts`
