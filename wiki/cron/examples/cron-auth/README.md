# Cron 授权状态示例

Agent 定时任务在无人值守执行时，可能需要复用用户态 cookie / auth token。`POST /api/auth/cron-auth` 会把当前 workspace 的 cron 授权状态写入 `cron_auth.json`。

返回 [Cron 示例索引](../README.md)。

## 配置授权状态

不要把真实 cookie 写进仓库或聊天记录。下面的 `access_token` 只是占位：

```powershell
$baseUrl = "http://127.0.0.1:8088"

$body = @{
  cookie = "access_token=<access-token-from-browser>; other_cookie=value"
} | ConvertTo-Json

curl.exe -X POST "$baseUrl/api/auth/cron-auth" `
  -H "Content-Type: application/json" `
  -H "X-Tenant-Id: tenant-a" `
  -H "X-Source-Id: RMASSIST" `
  -H "X-Agent-Id: default" `
  -d $body
```

返回示例：

```json
{
  "configured": true,
  "user_info_status": "refreshed",
  "user_info_expires_at": "2026-06-09T12:00:00Z",
  "auth_token_expires_at": null,
  "has_auth_token": false
}
```

## 执行时怎么用

`CronExecutor` 执行 Agent 任务时会读取 `CronAuthState`：

1. 从 `cron_auth.json` 读取 `user_info`、`auth_token`、`cookie_header`。
2. 如果 `auth_token` 可复用，就把它合并回 cookie。
3. 如果不可复用，就通过 `user_info` 重新签发。
4. 把结果写入 Agent request 的认证上下文。

因此排查“定时任务里没有登录态”时，先确认：

- 创建任务和写 cron auth 的 `X-Tenant-Id`、`X-Source-Id`、`X-Agent-Id` 是否一致。
- `cookie` 里是否包含可解析的 `access_token`。
- `cron_auth.json` 是否写在当前 runtime workspace 下，而不是默认租户下。

## 清理非目标 source 的授权

清理接口支持 dry run：

```powershell
$body = @{
  keep_source_id = "RMASSIST"
  force_delete_tenant_ids = @()
  dry_run = $true
} | ConvertTo-Json

curl.exe -X POST "$baseUrl/api/auth/cron-auth/cleanup" `
  -H "Content-Type: application/json" `
  -d $body
```

确认结果后再把 `dry_run` 改成 `false`。这个接口会删除非保留 source 的 cron 授权状态目录，排查前不要直接在生产环境执行非 dry-run。
