## 1. Header Builder

- [x] 1.1 在 `src/swe/app/mcp/http_headers.py` 新增统一的 HTTP MCP header 构建 helper
- [x] 1.2 helper 中接入 tenant/source 上下文读取，并接受显式 `session_id`
- [x] 1.3 实现 `x-swe-tenant-id`、`x-swe-source-id`、`x-swe-session-id` 的默认注入
- [x] 1.4 实现保留 `x-swe-*` header 的大小写无关去重与最终小写输出

## 2. Runtime Integration

- [x] 2.1 修改 `src/swe/app/runner/runner.py::_create_mcp_client_with_headers()` 使用统一 helper
- [x] 2.2 把 `session_id` 从 query 请求路径传入 HTTP MCP client 创建逻辑
- [x] 2.3 保持 `stdio` transport 不走新的 `x-swe-*` 注入逻辑
- [x] 2.4 把最终 header 集写入 `_swe_rebuild_info`，确保重建路径一致

## 3. Rebuild Consistency

- [x] 3.1 校验 `src/swe/agents/react_agent.py::_rebuild_mcp_client()` 对 materialized headers 的复用方式
- [x] 3.2 如有必要，调整重建逻辑避免重复合并或丢失 `x-swe-*` header

## 4. Verification

- [x] 4.1 更新 `tests/unit/app/test_runner_mcp_http_timeouts.py`
- [x] 4.2 更新 `tests/unit/app/mcp/test_http_header_resolution.py`
- [x] 4.3 更新 `tests/unit/app/test_runner_auth_token_passthrough.py`
- [x] 4.4 评估后无需新增集成测试；现有单测已覆盖默认 `x-swe-*` header 组装、保留头覆盖与重建复用路径
