# Chat API

本文档说明当前 Console 使用的两个聊天接口：

- `POST /api/console/chat`：提交一轮对话并通过 SSE 接收流式结果。
- `GET /api/chats/{chat_id}/history`：读取指定 ChatSpec 的压缩归档历史。

## 通用约定

### 基础地址

以下示例中的 `BASE_URL` 表示 Swe 服务地址，例如 `http://localhost:8088`。实际请求路径需要保留 `/api` 前缀。

如果启用了 agent-scoped 路由，同一组能力也可以通过下面的路径访问：

```text
/api/agents/{agent_id}/console/chat
/api/agents/{agent_id}/chats/{chat_id}/history
```

本文主体只描述用户请求中指定的两个非 agent-scoped 路径。

### 身份与请求头

除部署层额外配置的认证头外，非豁免 API 请求通常需要以下身份头：

| Header | 必填 | 说明 |
| --- | --- | --- |
| `X-Source-Id` | 是 | 来源标识，用于租户/数据隔离；缺失或格式非法返回 `400`。 |
| `X-Tenant-Id` | 视部署配置 | 租户标识。开启强制租户模式时必填。 |
| `X-User-Id` | 建议 | 当前用户标识。对 Console 对话请求，如果服务端已解析该身份，必须与请求体 `user_id` 一致。 |
| `Authorization` | 视部署配置 | 常规 Bearer Token。 |
| `X-Auth-Authorization` | 视部署配置 | 外部系统集成时可能使用的认证头。 |
| `X-Agent-Id` | 否 | 选择 agent；也可以使用 agent-scoped 路径。 |
| `X-B3-Traceid` | 否 | 链路追踪 ID；如果运行时生成的 response 没有 `trace_id`，Console 流会补充该值。 |

请求 JSON 接口时使用：

```http
Content-Type: application/json
```

---

## 1. 提交 Console 对话

### 基本信息

```http
POST /api/console/chat
Content-Type: application/json
Accept: text/event-stream
```

接口返回 HTTP `200` 后保持连接，并以 Server-Sent Events（SSE）格式返回多个事件。每个数据事件形如：

```text
data: {"object":"response",...}

```

事件之间使用空行分隔；`: keep-alive` 是 SSE 注释帧，不包含业务数据。

### 请求体

当前 Console 适配器实际读取的字段如下。除 `input` 外，未传字段使用表格中的默认值。

| 字段 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `input` | `array` | 是（实际对话建议至少 1 项） | 无 | 输入消息数组。每项至少包含 `content`；当前 Console 常用一项 user 消息。 |
| `input[].role` | `string` | 建议 | `user` | 常用值为 `user`。 |
| `input[].type` | `string` | 建议 | `message` | 消息类型，通常为 `message`。 |
| `input[].content` | `array` | 是 | 无 | 多模态内容块数组。文本块格式为 `{ "type": "text", "text": "..." }`。 |
| `session_id` | `string` | 否 | `default` | 逻辑会话 ID。新请求使用它归并到同一会话；重连时也可以传后端 `chat_id`。 |
| `user_id` | `string` | 否 | `default` | 用户 ID。开启请求身份校验时必须与已认证用户一致。 |
| `channel` | `string` | 否 | `console` | 通道标识，Console 请求应使用 `console`。 |
| `stream` | `boolean` | 否 | `true` | 兼容 AgentRequest 的字段；该路由始终返回 SSE 流，不建议设为 `false`。 |
| `reconnect` | `boolean` | 否 | `false` | 为 `true` 时不新建运行，而是连接一个仍在运行的 chat。此时 `input` 内容不会启动新一轮推理。 |
| `user_name` | `string` | 否 | 无 | 用户展示名/链路追踪字段。也可以由 `X-User-Name` 身份头提供。 |
| `bbk_id` | `string` | 否 | 无 | 组织或业务维度标识。也可以由 `X-Bbk-Id` 身份头提供。 |
| `system_prompt_injections` | `array[string]` | 否 | 无 | 请求级 system prompt 注入片段，按字符串数组传递。 |
| `selected_skill_names` | `array[string]` | 否 | 无 | 本轮显式选择的技能名称。 |
| `context_references` | `array[object]` | 否 | 无 | 本轮上下文引用，例如技能或工作区文件引用。 |
| `file_url_network` | `string` | 否 | 无 | 静态文件 URL 网络类型，规范值为 `office` 或 `business`。 |

