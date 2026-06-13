# Cron 示例索引

这里放的是可以复制改造的 cron 使用示例。所有示例都按当前 `v1.0.0` 代码核对过，重点覆盖真实接口字段、请求头、回调参数和排查入口。

示例里的占位值需要按你的环境替换：

| 占位值 | 含义 |
| --- | --- |
| `http://127.0.0.1:8088` | SWE API 地址；curl 示例使用完整 `/api/...` 路径 |
| `tenant-a` | 逻辑租户 ID，对应 `X-Tenant-Id` |
| `RMASSIST` | source ID，对应 `X-Source-Id` |
| `default` | Agent ID，对应 `X-Agent-Id` |
| `user-001` | 通道接收用户或任务创建用户 |
| `session-cron-demo` | 定时任务投递到的会话 ID |
| `<job-id>` | 创建任务后服务端返回的任务 ID |

## 覆盖矩阵

| 场景 | 示例 | 主要入口 |
| --- | --- | --- |
| 创建 Agent 定时任务 | [api-agent-daily](api-agent-daily/README.md) | `POST /api/cron/jobs` |
| 用 CLI 管固定文本任务 | [cli-text-weekly](cli-text-weekly/README.md) | `swe cron create/list/update/run` |
| 模拟外部调度平台回调 | [callback-jobparam](callback-jobparam/README.md) | `POST /api/internal/cron/callback` |
| 广播任务到多个租户 | [broadcast-to-tenants](broadcast-to-tenants/README.md) | `POST /api/cron/jobs/{job_id}/broadcast` |
| 配置 cron 授权状态 | [cron-auth](cron-auth/README.md) | `POST /api/auth/cron-auth` |
| 排查 Monitor 和通知 | [monitor-notification-debug](monitor-notification-debug/README.md) | `/monitor/cron/*` |

## 使用前先确认

- curl 示例直接访问 SWE HTTP API，所以路径写完整 `/api/...`。
- CLI 示例里的 `--base-url` 不需要写 `/api`；`src/swe/cli/http.py` 会自动补 `/api`。
- 创建任务时 `id` 字段仍需要出现在请求体里，但 `POST /api/cron/jobs` 会忽略客户端传入值并生成新的 UUID。
- `task_type=agent` 必须有 `request`；`task_type=text` 必须有 `text`。
- 如果指定 `model_slot`，provider 和 model 必须在当前 tenant 可用，否则 API 会返回 400。
- 示例不要直接提交真实 cookie、access token、客户 ID 或生产 tenant。

返回 [Cron 定时任务模块索引](../README.md)。
