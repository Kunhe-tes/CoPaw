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
- 在 `stdout` 只返回 `{}`；任何 `Stop` handler 输出都会被运行时静默丢弃

## 目录内容

1. `hooks/hooks.json`
2. `scripts/finalize_stop_summary.py`
3. 当前 `SKILL.md`

## 关键说明

- `Stop` 不会像 `BeforeStop` 那样自动续跑，也不是结束门禁
- 它适合最终审计、埋点和不影响会话的外部通知
- `block` / `deny` / `stop` / `continue: false`、`additionalContext` 以及 `failPolicy: block` 的控制效果都不会生效，也不会发出警告
- 需要拦住结束并让模型继续完成任务时，使用 `BeforeStop` 并返回 `block`
