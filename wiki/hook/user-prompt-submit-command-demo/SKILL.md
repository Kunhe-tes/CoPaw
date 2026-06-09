---
name: user-prompt-submit-command-demo
description: "Use this skill when you need a concrete UserPromptSubmit command hook example that inspects prompt text, injects additionalContext, and optionally sets a session title. Trigger when the task is to demonstrate a skill-owned command hook for user-input preflight checks."
license: Proprietary. LICENSE.txt has complete terms
metadata:
  builtin_skill_version: "1.0"
  swe:
    uses_tools:
      - execute_shell_command
---

# UserPromptSubmit Command Demo

这个样例演示 skill 级 `UserPromptSubmit + command handler`。

## 覆盖点

- 事件：`UserPromptSubmit`
- handler 类型：`command`
- 目的：在用户输入进入 Agent 前做轻量检查，并向本轮上下文注入说明

## 这个 demo 会做什么

- 当 `prompt` 为空时，返回空对象
- 当 `prompt` 含有明显的敏感导向词时，直接 `block`
- 普通输入场景下：
  - 生成一个简短 `sessionTitle`
  - 追加一条 `additionalContext`

## 目录内容

1. `hooks/hooks.json`
2. `scripts/check_user_prompt.py`
3. 当前 `SKILL.md`

## 运行要点

- skill 级 `command` handler 必须用 `argv`
- 脚本必须位于当前 skill 的 `scripts/` 目录
- stdout 只能输出最终 JSON；调试信息请写 stderr
