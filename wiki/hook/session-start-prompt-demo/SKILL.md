---
name: session-start-prompt-demo
description: "Use this skill when you need a concrete SessionStart prompt hook example that gates agent startup based on HookContext fields such as channel, source, cwd, and tenant metadata. Trigger when the goal is to demonstrate a skill-owned prompt hook, a minimal hooks/hooks.json for SessionStart, or a payload helper script for local debugging."
license: Proprietary. LICENSE.txt has complete terms
metadata:
  builtin_skill_version: "1.0"
---

# SessionStart Prompt Demo

这个样例演示 skill 级 `SessionStart + prompt handler` 的最小完整目录。

## 覆盖点

- 事件：`SessionStart`
- handler 类型：`prompt`
- 目的：在 Agent 正式进入主流程前，先基于 `HookContext` 做入口策略判断

## 目录内容

1. `hooks/hooks.json`
2. `scripts/build_session_start_payload.py`
3. 当前 `SKILL.md`

## 关键说明

- `prompt` handler 本身不会执行本地脚本；它直接调用当前租户激活模型。
- `scripts/build_session_start_payload.py` 只是调试辅助脚本，用来生成一份最小
  `HookContext` 样本，方便你先观察 prompt 会拿到什么字段。
- 这个 demo 的 prompt 规则重点检查：
  - `channel` 是否为空
  - `cwd` / `workspace_dir` 是否存在
  - `source` 是否属于预期启动来源

## 调试脚本

在 demo 目录下运行：

```bash
python scripts/build_session_start_payload.py
```

脚本会打印一个最小 `SessionStart` payload，便于你手动对照
`docs/hook/hook-runtime.md` 里的字段说明。