#### `input.content` 支持的内容块

常用内容块如下：

| `type` | 主要字段 | 用途 |
| --- | --- | --- |
| `text` | `text: string` | 文本消息。 |
| `image` | `image_url: string` | 图片 URL。 |
| `video` | `video_url: string` | 视频 URL。 |
| `audio` | `data: string`, `format?: string` | 音频数据或地址。 |
| `file` | `file_url?: string`, `file_id?: string`, `filename?: string`, `file_data?: string` | 文件附件。 |
| `data` | `data: object` | 结构化数据。 |

内容块还可以携带运行时通用字段 `object`、`status`、`delta`、`index`、`msg_id`、`sequence_number`；普通请求通常不需要手动设置这些字段。

#### AgentRequest 兼容字段

请求可以通过 AgentScope Runtime 的 `AgentRequest` 校验，因此也可能接受 `id`、`model`、`top_p`、`temperature`、`frequency_penalty`、`presence_penalty`、`max_tokens`、`stop`、`n`、`seed`、`tools` 等字段。但当前 Console 路由会把请求转换为 Console 原生 payload，只明确转发本节前表中的会话、身份和上下文字段；不要依赖这些通用字段改变当前 Console 使用的模型参数。

### 新建对话请求示例

```bash
curl -N -X POST "${BASE_URL}/api/console/chat" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "X-Tenant-Id: tenant-a" \
  -H "X-User-Id: user-001" \
  -H "X-Source-Id: portal" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "input": [
      {
        "role": "user",
        "type": "message",
        "content": [
          {
            "type": "text",
            "text": "请总结本周销售数据"
          }
        ]
      }
    ],
    "session_id": "session-user-001",
    "user_id": "user-001",
    "channel": "console",
    "stream": true,
    "context_references": [],
    "file_url_network": "office"
  }'
```

### 多模态请求示例

```json
{
  "input": [
    {
      "role": "user",
      "type": "message",
      "content": [
        {"type": "text", "text": "请描述这张图片"},
        {"type": "image", "image_url": "https://example.com/report.png"}
      ]
    }
  ],
  "session_id": "session-user-001",
  "user_id": "user-001",
  "channel": "console"
}
```

上下文引用示例：

```json
[
  {
    "type": "skill",
    "id": "skill:writer",
    "name": "writer"
  },
  {
    "type": "workspace_file",
    "id": "workspace_file:media/report.txt",
    "root": "media",
    "relative_path": "report.txt"
  }
]
```

### 重连请求示例

重连只连接正在运行的任务，不会创建新的 ChatSpec，也不会使用本次请求中的 `input` 启动推理。`session_id` 可以是后端 `chat_id`，也可以是该 chat 对应的逻辑 session ID。

```bash
curl -N -X POST "${BASE_URL}/api/console/chat" \
  -H "X-Tenant-Id: tenant-a" \
  -H "X-User-Id: user-001" \
  -H "X-Source-Id: portal" \
  -H "Content-Type: application/json" \
  -d '{
    "reconnect": true,
    "session_id": "2d5f8fb3-6b17-4c77-b5a1-1e03f9dc2d41",
    "user_id": "user-001",
    "channel": "console"
  }'
```

### 响应头

新建运行时，响应通常包含：

| Header | 说明 |
| --- | --- |
| `Content-Type` | `text/event-stream`。 |
| `Cache-Control` | `no-cache`。 |
| `Connection` | `keep-alive`。 |
| `X-Accel-Buffering` | `no`，避免 Nginx 缓冲 SSE。 |
| `X-Swe-Msgid` | 本轮用户问题的消息 ID，仅新建运行返回；不是 `chat_id`。 |
| `X-Swe-Sessionid` | 服务端解析出的逻辑 `session_id`，仅新建运行返回。 |
| `X-Tenant-Id-Resolved` | 中间件解析后的租户 ID，配置启用时可能返回。 |
| `X-Scope-Id-Resolved` | 中间件解析后的运行时 scope ID，配置启用时可能返回。 |

