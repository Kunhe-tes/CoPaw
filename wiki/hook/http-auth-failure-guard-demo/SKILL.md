---
name: http-auth-failure-guard-demo
description: "Use this skill when you need a concrete skill-owned hook example that detects protected HTTP tool responses with 401 or 403 status codes after a tool call, then blocks the current event and injects context telling the model the task has already failed. Trigger when demonstrating PostToolUse/PostToolUseFailure guards for API authentication or authorization failures."
license: Proprietary. LICENSE.txt has complete terms
metadata:
  builtin_skill_version: "1.0"
---

# HTTP Auth Failure Guard Demo

这是一个最小样例，用于演示：指定工具接口调用后，如果工具结果或失败信息里出现
HTTP `401` / `403`，hook 会返回两类效果：

1. `decision: "block"`：阻断当前 hook 事件的继续推进
2. `additionalContext`：向后续推理注入提示，提醒模型此次任务已经失败，不要继续调用同一接口或基于失败结果推进

## 覆盖点

- 主样例事件：`PostToolUse`
- 失败样例事件：`PostToolUseFailure`
- handler 类型：`command`

## 目录内容

1. `hooks/hooks.json`
2. `scripts/http_auth_failure_guard.py`
3. 当前 `SKILL.md`

## 行为说明

- `hooks/hooks.json` 默认只匹配工具名 `call_protected_api`，迁移到真实场景时应改成你的实际工具名。
- 脚本会从 `tool_response` 的 `status_code`、`status`、`statusCode`、`code` 字段，以及 `error` 文本里识别 HTTP `401` / `403`。
- 命中 `401` / `403` 时返回 `block` 和 `additionalContext`。
- 未命中鉴权失败状态码时返回空对象，不影响其他 hook 或原始工具结果。

## 关键限制

- `PostToolUse` 发生在工具已经返回之后，无法撤销已经发生的外部请求；这里的阻断主要用于阻止 Agent 继续基于失败结果推进。
- `PostToolUseFailure` 不会吞掉原始工具失败；它适合补充诊断上下文，让模型不要继续无效重试。
- 如果你希望在调用前就阻止某个工具，应改用 `PreToolUse`。
