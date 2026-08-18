# 安全、审批与治理边界

本文档整理与执行安全、审批流程、认证和路径边界相关的模块。

## 工具治理主链路

| 区域 | 关键文件 | 说明 |
|------|----------|------|
| Agent 接入层 | `src/swe/agents/tool_guard_mixin.py` | 在 Agent 工具调用前插入治理逻辑 |
| 审批模型 | `src/swe/security/tool_guard/models.py` | 审批与守卫相关结构 |
| 审批入口 | `src/swe/security/tool_guard/approval.py` | 审批流程入口 |
| 守卫引擎 | `src/swe/security/tool_guard/engine.py` | 规则执行与决策 |
| Guardian | `src/swe/security/tool_guard/guardians/file_guardian.py`, `src/swe/security/tool_guard/guardians/rule_guardian.py` | 文件边界和规则守卫 |
| 规则集 | `src/swe/security/tool_guard/rules/dangerous_shell_commands.yaml` | 危险命令规则 |
| 工具函数 | `src/swe/security/tool_guard/utils.py` | 守卫辅助逻辑 |

## 其他安全边界

| 文件 | 说明 |
|------|------|
| `src/swe/security/tenant_path_boundary.py` | 租户路径越界防护 |
| `src/swe/security/process_limits.py` | 租户级子进程 CPU 时间/内存上限解析与 Unix rlimit 封装 |
| `src/swe/security/skill_scanner/scanner.py` | 技能扫描器 |
| `src/swe/security/skill_scanner/scan_policy.py` | 技能扫描策略 |
| `src/swe/security/skill_scanner/models.py` | 技能扫描结果模型 |
| `src/swe/security/skill_scanner/analyzers/package_analyzer.py` | Skill 包体安全检测，覆盖符号链接、二进制、隐藏可执行文件、嵌套压缩包路径穿越等入口风险 |
| `src/swe/security/skill_scanner/analyzers/ast_behavior_analyzer.py` | Python AST 行为检测，覆盖动态执行、shell 执行等高风险代码行为 |
| `src/swe/agents/tools/shell.py` | tenant-scoped shell 子进程的路径边界、超时与 process-limit 执行点 |
| `src/swe/app/mcp/stdio_launcher.py` | tenant-aware MCP `stdio` launcher，在 `exec` 目标命令前设置 rlimit |
| `src/swe/app/auth.py` | 应用认证中间件/逻辑 |
| `src/swe/app/routers/auth.py` | 认证路由 |
| `src/swe/app/approvals/service.py` | 审批服务 |

## 治理范围

- Shell、文件读写、浏览器等高风险工具需进入 Tool Guard 决策
- 技能文件进入系统前可经过扫描策略校验
- Skill 扫描采用分层策略：包体与上下文先建立可信输入，静态规则和 AST 分析只产出证据，block/warn/off 与后续准入策略负责最终决策
- 租户目录与密钥目录必须受请求上下文和路径边界共同限制
- `security.process_limits` 仅覆盖 tenant-scoped builtin shell 与 MCP `stdio` 子进程，不扩展到 local model、tunnel、CLI 维护任务等平台托管进程
- 首版 process-limit 依赖 Unix `resource.setrlimit(...)`，以 Linux/Unix 为主；不支持的平台会保留原有启动行为并输出显式诊断，而不是静默假装已生效
- `cpu_time_limit_seconds` 限制的是进程累计 CPU 时间，不等同于现有 shell `timeout` 的 wall-clock 超时；`sleep`/I/O 等低 CPU 命令仍主要由 wall-clock timeout 兜底
- API 请求受认证与租户中间件约束

## 关联功能域

- Agent 工具调用链: [agent-and-orchestration.md](agent-and-orchestration.md)
- 通道/API 接入面: [channels-and-access.md](channels-and-access.md)
