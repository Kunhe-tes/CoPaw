# CLI 创建每周固定文本任务

这个示例演示用 `swe cron` 管理一个 `task_type=text` 的固定文本任务。CLI 会自动给 `--base-url` 补 `/api`，所以这里不要写成 `http://127.0.0.1:8088/api`。

返回 [Cron 示例索引](../README.md)。

## 创建固定文本任务

```powershell
venv\Scripts\python.exe -m swe cron create `
  --base-url http://127.0.0.1:8088 `
  --agent-id default `
  --tenant-id tenant-a `
  --source-id RMASSIST `
  --type text `
  --name "每周例会提醒" `
  --cron "0 9 * * mon" `
  --timezone Asia/Shanghai `
  --channel zhaohu `
  --target-user user-001 `
  --target-session session-cron-demo `
  --text "今天 09:30 例会，请提前准备上周进展、风险和本周计划。" `
  --mode final
```

这会构造一个 `CronJobSpec`：

- `task_type` 是 `text`
- `text` 是最终投递内容
- 不会写入 `model_slot`
- 不会调用 Agent runner，只会通过 `channel_manager.send_text()` 投递固定文本

## 查询任务列表

```powershell
venv\Scripts\python.exe -m swe cron list `
  --base-url http://127.0.0.1:8088 `
  --agent-id default `
  --tenant-id tenant-a `
  --source-id RMASSIST
```

## 更新执行时间和文本

```powershell
venv\Scripts\python.exe -m swe cron update <job-id> `
  --base-url http://127.0.0.1:8088 `
  --agent-id default `
  --tenant-id tenant-a `
  --source-id RMASSIST `
  --cron "30 8 * * mon" `
  --text "今天 09:30 例会，请 08:30 前提交上周进展和本周计划。"
```

`update` 会先读取现有任务，再合并你传入的字段，最后 `PUT /cron/jobs/{job_id}` 替换任务。

## 手动运行、暂停和恢复

```powershell
venv\Scripts\python.exe -m swe cron run <job-id> `
  --base-url http://127.0.0.1:8088 `
  --agent-id default `
  --tenant-id tenant-a `
  --source-id RMASSIST

venv\Scripts\python.exe -m swe cron pause <job-id> `
  --base-url http://127.0.0.1:8088 `
  --agent-id default `
  --tenant-id tenant-a `
  --source-id RMASSIST

venv\Scripts\python.exe -m swe cron resume <job-id> `
  --base-url http://127.0.0.1:8088 `
  --agent-id default `
  --tenant-id tenant-a `
  --source-id RMASSIST
```

`run` 是立即执行一次，不会改变 cron 表达式；`pause` / `resume` 会更新 SWE 本地任务状态，并同步外部调度平台启停状态。
