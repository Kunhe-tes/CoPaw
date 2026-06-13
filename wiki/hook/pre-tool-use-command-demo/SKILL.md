---
name: pre-tool-use-command-demo
description: "Use this skill when you need a concrete PreToolUse command hook example that inspects tool_name and tool_input, then returns deny, ask, allow, or updatedInput. Trigger when demonstrating skill-owned approval or rewrite policies before a tool actually runs."
license: Proprietary. LICENSE.txt has complete terms
metadata:
  builtin_skill_version: "1.0"
  swe:
    uses_tools:
      - execute_shell_command
---

# PreToolUse Command Demo

这个样例演示 skill 级 `PreToolUse + command handler`。

## 覆盖点

- 事件：`PreToolUse`
- handler 类型：`command`
- 目的：在工具真正执行前做许可判断、人工审批或输入改写

## 这个 demo 的策略

- 仅对 `execute_shell_command` 生效
- 命令包含 `rm -rf` 时返回 `deny`
- 命令包含 `git push` 时返回 `ask`
- 命令是 `ls` 且未带参数时，返回 `updatedInput`

## 目录内容

1. `hooks/hooks.json`
2. `scripts/check_shell_command.py`
3. 当前 `SKILL.md`

## 关键说明

- 这个脚本故意同时展示 `permissionDecision`、`updatedInput` 这几类
  `PreToolUse` 常见返回值。
- `updatedInput` 会整体替换工具输入对象，不是局部 merge。
- 如果你要接审批 UI，重点看 `permissionDecision: "ask"` 的分支。
