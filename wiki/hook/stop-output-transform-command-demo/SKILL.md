---
name: stop-output-transform-command-demo
description: "Use this skill when you need a concrete Stop command output transformer that normalizes final assistant text before it is delivered."
license: Proprietary. LICENSE.txt has complete terms
metadata:
  builtin_skill_version: "1.0"
  swe:
    uses_tools:
      - execute_shell_command
---

# Stop Output Transform Command Demo

这个样例演示 skill 级 `Stop + command` 输出变换器。它在最终文本交付前移除
`DRAFT:` 前缀和首尾空白；真实场景可以替换为统一落款、格式化或受控的文本脱敏。

## 覆盖点

- 事件：`Stop`
- handler 类型：`command`
- 配置：`outputTransform: true`
- 目的：以 `replacementText` 完整替换候选 assistant 文本，再交给普通 Stop handler 校验

## 这个 demo 会做什么

1. runtime 暂存可提取的 assistant 文本，并把当前文本放在 HookContext 的
   `assistant_response`。
2. `scripts/normalize_final_output.py` 从 stdin 读取 HookContext，输出严格的
   `allow` 决策；只有文本实际变化且非空时才输出：

   ```json
   {"decision":"allow","reason":"final output normalized","hookSpecificOutput":{"replacementText":"final text"}}
   ```

3. runtime 用 `replacementText` 替换候选文本。当前配置的 `failPolicy: block` 表示
   脚本失败或超时会以未完成结束本轮，不会投递原候选文本。

## 使用限制

- `outputTransform` 只能配置在 `Stop`，且不能与 `once: true` 一起使用。
- 变换器只能返回 `decision: "allow"`；`block`、`deny`、`stop`、
  `additionalContext`、`updatedInput` 和权限决策均不受支持。
- `replacementText` 必须是非空字符串，且只能放在 `hookSpecificOutput` 中。省略它
  表示保留当前文本。
- 多个变换器会按“租户 → Agent Profile → 已激活 Skill（按 `skill_name` 排序）”串行运行；
  后一个读取前一个的替换结果。普通 Stop handler 在全部变换完成后并发运行。
- 总变换时间受 Agent Profile 的
  `running.hook_runtime.max_stop_transform_seconds` 控制，默认 30 秒。

## 目录内容

1. `hooks/hooks.json`
2. `scripts/normalize_final_output.py`
3. 当前 `SKILL.md`

## 本地调试

在 demo 根目录运行：

```bash
printf '{"hook_event_name":"Stop","assistant_response":"  DRAFT: final text  "}' | python scripts/normalize_final_output.py
```

预期 stdout 为单行 JSON，包含 `decision: "allow"` 和
`hookSpecificOutput.replacementText: "final text"`。

若输入已经是最终文本，脚本仍返回 `allow`，但省略 `hookSpecificOutput`，让 runtime
保留原文本。
