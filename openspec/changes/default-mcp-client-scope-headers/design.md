## Context

当前仓库里，HTTP MCP header 的处理分散在三处：

- `src/swe/app/mcp/http_headers.py`
  - 只负责展开环境变量与 tenant env 引用
- `src/swe/app/runner/runner.py::_create_mcp_client_with_headers()`
  - 负责把静态配置 header 与 passthrough header 合并
- `src/swe/agents/react_agent.py::_rebuild_mcp_client()`
  - 在 MCP 会话异常后，依据 `_swe_rebuild_info` 重新创建 client

这套实现还没有把 Swe 自己的运行时身份默认传播给远程 MCP 服务，因此远端服务感知不到：
- 当前 tenant
- 当前 source
- 当前 session

同时，现有合并逻辑没有显式处理保留 header 的大小写冲突。例如配置中若写了 `X-Swe-Tenant-Id`，运行时再写 `x-swe-tenant-id`，有机会形成大小写不同但语义相同的重复 header。

## Goals / Non-Goals

**Goals**

- 让所有 HTTP MCP client 默认携带 `x-swe-tenant-id`、`x-swe-source-id`、`x-swe-session-id`
- 保证首次创建和重建后的 header 集一致
- 明确 `x-swe-*` header 的优先级，禁止被静态配置或 passthrough 伪造覆盖
- 不改变 `stdio` transport 行为

**Non-Goals**

- 不把 `x-swe-*` header 暴露成用户可配置模板系统
- 不修改 Console 上的 MCP 配置表单
- 不扩展到 MCP 之外的普通 HTTP 请求
- 不引入新的上下文变量来保存 session 以外的额外身份

## Decisions

### 决策 1：新增统一的 HTTP MCP header 构建 helper

**选择**：在 `src/swe/app/mcp/http_headers.py` 增加新的组装函数，统一完成：
- 静态 header 解析
- passthrough header 合并
- 运行时 `x-swe-*` header 注入

**理由**：
- 当前逻辑分散在 runner / rebuild 路径，后续很容易再漂移
- `resolve_mcp_http_headers()` 的职责是“解析”，不适合继续塞入 merge 细节；新增 helper 更清晰
- 后续若再增加保留 header，只需改一处

**建议接口**：

```python
def build_mcp_http_headers(
    headers: Mapping[str, str] | None,
    *,
    passthrough_headers: Mapping[str, str] | None = None,
    session_id: str | None = None,
) -> dict[str, str] | None:
    ...
```

该函数内部从当前上下文读取 `tenant_id` / `source_id`，并把 `session_id` 作为显式参数传入。

### 决策 2：`x-swe-*` 使用保留字段语义，并在最终阶段覆盖

**选择**：header 合并优先级固定为：

1. 静态配置 header
2. passthrough header
3. 运行时 `x-swe-*` header

**理由**：
- `x-swe-*` 代表 Swe 自己解析出的真实请求身份，不能被配置或外部来包伪造
- passthrough 仍应保留对普通 header 的覆盖能力，例如 `authorization`、`cookie`
- 这能把“调用者身份”和“业务自定义 header”明确分层

### 决策 3：保留 header 做大小写无关覆盖，最终统一写成小写

**选择**：在注入 `x-swe-*` 前，先对现有 header 做一次大小写无关清理；凡是 `.lower()` 后命中：
- `x-swe-tenant-id`
- `x-swe-source-id`
- `x-swe-session-id`

都先删掉，再写入新的小写 key。

**理由**：
- HTTP header 语义上大小写不敏感，但 Python dict 是大小写敏感的
- 如果不清理，`X-Swe-Tenant-Id` 与 `x-swe-tenant-id` 可能并存，导致远端行为不可预测
- 用户要求的字段名本身就是小写，最终也应稳定输出为小写

### 决策 4：缺失身份时只省略对应 header，不伪造空值

**选择**：
- `tenant_id` 有值时注入 `x-swe-tenant-id`
- `source_id` 有值时注入 `x-swe-source-id`
- `session_id` 非空时注入 `x-swe-session-id`
- 对缺失字段不写空字符串 header

