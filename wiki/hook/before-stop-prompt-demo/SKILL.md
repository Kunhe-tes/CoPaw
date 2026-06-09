---
name: before-stop-prompt-demo
description: "Use this skill when you need a concrete BeforeStop prompt hook example that blocks completion until the assistant response satisfies a release or verification gate. Trigger when demonstrating completion gates before a turn is allowed to finish."
license: Proprietary. LICENSE.txt has complete terms
metadata:
  builtin_skill_version: "1.0"
---

# BeforeStop Prompt Demo

这个样例演示 skill 级 `BeforeStop + prompt handler`。

## 覆盖点

- 事件：`BeforeStop`
- handler 类型：`prompt`
- 目的：在候选回复已经生成后，决定“现在能不能结束”

## 关键说明

- `BeforeStop` 上的 prompt 只能返回 `allow` 或 `block`
- 不能返回 `additionalContext`、`updatedInput`、`sessionTitle`
- 返回 `block` 后，系统会在同一次请求里继续尝试完成任务，而不是立刻结束

## 目录内容

1. `hooks/hooks.json`
2. `scripts/build_before_stop_payload.py`
3. 当前 `SKILL.md`

## 调试脚本

```bash
python scripts/build_before_stop_payload.py
```

脚本会输出一份包含 `assistant_response` 的最小 HookContext，
便于你先设计 prompt 规则，再迁移到真实策略。
