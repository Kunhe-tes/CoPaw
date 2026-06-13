---
name: stop-command-summary-demo
description: "Use this skill when you need a concrete Stop command hook example that appends final additionalContext or halts the end-of-turn path with continue:false. Trigger when demonstrating end-of-turn cleanup or final-stop annotations."
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
- 目的：在当前轮真正结束前补充收尾上下文，或给出明确停止原因

## 这个 demo 会做什么

- 正常情况下，返回一条 `additionalContext`，把收尾说明写入后续记忆
- 如果 `assistant_response` 包含 `WAIT_FOR_REVIEW` 这样的哨兵标记，
  则返回 `continue: false`，要求当前轮以“等待人工复核”为原因停止

## 目录内容

1. `hooks/hooks.json`
2. `scripts/finalize_stop_summary.py`
3. 当前 `SKILL.md`

## 关键说明

- `Stop` 不会像 `BeforeStop` 那样自动续跑
- 因此这个事件更适合做最终审计、落备注、追加收尾上下文