`chat_id` 是由服务端创建的 ChatSpec UUID。此接口不是 JSON 创建接口，不会把 chat 元数据作为单独响应体返回；如需按 `chat_id` 读取历史，使用聊天列表/详情能力取得后端 ChatSpec ID，或从业务侧保存已知的 chat ID。

### SSE 事件

服务端发送的每个业务事件都是 `data: <JSON>`，没有依赖 `event:` 字段，客户端应按 JSON 的 `object` 或顶层字段区分事件。

#### 1. 心跳注释帧

空闲期间大约每 15 秒发送一次，用于保持反向代理连接，不是 JSON 业务事件：

```text
: keep-alive

```

#### 2. 标题更新事件

首次响应前如果异步标题生成完成，可能收到：

```text
data: {"object":"session_title_updated","session_id":"session-user-001","session_title":"本周销售数据总结"}

```

字段：`object` 固定为 `session_title_updated`，`session_id` 为逻辑会话 ID，`session_title` 为新标题。

#### 3. 运行响应事件

典型生命周期是 `created`、`in_progress`、`completed`；也可能是 `failed` 或 `canceled`。示例：

```text
data: {"object":"response","id":"response-001","status":"in_progress","created_at":1776384000000,"output":[]}

data: {"object":"message","id":"message-001","type":"message","role":"assistant","status":"completed","content":[{"object":"content","type":"text","status":"completed","text":"本周销售额较上周增长 12%。"}],"metadata":{}}

data: {"object":"response","id":"response-001","status":"completed","created_at":1776384000000,"completed_at":1776384004200,"output":[{"object":"message","id":"message-001","type":"message","role":"assistant","status":"completed","content":[{"object":"content","type":"text","status":"completed","text":"本周销售额较上周增长 12%。"}]}]}

```

`response` 顶层字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `object` | `string` | 通常为 `response`。 |
| `id` | `string` | 本轮运行响应 ID。 |
| `status` | `string` | `created`、`in_progress`、`completed`、`canceled`、`failed`、`rejected` 或运行时扩展状态。 |
| `created_at` | `integer` | 创建时间，Unix 毫秒时间戳。 |
| `completed_at` | `integer` | 完成时间，Unix 毫秒时间戳；未完成时可能没有。 |
| `output` | `array` | 当前响应中的消息列表；中间帧可能为空，终态帧也可能只更新状态。 |
| `usage` | `object` | 可选的 token/模型用量信息。 |
| `error` | `object` | 失败信息，通常包含 `code` 和 `message`。 |
| `session_id` | `string` | 运行时可能返回的会话 ID。 |
| `trace_id` | `string` | 链路追踪 ID，可能由 `X-B3-Traceid` 补充。 |

`message` 字段通常包含 `id`、`object`、`type`、`role`、`status`、`content`、`code`、`message`、`usage`、`metadata`。其中 `content` 是多模态内容块数组，常用文本块为：

```json
{
  "object": "content",
  "type": "text",
  "status": "completed",
  "text": "回答内容"
}
```

#### 4. 对话压缩事件

执行压缩后可能发送一个不含完整消息列表的边界事件：

```text
data: {"object":"conversation_compacted","chat_id":"2d5f8fb3-6b17-4c77-b5a1-1e03f9dc2d41","boundary":{"id":"boundary-001","archived_message_count":24,"first_message_id":"msg-001","last_message_id":"msg-024","created_at":"2026-08-17T08:00:00+00:00","first_timestamp":"2026-08-17T07:30:00+00:00","last_timestamp":"2026-08-17T07:59:00+00:00"}}

```

`boundary` 的字段与历史接口响应中的 `boundaries[]` 相同。

#### 5. 工具实时输出帧

允许的工具执行期间可能收到：

```text
data: {"object":"tool_output_frame","tool_call_id":"call-001","tool_name":"execute_shell_command","sequence":1,"source":"stdout","text":"total 24\n","truncated":false,"budget_bytes":65536}

```

