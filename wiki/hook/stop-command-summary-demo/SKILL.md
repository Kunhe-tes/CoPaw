---
name: stop-command-summary-demo
description: "Use this skill when you need a concrete Stop command hook example that emits final audit or telemetry records without affecting the end-of-turn path. Trigger when demonstrating end-of-turn observability."
license: Proprietary. LICENSE.txt has complete terms
metadata:
  builtin_skill_version: "1.0"
  swe:
    uses_tools:
      - execute_shell_command
---

# Stop Command Summary Demo

这个样例演示 skill 级 `Stop + command handler`。

## 覆盖点

- 事件：`Stop`
- handler 类型：`command`
- 目的：在当前轮真正结束时发送外部审计或埋点记录，不影响会话主流程

## 这个 demo 会做什么

- 从 payload 读取最后一次相关工具和候选回复中的复核标记
- 将结构化审计记录写到 `stderr`，便于日志采集器或外部观测系统接收
- 在 `stdout` 返回 `{"decision":"allow","reason":"summary recorded"}`，在记录完成后批准候选回复

## 目录内容

1. `hooks/hooks.json`
2. `scripts/finalize_stop_summary.py`
3. 当前 `SKILL.md`

## 关键说明

- `Stop` 是结束门禁；handler 可先写入审计、埋点或外部通知，再用 `allow` 批准候选回复
- `block` 会让 Agent 在同一请求内继续尝试；`deny`、`stop`、`continue: false`、`additionalContext` 等输出不受支持
- `failPolicy: block` 的执行失败会以未完成结束当前请求，不会自动续跑
