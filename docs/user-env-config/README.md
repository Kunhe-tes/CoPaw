# 环境变量设置与使用说明

本文档面向普通用户和外部接入方，说明如何在 Swe 中为用户或来源配置运行时环境变量，以及这些变量会在哪些场景中生效。

## 适用场景

环境变量适合保存运行时需要使用的配置或密钥，例如：

- MCP Server 需要的访问令牌
- 外部 API Key
- Hook 或 Shell 命令执行时需要读取的业务配置
- 按用户、来源隔离的第三方服务凭据

环境变量按请求 scope 隔离。调用接口时需要提供 `X-Tenant-Id` 和 `X-Source-Id`，同一个用户在不同来源下可以拥有不同的环境变量。

## 生效范围

配置后的环境变量会在以下运行时场景中使用：

- Shell 命令执行
- Command Hook 执行
- MCP stdio Server 子进程
- MCP HTTP Header 中显式引用的变量

需要注意：

- MCP stdio 会把当前 scope 的环境变量注入到 MCP Server 进程环境中。
- MCP HTTP 不会自动把所有环境变量加入 header。只有在 MCP header 配置中显式写 `${ENV:变量名}` 时，才会解析当前 scope 的变量值。
- 已经启动的 MCP stdio 进程不会自动收到后续修改的环境变量，需要重启或重新加载 MCP 客户端后生效。
- 普通查询接口不会返回明文密钥，只会返回掩码值。

## 通用请求头

外部调用 tenant scoped API 时通常需要携带：

```http
Authorization: Bearer <token>
X-Tenant-Id: <tenant_id>
X-Source-Id: <source_id>
Content-Type: application/json
```

其中：

- `X-Tenant-Id` 表示用户或租户身份。
- `X-Source-Id` 表示来源、渠道或业务系统。
- 两者共同决定环境变量保存和读取的 scope。

## 设置当前 scope 环境变量

使用 `PUT /api/envs` 全量保存当前 scope 的环境变量。

```http
PUT /api/envs
```

请求体：

```json
{
  "MCP_TOKEN": "tenant-secret",
  "OPENAI_API_KEY": "sk-xxx"
}
```

响应示例：

```json
[
  {
    "key": "MCP_TOKEN",
    "value": "********"
  },
  {
    "key": "OPENAI_API_KEY",
    "value": "********"
  }
]
```

示例：

```bash
curl -X PUT "http://127.0.0.1:8099/api/envs" \
  -H "Authorization: Bearer <token>" \
  -H "X-Tenant-Id: tenant-a" \
  -H "X-Source-Id: source-a" \
  -H "Content-Type: application/json" \
  -d '{"MCP_TOKEN":"tenant-secret","OPENAI_API_KEY":"sk-xxx"}'
```

`PUT /api/envs` 是全量替换语义。请求体中没有出现的旧变量会被删除。

## 增量更新环境变量

使用 `PATCH /api/envs` 增量更新当前 scope 的环境变量，适合在不知道旧密钥明文时保留原值。

```http
PATCH /api/envs
```

请求体：

```json
{
  "values": {
    "NEW_TOKEN": "new-secret"
  },
  "preserve": ["MCP_TOKEN"],
  "delete": ["OLD_TOKEN"]
}
```

字段说明：

- `values`：新增或覆盖的变量。
- `preserve`：保留已有值的变量。
- `delete`：删除的变量。

响应仍只返回掩码值：

```json
[
  {
    "key": "MCP_TOKEN",
    "value": "********"
  },
  {
    "key": "NEW_TOKEN",
    "value": "********"
  }
]
```

## 查询环境变量

使用 `GET /api/envs` 查询当前 scope 已配置的环境变量。

```http
GET /api/envs
```

响应示例：

```json
[
  {
    "key": "MCP_TOKEN",
    "value": "********"
  }
]
```

查询接口不会返回明文值。看到 `********` 表示该变量已有非空值。

## 删除单个环境变量

使用 `DELETE /api/envs/{key}` 删除当前 scope 的单个环境变量。

