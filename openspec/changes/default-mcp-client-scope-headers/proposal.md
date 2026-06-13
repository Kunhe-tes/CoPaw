## Why

当前远程 HTTP MCP client 的出站请求只会携带两类 header：
- MCP 配置里静态声明的 `headers`
- 请求期透传的 `x-header-*` / `cookie`

这导致远程 MCP 服务拿不到 Swe 当前请求的运行时身份，至少有三个实际问题：
- 无法默认识别调用属于哪个 tenant/source/session
- 每个 MCP client 都要手工配置相同的 `x-swe-*` header，容易遗漏
- 即使静态 header 配好了，`session_id` 这类请求级字段也无法正确跟随每次调用变化

用户期望是：调用 MCP client 接口时，默认附带 `x-swe-tenant-id`、`x-swe-source-id`、`x-swe-session-id`，让远程 MCP 服务天然具备 Swe 侧上下文。

## What Changes

- **修改** HTTP MCP client 的默认 header 组装逻辑，在 `streamable_http` 和 `sse` transport 下自动注入：
  - `x-swe-tenant-id`
  - `x-swe-source-id`
  - `x-swe-session-id`
- **新增** 统一的 MCP HTTP header 构建 helper，集中处理：
  - 静态配置 header
  - passthrough header
  - 运行时 `x-swe-*` header
  - 保留 header 的优先级与大小写去重规则
- **修改** 请求级 MCP client 创建路径，确保首次连接与中断后重建都使用同一份最终 header 集
- **新增** 针对 header 合并、大小写覆盖、缺省字段和重建路径的测试

## Capabilities

### Modified Capabilities

- `source-scoped-runtime-isolation`: 远程 HTTP MCP 服务默认接收 Swe 运行时 tenant/source/session 身份
- `skill-session-hook-loading`: MCP 工具侧的请求上下文传播从显式配置改为默认内建

## Impact

- **代码文件**
  - `src/swe/app/mcp/http_headers.py`
  - `src/swe/app/runner/runner.py`
  - `src/swe/agents/react_agent.py`
  - `tests/unit/app/test_runner_mcp_http_timeouts.py`
  - `tests/unit/app/mcp/test_http_header_resolution.py`
  - `tests/unit/app/test_runner_auth_token_passthrough.py`
- **行为变化**
  - 仅影响 HTTP 类 MCP client（`streamable_http` / `sse`）
  - `stdio` MCP client 保持不变
  - 若用户配置了同名 `x-swe-*` header，运行时注入值将覆盖配置值
- **兼容性**
  - 对现有 MCP 服务是向前兼容的附加 header 变更
  - 对依赖伪造同名 `x-swe-*` header 的配置属于行为收敛，后续以运行时真实身份为准