`source` 可能为 `stdout`、`stderr` 或 `message`。实时工具输出可能因行数或字节预算被截断，客户端应检查 `truncated`。

#### 6. 流内错误帧

生产者发生内部异常时，流中可能收到：

```text
data: {"error":"internal server error"}

```

这类错误不一定改变已建立连接的 HTTP 状态码，客户端必须同时处理 HTTP 错误和 SSE 内的错误 JSON。

### HTTP 错误

| 状态码 | 典型原因 | 示例响应 |
| --- | --- | --- |
| `400` | 缺少/非法 `X-Source-Id`，或请求字段无法提取。 | `{ "detail": "X-Source-Id header is required" }` |
| `403` | 请求体 `user_id` 与认证用户不一致，或 agent 不一致。 | `{ "detail": "Console sender does not match authenticated user" }` |
| `404` | `reconnect=true` 时没有可连接的运行。 | `{ "detail": "No running chat for this session" }` |
| `422` | JSON 或 AgentRequest 校验失败。 | FastAPI 标准校验错误。 |
| `503` | 当前 workspace 没有 Console channel。 | `{ "detail": "Channel Console not found" }` |

---

## 2. 获取压缩归档历史

### 基本信息

```http
GET /api/chats/{chat_id}/history
```

该接口只读取已经从在线 memory 压缩归档的消息，不等同于 `GET /api/chats/{chat_id}` 返回的当前在线会话状态。响应消息按时间线正序返回；分页方向是从最新归档消息向更早消息翻页。

### 路径参数

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chat_id` | `string` | 是 | 后端 `ChatSpec.id`，必须是规范格式 UUID。它不是逻辑 `session_id`。 |

### 查询参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `limit` | `integer` | 否 | `50` | 每页消息数，范围 `1` 到 `50`。 |
| `before` | `string` | 否 | 无 | 不透明游标。把上一页响应的 `next_cursor` 原样传入，获取更早的一页。不要自行解码、拼接或修改。 |

### 首页请求示例

```bash
curl "${BASE_URL}/api/chats/2d5f8fb3-6b17-4c77-b5a1-1e03f9dc2d41/history?limit=2" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "X-Tenant-Id: tenant-a" \
  -H "X-User-Id: user-001" \
  -H "X-Source-Id: portal"
```

### 分页请求示例

```bash
curl "${BASE_URL}/api/chats/2d5f8fb3-6b17-4c77-b5a1-1e03f9dc2d41/history?limit=2&before=${NEXT_CURSOR}" \
  -H "X-Tenant-Id: tenant-a" \
  -H "X-User-Id: user-001" \
  -H "X-Source-Id: portal"