```http
DELETE /api/envs/MCP_TOKEN
```

删除成功后返回剩余变量的掩码列表。变量不存在时返回 `404`。

## 为指定用户和来源写入环境变量

管理端或内部系统可以使用 `PUT /api/envs/target` 为指定目标 scope 写入环境变量。

```http
PUT /api/envs/target
```

该接口需要管理权限，请求头需要包含：

```http
X-User-Role: manager
```

或：

```http
X-User-Role: admin
```

请求体：

```json
{
  "target_tenant_id": "tenant-b",
  "target_source_id": "source-b",
  "values": {
    "MCP_TOKEN": "target-secret"
  }
}
```

响应示例：

```json
{
  "envs": [
    {
      "key": "MCP_TOKEN",
      "value": "********"
    }
  ],
  "audit": {
    "actor": "manager-1",
    "target_tenant_id": "tenant-b",
    "target_source_id": "source-b",
    "keys": ["MCP_TOKEN"]
  }
}
```

示例：

```bash
curl -X PUT "http://127.0.0.1:8099/api/envs/target" \
  -H "Authorization: Bearer <token>" \
  -H "X-Tenant-Id: tenant-a" \
  -H "X-Source-Id: source-a" \
  -H "X-User-Role: manager" \
  -H "X-User-Id: manager-1" \
  -H "Content-Type: application/json" \
  -d '{"target_tenant_id":"tenant-b","target_source_id":"source-b","values":{"MCP_TOKEN":"target-secret"}}'
```

## 在 MCP 中使用环境变量

### MCP stdio

MCP stdio Server 会在启动时接收当前 scope 的环境变量。例如当前 scope 配置了：

```json
{
  "MCP_TOKEN": "tenant-secret"
}
```

stdio 类型的 MCP Server 进程中可以直接读取 `MCP_TOKEN`。

如果 MCP 客户端自身配置里也设置了同名 `env`，客户端配置值优先生效。

### MCP HTTP Header

HTTP 类型 MCP 不会自动携带全部环境变量。需要在 MCP client 的 header 配置中显式引用：

```json
{
  "headers": {
    "Authorization": "Bearer ${ENV:MCP_TOKEN}"
  }
}
```

运行时会把 `${ENV:MCP_TOKEN}` 替换为当前 scope 中 `MCP_TOKEN` 的值。

普通 `${MCP_TOKEN}` 不表示 tenant runtime env 引用，不建议用于租户隔离密钥。

## 命名与限制

环境变量名必须满足：

```text
^[A-Za-z_][A-Za-z0-9_]*$
```

变量值必须是字符串。

以下变量名受保护，不能通过用户环境变量接口写入：

- `SWE_WORKING_DIR`
- `SWE_SECRET_DIR`
- `PATH`
- `HOME`
- `SHELL`
- `BASH_ENV`
- `ENV`
- `ZDOTDIR`
- `IFS`
- `CDPATH`
- `PYTHONPATH`
- `PYTHONHOME`
- `LD_LIBRARY_PATH`
- `DYLD_LIBRARY_PATH`

## 常见问题

### 为什么查询接口看不到明文值？

这是预期行为。环境变量通常包含密钥，查询接口只返回掩码值，避免普通页面或日志暴露明文。

### 修改环境变量后 MCP 没生效怎么办？

如果是 MCP stdio，已启动的进程不会自动更新环境变量。请重启或重新加载对应 MCP 客户端。

如果是 MCP HTTP Header，请确认 header 中使用的是 `${ENV:变量名}` 语法。

### 不同来源的变量会互相覆盖吗？

不会。`X-Tenant-Id` 和 `X-Source-Id` 共同决定 scope。同一个 `X-Tenant-Id` 下，不同 `X-Source-Id` 会保存到不同 scope。

### 可以通过普通 `/api/envs` 写入其他用户的变量吗？

不可以。普通 `/api/envs` 只写当前请求头对应的 scope。需要管理端写入目标用户和来源时，请使用 `PUT /api/envs/target`。
