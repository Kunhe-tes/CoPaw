---
name: mcp-failure-fallback-demo
description: "Use this skill when you need a concrete PostToolUseFailure command hook example for MCP-style failures, plus an optional BeforeStop prompt gate that checks whether the final reply overstates failed-tool data. Trigger when demonstrating failure fallback additionalContext or a combined failure-and-final-check hook layout."
license: Proprietary. LICENSE.txt has complete terms
metadata:
  builtin_skill_version: "1.0"
---

# MCP Failure Fallback Demo

这是一个最小样例，用于演示两类常见组合：

1. `PostToolUseFailure + command`：MCP 或其他工具失败后注入统一兜底上下文
2. `BeforeStop + prompt`：在回复结束前再做一次一致性检查

## 覆盖点

- 主样例事件：`PostToolUseFailure`
- 附带事件：`BeforeStop`
- handler 类型：`command` + `prompt`

## 目录内容

1. `hooks/hooks.json`
2. `scripts/mcp_failure_fallback.py`
3. 当前 `SKILL.md`

## 行为说明

- 当 `error` 为空或缺失时，失败脚本返回空对象，不注入额外上下文。
- 当 `error` 非空时，脚本返回一条统一 `additionalContext`，提示模型不要把失败工具结果当成已验证事实。
- `BeforeStop` prompt handler 会基于 `assistant_response` 与 HookContext JSON 做收尾前检查；如果候选回复把失败调用说成“已确认成功”，就应该返回 `block`。

## 关键限制

- 当前 Hook Runtime 的 `prompt` handler 拿到的是 HookContext JSON，不是完整 transcript。
- 因此这个 demo 的结束前检查只能做“基于当前上下文的近似一致性校验”，不能代替完整会话审计。