```

`next_cursor` 是与当前 `chat_id` 绑定并带签名的游标；把它用于其他 chat 或修改内容会返回 `422`。

### 成功响应

HTTP 状态码为 `200`，响应头为 `Content-Type: application/json`。响应模型为 `ChatArchivePage`：

```json
{
  "messages": [
    {
      "sequence_number": null,
      "object": "message",
      "status": "completed",
      "error": null,
      "id": "msg-024",
      "type": "message",
      "role": "assistant",
      "content": [
        {
          "sequence_number": null,
          "object": "content",
          "status": "completed",
          "error": null,
          "type": "text",
          "index": null,
          "delta": false,
          "msg_id": null,
          "text": "本周销售额较上周增长 12%。"
        }
      ],
      "code": null,
      "message": null,
      "usage": null,
      "metadata": {
        "original_id": "msg-024",
        "original_name": "assistant",
        "metadata": {}
      },
      "timestamp": "2026-08-17T07:59:00+00:00"
    }
  ],
  "boundaries": [
    {
      "id": "boundary-001",
      "archived_message_count": 24,
      "first_message_id": "msg-001",
      "last_message_id": "msg-024",
      "created_at": "2026-08-17T08:00:00+00:00",
      "first_timestamp": "2026-08-17T07:30:00+00:00",
      "last_timestamp": "2026-08-17T07:59:00+00:00"
    }
  ],
  "has_more": true,
  "next_cursor": "eyJjaGF0X2lkIjoi..."
}
```

### 响应字段

#### 顶层字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `messages` | `array` | 当前页归档消息，按时间线正序排列。 |
| `boundaries` | `array` | 当前页涉及的压缩边界；只有该边界的最后一条消息出现在当前页时才会包含对应边界。 |
| `has_more` | `boolean` | 是否还有更早的归档消息。 |
| `next_cursor` | `string|null` | 下一页游标；`has_more=false` 时为 `null`。 |

#### `messages[]` 字段

消息对象沿用 AgentScope Runtime `Message`，常用字段如下：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string` | 当前消息 ID。 |
| `object` | `string` | 通常为 `message`。 |
| `type` | `string` | 消息类型。 |
| `role` | `string|null` | `user`、`assistant`、`system` 或 `tool`。 |
| `status` | `string` | 消息状态。 |
| `content` | `array|null` | 文本、图片、文件等内容块。 |
| `code` | `string|null` | 错误或特殊消息代码。 |
| `message` | `string|null` | 错误/状态文字。 |
| `usage` | `object|null` | 可选用量信息。 |
| `metadata` | `object|null` | 元数据；归档消息通常包含 `original_id`、`original_name` 和原始 metadata。 |
| `timestamp` | `string|null` | 后端规范化的消息时间戳。 |

历史接口在展示前会过滤隐藏上下文内容，但不会跨 chat 读取归档；`metadata.original_id` 用于保留归档消息对应的原始消息 ID。

#### `boundaries[]` 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `string` | 压缩批次 ID。 |
| `archived_message_count` | `integer` | 该批次归档的消息数量。 |
| `first_message_id` | `string` | 批次首条消息 ID。 |
| `last_message_id` | `string` | 批次末条消息 ID。 |
| `created_at` | `string` | 边界创建时间。 |
| `first_timestamp` | `string|null` | 首条消息时间。 |
| `last_timestamp` | `string|null` | 末条消息时间。 |

### 无归档数据

如果 `chat_id` 存在但尚未产生压缩归档，接口仍返回 `200`：

```json
{
  "messages": [],
  "boundaries": [],
  "has_more": false,
  "next_cursor": null
}
```

### HTTP 错误

| 状态码 | 典型原因 | 示例响应 |
| --- | --- | --- |
| `400` | 身份头缺失/非法，具体取决于中间件配置。 | `{ "detail": "X-Source-Id header is required" }` |
| `404` | `chat_id` 对应的 ChatSpec 不存在。 | `{ "detail": "Chat not found: 2d5f8fb3-..." }` |
| `422` | `chat_id` 不是规范 UUID、`limit` 不在 `1..50`，或 `before` 无效/被篡改。 | `{ "detail": "Invalid conversation archive cursor" }` |

### 分页建议

1. 首次请求不传 `before`。
2. 如果 `has_more=true`，读取 `next_cursor`。
3. 下一次请求将 `next_cursor` URL 编码后作为 `before` 传回，并保持同一个 `chat_id`。
4. 当 `has_more=false` 时停止，不要继续请求 `before=null`。

---

## 3. 两个接口的关系

| 场景 | 使用接口 | 关键 ID |
| --- | --- | --- |
| 发送新问题、接收实时回答 | `POST /api/console/chat` | `session_id` 是逻辑会话；服务端内部运行键是 `ChatSpec.id`。 |
| 客户端断线后接回正在运行的回答 | `POST /api/console/chat` + `reconnect=true` | `session_id` 可传 `chat_id` 或逻辑 session ID。 |
| 读取压缩前的当前在线历史 | `GET /api/chats/{chat_id}` | 使用后端 `ChatSpec.id`。 |
| 读取已经归档的较早历史 | `GET /api/chats/{chat_id}/history` | 使用同一个后端 `ChatSpec.id` 和 `next_cursor`。 |

其中 `X-Swe-Msgid` 是本轮用户问题消息 ID，不能当作 `chat_id` 使用；`next_cursor` 也只能在它所属的 chat 上继续分页。
