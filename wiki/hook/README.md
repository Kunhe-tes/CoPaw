# Hook 样例索引

本文档汇总 `docs/hook/hook-runtime.md` 对应的可运行样例。所有样例都只放在
`docs/hook/` 下，目录结构统一遵循 skill 级 hook 的真实布局：

```text
<demo>/
├── SKILL.md
├── hooks/
│   └── hooks.json
└── scripts/
    └── ...
```

这些样例都按当前实现校对过，重点覆盖两件事：

1. 7 个 hook 事件类型全部有例子
2. 3 类 handler 类型 `command` / `http` / `prompt` 全部有例子

## 覆盖矩阵

| 事件 | 推荐样例 | handler 类型 | 说明 |
| --- | --- | --- | --- |
| `SessionStart` | [session-start-prompt-demo](session-start-prompt-demo/SKILL.md) | `prompt` | 演示会话启动前的入口策略判断 |
| `UserPromptSubmit` | [user-prompt-submit-command-demo](user-prompt-submit-command-demo/SKILL.md) | `command` | 演示用户输入预检查、补充上下文与会话标题 |
| `PreToolUse` | [pre-tool-use-command-demo](pre-tool-use-command-demo/SKILL.md) | `command` | 演示工具执行前的 deny / ask / updatedInput |
| `PostToolUse` | [hook-http-demo](hook-http-demo/SKILL.md) | `http` | 演示成功工具结果通过 HTTP 发送到本地接收器 |
| `PostToolUseFailure` | [mcp-failure-fallback-demo](mcp-failure-fallback-demo/SKILL.md) | `command` | 演示失败后注入统一兜底上下文 |
| `BeforeStop` | [before-stop-prompt-demo](before-stop-prompt-demo/SKILL.md) | `prompt` | 演示结束前 gate，只允许 `allow` / `block` |
| `Stop` | [stop-command-summary-demo](stop-command-summary-demo/SKILL.md) | `command` | 演示真正结束前补充收尾上下文或停止说明 |

## Handler 覆盖

| handler 类型 | 对应样例 | 关键点 |
| --- | --- | --- |
| `command` | `user-prompt-submit-command-demo`、`pre-tool-use-command-demo`、`mcp-failure-fallback-demo`、`stop-command-summary-demo` | skill 级必须使用 `argv`，脚本必须放在 `scripts/` 下 |
| `http` | `hook-http-demo` | skill 级不能写明文 `headers` 与 `allowedEnvVars` |
| `prompt` | `session-start-prompt-demo`、`before-stop-prompt-demo` | 只能挂到 `SessionStart`、`UserPromptSubmit`、`PreToolUse`、`BeforeStop`、`Stop` |

## 使用方式

1. 先阅读 [hook-runtime.md](hook-runtime.md)，确认事件时机与返回语义。
2. 再挑一个最接近你场景的 demo，直接复用它的目录布局和字段写法。
3. 如果要把样例迁移到真实 skill，重点检查：
   - `hooks/hooks.json` 的事件名和 `matcher.tools`
   - `scripts/` 脚本路径是否仍在 skill 根目录内
   - `http` handler 是否误写了 skill 级不允许的字段
   - `BeforeStop` 是否只返回 `allow` / `block`

## 额外说明

- `hook-http-demo` 保留了原有目录名，但它覆盖的事件就是 `PostToolUse`。
- `mcp-failure-fallback-demo` 除了主要展示 `PostToolUseFailure`，还额外附带了一个
  `BeforeStop` prompt gate，方便一起观察“失败兜底 + 结束前一致性校验”的组合写法。
- prompt 样例目录里的 `scripts/*.py` 不是 hook runtime 自动执行的 handler，而是用于
  生成最小 `HookContext` 样本，方便你手工调试 prompt 规则。