**理由**：
- 空字符串 header 会把“未知”和“明确为空”混成一类
- 省略字段更利于远端按 presence 判断能力
- 这与当前仓库中 source/session 并非所有入口都强制存在的事实一致

### 决策 5：request-scoped client 在创建时写入“最终 header 集”到 rebuild info

**选择**：`runner._create_mcp_client_with_headers()` 在构建完最终 header 后：
- 用这份最终 header 初始化 `HttpStatefulClient`
- 同时把同一份最终 header 写入 `_swe_rebuild_info["headers"]`

`react_agent._rebuild_mcp_client()` 重建时直接复用这份 materialized headers。

**理由**：
- 重建应复现“这次请求实际连出去时的 header”，而不是重新推导一遍
- `session_id` 是请求级数据，不适合在重建路径里依赖隐式猜测
- materialized headers 可以天然保留静态 header、passthrough header 与 `x-swe-*` 的最终结果

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|---------|
| 远程 MCP 服务依赖用户自定义的同名 `x-swe-*` 值 | 文档明确这些字段为运行时保留 header，测试验证运行时覆盖 |
| 新 helper 只接入 runner，遗漏重建路径 | 用 `_swe_rebuild_info["headers"]` 固化最终 header，并补充重建测试 |
| 缺失 `source_id` 的入口行为不一致 | 约定“缺失则省略”，并补测试覆盖 |
| header 合并改动影响现有 passthrough 行为 | 保持非保留 header 的现有 merge 顺序不变，并复用现有测试断言 |

## Design Details

### Header 组装流程

```text
client_config.headers
  -> resolve_mcp_http_headers() 解析 env 引用
  -> merge passthrough_headers
  -> 删除大小写冲突的保留 x-swe-* keys
  -> 注入运行时 x-swe-tenant-id / x-swe-source-id / x-swe-session-id
  -> 返回最终 headers
```

### 请求级创建路径

```text
AgentRunner.query_handler()
  -> 解析 request.session_id / tenant context / source context
  -> _build_and_connect_mcp_clients(..., passthrough_headers=...)
  -> _create_mcp_client_with_headers(..., session_id=request.session_id)
  -> HttpStatefulClient(headers=final_headers)
```

### 重建路径

```text
首次创建 request-scoped HTTP MCP client
  -> _swe_rebuild_info["headers"] = final_headers

MCP 会话中断
  -> SWEAgent._rebuild_mcp_client()
  -> 使用 _swe_rebuild_info["headers"] 重新创建 HttpStatefulClient
```

### 测试策略

1. 扩充 `tests/unit/app/test_runner_mcp_http_timeouts.py`
   - 断言 HTTP transport 默认附带 3 个 `x-swe-*` header
   - 断言保留 header 采用运行时值覆盖静态值
2. 扩充 `tests/unit/app/mcp/test_http_header_resolution.py`
   - 断言 env 解析与 `x-swe-*` 注入可以同时成立
   - 断言缺失 `source_id` / `session_id` 时省略对应 header
3. 扩充 `tests/unit/app/test_runner_auth_token_passthrough.py`
   - 断言 passthrough `cookie` 仍保留，且不会覆盖保留 `x-swe-*`
4. 如实现阶段需要端到端兜底，再补一条 loopback MCP 集成测试验证远端实际收到 header

## File Structure

```text
src/swe/
├── app/
│   ├── mcp/
│   │   └── http_headers.py      # 新增统一 header builder
│   └── runner/
│       └── runner.py            # 请求级 client 构建改走统一 helper
└── agents/
    └── react_agent.py           # 重建路径复用最终 headers

tests/
├── unit/app/
│   ├── test_runner_mcp_http_timeouts.py
│   ├── test_runner_auth_token_passthrough.py
│   └── mcp/test_http_header_resolution.py
```

## Migration Plan

1. 先引入统一 helper 和对应单元测试
2. 再接入 request-scoped HTTP MCP client 创建路径
3. 最后校验重建路径与保留 header 覆盖行为

整个变更不要求迁移现有 MCP 配置；新 header 为运行时自动附加。
