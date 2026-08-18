# SubAgent 设计文档

## 0. 设计目标

本文档面向自研 Agent Runtime，目标是实现类似 Claude Code / Codex 的 SubAgent 能力，并为后续实现 **Plan Mode**、**Goal Mode**、并行代码分析、审查、测试验证等能力提供基础。

SubAgent 的核心价值不是“多开几个模型会话”，而是：

1. **隔离上下文**：避免主 Agent 被搜索结果、日志、文件内容、测试输出污染。
2. **分离职责**：主 Agent 负责目标、决策、汇总；SubAgent 负责局部事实发现、验证、审查。
3. **收窄权限**：让某些 Agent 天然只读、只能测试、只能审查，降低误操作风险。
4. **并行执行**：对代码库探索、PR 审查、日志分析、测试面分析等可并行任务提速。
5. **结构化返回**：SubAgent 不直接对用户输出最终答案，而是向主 Agent 返回可消费的结构化结果。

## 1. 核心结论

### 1.1 SubAgent 不是 prompt，而是运行时实体

SubAgent 应定义为：

```text
SubAgent =
  独立上下文窗口
  + 独立系统提示词
  + 独立工具集合
  + 独立权限策略
  + 可选独立模型
  + 可选独立工作区
  + 可选独立记忆
  + 结构化输入协议
  + 结构化输出协议
```

### 1.2 主 Agent 与 SubAgent 的边界

```text
Main Agent：
  负责理解用户目标、拆解任务、选择 SubAgent、汇总结果、做最终决策。

SubAgent：
  负责局部任务执行，例如代码搜索、模块分析、风险审查、测试面识别、日志归因。

Runtime：
  负责权限控制、工具拦截、预算、审计、并发、生命周期。
```

### 1.3 权限原则

最重要的安全规则：

```text
SubAgent 的权限只能比父级更窄，不能比父级更宽。
```

即：

```text
EffectivePermission =
  ParentSessionPermission
  ∩ SubAgentPermission
  ∩ RuntimePolicy
  ∩ WorkspacePolicy
```

## 2. 名词定义

| 名词 | 定义 |
|---|---|
| Main Agent | 面向用户的主控 Agent，负责意图理解、任务拆解、编排和最终回答 |
| SubAgent | 被主 Agent 委派的专用 Agent，拥有独立上下文和工具权限 |
| Delegation | 主 Agent 向 SubAgent 发起任务委派的动作 |
| DelegationSpec | 主 Agent 发送给 SubAgent 的结构化任务协议 |
| AgentResult | SubAgent 返回给主 Agent 的结构化结果 |
| Agent Registry | SubAgent 注册中心，保存可用 Agent 的定义 |
| Delegation Manager | 委派管理器，负责选择、启动、暂停、取消 SubAgent |
| Tool Gateway | 工具网关，负责工具可见性、权限检查和执行审计 |
| Permission Policy | 工具和操作权限策略 |
| Workspace Isolation | 工作区隔离策略，例如 shared workspace、sandbox、git worktree |
| Fresh SubAgent | 新建独立上下文，只接收委派任务摘要 |
| Fork SubAgent | 从主 Agent 当前上下文 fork 出来的分支 Agent |

## 3. 总体架构

```text
┌─────────────────────────────────────────────┐
│ User / CLI / IDE / Web UI                   │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│ Main Agent                                   │
│ - intent understanding                       │
│ - mode control: normal / plan / goal         │
│ - task decomposition                         │
│ - result synthesis                           │
└───────────────┬─────────────────────────────┘
                │ delegate_to_subagent
┌───────────────▼─────────────────────────────┐
│ Delegation Manager                           │
│ - agent selection                            │
│ - delegation spec construction               │
│ - lifecycle control                          │
│ - budget / concurrency control               │
└───────────────┬─────────────────────────────┘
                │
┌───────────────▼─────────────────────────────┐
│ Agent Registry                               │
│ - plan-researcher                            │
│ - code-reviewer                              │
│ - test-analyzer                              │
│ - security-reviewer                          │
│ - log-analyzer                               │
└───────────────┬─────────────────────────────┘
                │
┌───────────────▼─────────────────────────────┐
│ SubAgent Runtime                             │
│ - isolated context                           │
│ - model routing                              │
│ - tool loop                                  │
│ - result validation                          │
└───────────────┬─────────────────────────────┘
                │
┌───────────────▼─────────────────────────────┐
│ Tool Gateway / Permission Engine             │
│ - tool visibility                            │
│ - authorization                              │
│ - approval                                   │
│ - sandbox                                    │
│ - audit log                                  │
└───────────────┬─────────────────────────────┘
                │
┌───────────────▼─────────────────────────────┐
│ Evidence Store / Trace Store / Artifact Store│
└─────────────────────────────────────────────┘
```

## 4. 设计原则

### 4.1 主控集中，子任务自治

主 Agent 是唯一的全局决策者。SubAgent 只在局部任务内自治，不直接决定全局计划、是否结束 Goal、是否批准执行。

错误设计：

```text
SubAgent 自己判断整个任务是否完成。
SubAgent 自己决定是否进入执行模式。
SubAgent 自己创建更多 SubAgent。
```

推荐设计：

```text
SubAgent 返回事实、证据、风险、建议。
Main Agent 汇总后做最终判断。
Goal Evaluator 独立判断是否达成目标。
```

### 4.2 默认 fresh context

MVP 阶段建议所有 named SubAgent 默认 fresh context。

```text
SubAgent 启动时只看到：
- 自己的 system prompt
- 工程环境信息
- 主 Agent 构造的 DelegationSpec
- 必要的用户目标摘要
```

### 4.3 只返回摘要，不返回过程噪声

SubAgent 不应该把完整搜索日志、测试日志、文件内容都返回主 Agent。它应返回：

```text
- 结论
- 证据引用
- 置信度
- 风险
- 未决问题
- 建议下一步
```

### 4.4 Read-heavy 优先并行，Write-heavy 谨慎并行

并行 SubAgent 最适合：

```text
- 代码库探索
- 日志分析
- 测试面分析
- PR 审查
- 文档归纳
- 风险识别
```

不建议一开始支持多个 SubAgent 并行修改同一代码库。

## 5. 核心模块设计

### 5.1 AgentRegistry

负责注册、查询、版本化 SubAgent 定义。

```ts
interface AgentRegistry {
  register(definition: SubAgentDefinition): void;
  get(name: string): SubAgentDefinition;
  list(filter?: AgentFilter): SubAgentDefinition[];
  resolve(name: string, version?: string): SubAgentDefinition;
}
```

### 5.2 DelegationManager

负责主 Agent 到 SubAgent 的委派。

```ts
interface DelegationManager {
  delegate(
    parentContext: MainAgentContext,
    spec: DelegationSpec
  ): Promise<AgentResult>;

  delegateParallel(
    parentContext: MainAgentContext,
    specs: DelegationSpec[],
    options: ParallelDelegationOptions
  ): Promise<AgentResult[]>;

  cancel(taskId: string): Promise<void>;

  resume(
    parentContext: MainAgentContext,
    agentRunId: string,
    followUp: DelegationFollowUp
  ): Promise<AgentResult>;
}
```

### 5.3 SubAgentRuntime

负责真正运行一个 SubAgent。

```ts
interface SubAgentRuntime {
  run(context: SubAgentRunContext): Promise<AgentResult>;
}
```

职责：

```text
1. 初始化独立上下文。
2. 注入 SubAgent system prompt。
3. 注入 DelegationSpec。
4. 暴露被授权工具。
5. 执行模型 tool loop。
6. 检查预算。
7. 校验输出协议。
8. 记录 trace 和 audit log。
```

### 5.4 PermissionEngine

负责权限合成和工具授权。

```ts
interface PermissionEngine {
  computeEffectivePolicy(
    parentPolicy: PermissionPolicy,
    subAgentPolicy: PermissionPolicy,
    runtimePolicy: PermissionPolicy,
    workspacePolicy: WorkspacePolicy
  ): EffectivePermissionPolicy;

  authorizeToolCall(
    context: AgentRunContext,
    toolCall: ToolCall
  ): Promise<ToolAuthorizationDecision>;
}
```

### 5.5 ToolGateway

所有工具调用必须经过 ToolGateway。

```ts
interface ToolGateway {
  visibleTools(policy: EffectivePermissionPolicy): ToolSpec[];

  execute(
    context: AgentRunContext,
    toolCall: ToolCall
  ): Promise<ToolResult>;
}
```

### 5.6 ResultSynthesizer

负责汇总多个 SubAgent 结果。

```ts
interface ResultSynthesizer {
  synthesize(input: SynthesisInput): Promise<SynthesisResult>;
}
```

## 6. 核心数据模型

### 6.1 SubAgentDefinition

```ts
type SubAgentDefinition = {
  name: string;
  version: string;
  description: string;

  role: "researcher" | "reviewer" | "executor" | "tester" | "analyst";

  model: {
    provider: string;
    name: string | "inherit";
    reasoningEffort?: "low" | "medium" | "high";
    temperature?: number;
    maxTokens?: number;
  };

  prompt: {
    system: string;
    outputContract: string;
  };

  tools: {
    allow?: string[];
    deny?: string[];
    mcpServers?: string[];
  };

  permission: PermissionPolicy;

  isolation: {
    context: "fresh" | "fork";
    workspace: "shared" | "sandbox" | "worktree";
    memory: "none" | "session" | "project" | "user";
    network: "disabled" | "restricted" | "enabled";
  };

  budget: {
    maxTurns: number;
    maxToolCalls: number;
    maxInputTokens?: number;
    maxOutputTokens?: number;
    timeoutMs?: number;
  };

  routing: {
    taskTypes: string[];
    triggerKeywords?: string[];
    priority: number;
  };

  lifecycle: {
    resumable: boolean;
    cancellable: boolean;
    allowNestedDelegation: false;
  };
};
```

说明：

- `description` 要写得非常明确，因为它会影响主 Agent 何时选择该 SubAgent。
- `allowNestedDelegation` MVP 阶段固定为 `false`。
- `tools.allow` 推荐优先使用白名单，而不是只写 denylist。

### 6.2 DelegationSpec

主 Agent 委派给 SubAgent 的任务协议。

```ts
type DelegationSpec = {
  taskId: string;
  parentThreadId: string;
  agentName: string;

  objective: string;
  background: string;

  modeContext: {
    parentMode: "normal" | "plan" | "execute" | "goal";
    goalId?: string;
    planId?: string;
  };

  scope: {
    includePaths?: string[];
    excludePaths?: string[];
    modules?: string[];
    symbols?: string[];
    files?: string[];
  };

  constraints: string[];

  allowedActions: string[];
  forbiddenActions: string[];

  evidenceRequirements: Array<{
    type: "file" | "command" | "diff" | "test" | "log" | "artifact";
    required: boolean;
    description: string;
  }>;

  expectedOutput: {
    format: "json";
    schemaName: "AgentResult";
    requiredSections: string[];
  };

  budget: {
    maxTurns: number;
    maxToolCalls: number;
    maxTokens: number;
    timeoutMs?: number;
  };

  returnPolicy: {
    includeRawLogs: boolean;
    includeFileSnippets: boolean;
    maxSummaryTokens: number;
  };
};
```

示例：

```json
{
  "taskId": "plan-auth-oauth-001",
  "parentThreadId": "thread-123",
  "agentName": "plan-researcher",
  "objective": "研究当前项目认证流程，找出新增 OAuth 登录能力需要修改的位置",
  "background": "用户要求先规划，不允许直接改代码",
  "modeContext": {
    "parentMode": "plan"
  },
  "scope": {
    "modules": ["auth", "session", "user"],
    "excludePaths": ["node_modules", "dist", "build"]
  },
  "constraints": [
    "不得修改任何文件",
    "不得运行会写回仓库文件的命令",
    "关键结论必须附带证据"
  ],
  "allowedActions": [
    "read_file",
    "search_code",
    "git_diff",
    "git_status",
    "run_non_mutating_command"
  ],
  "forbiddenActions": [
    "write_file",
    "edit_file",
    "apply_patch",
    "run_formatter_write",
    "run_migration",
    "deploy"
  ],
  "evidenceRequirements": [
    {
      "type": "file",
      "required": true,
      "description": "每个关键模块结论必须附带文件路径"
    }
  ],
  "expectedOutput": {
    "format": "json",
    "schemaName": "AgentResult",
    "requiredSections": [
      "summary",
      "findings",
      "relevantFiles",
      "risks",
      "recommendations",
      "openQuestions"
    ]
  },
  "budget": {
    "maxTurns": 6,
    "maxToolCalls": 30,
    "maxTokens": 12000
  },
  "returnPolicy": {
    "includeRawLogs": false,
    "includeFileSnippets": true,
    "maxSummaryTokens": 2000
  }
}
```

### 6.3 AgentResult

SubAgent 的标准返回协议。

```ts
type AgentResult = {
  taskId: string;
  agentRunId: string;
  agentName: string;

  status: "completed" | "partial" | "blocked" | "failed" | "cancelled";

  summary: string;

  findings: Array<{
    claim: string;
    evidence: EvidenceRef[];
    confidence: "high" | "medium" | "low";
  }>;

  relevantFiles: Array<{
    path: string;
    reason: string;
    importance: "high" | "medium" | "low";
  }>;

  risks: Array<{
    risk: string;
    reason: string;
    mitigation?: string;
    severity: "critical" | "high" | "medium" | "low";
  }>;

  recommendations: Array<{
    recommendation: string;
    rationale: string;
    priority: "must" | "should" | "could";
  }>;

  openQuestions: string[];

  suggestedNextSteps: string[];

  metrics: {
    turnsUsed: number;
    toolCallsUsed: number;
    inputTokens?: number;
    outputTokens?: number;
    elapsedMs: number;
  };

  artifacts?: ArtifactRef[];

  errors?: Array<{
    code: string;
    message: string;
    recoverable: boolean;
  }>;
};
```

### 6.4 EvidenceRef

```ts
type EvidenceRef = {
  type: "file" | "symbol" | "command" | "diff" | "test" | "log" | "artifact";
  ref: string;
  detail: string;
  lineRange?: {
    start: number;
    end: number;
  };
  commandExitCode?: number;
};
```

证据必须足够让主 Agent 做判断，但不能把大量原始日志塞回主上下文。

### 6.5 PermissionPolicy

```ts
type PermissionPolicy = {
  mode: "readonly" | "default" | "accept_edits" | "auto" | "deny_by_default" | "bypass";

  tools: {
    allow?: string[];
    deny?: string[];
    ask?: string[];
  };

  filesystem: {
    read: PathRule[];
    write: PathRule[];
    deny: PathRule[];
    protectedPaths: string[];
  };

  shell: {
    enabled: boolean;
    strategy: "deny_all" | "allowlist" | "classifier" | "ask";
    allowedCommands?: string[];
    deniedPatterns?: string[];
    requireApprovalPatterns?: string[];
  };

  network: {
    enabled: boolean;
    allowedDomains?: string[];
    deniedDomains?: string[];
  };

  mutation: {
    allowFileWrite: boolean;
    allowPatch: boolean;
    allowDelete: boolean;
    allowFormatWrite: boolean;
    allowMigration: boolean;
    allowDeploy: boolean;
  };
};
```

## 7. SubAgent 生命周期

### 7.1 状态机

```text
CREATED
  ↓
QUEUED
  ↓
RUNNING
  ├─ WAITING_APPROVAL
  ├─ WAITING_TOOL
  ├─ CANCEL_REQUESTED
  ↓
COMPLETED
或
PARTIAL
或
BLOCKED
或
FAILED
或
CANCELLED
```

### 7.2 状态定义

| 状态 | 含义 |
|---|---|
| CREATED | 已创建任务，但尚未进入调度队列 |
| QUEUED | 等待执行，可能受并发限制 |
| RUNNING | SubAgent 正在运行 |
| WAITING_APPROVAL | 某个工具调用需要用户或策略审批 |
| WAITING_TOOL | 工具执行中 |
| COMPLETED | 成功完成并返回完整 AgentResult |
| PARTIAL | 超预算或信息不足，但返回了部分结果 |
| BLOCKED | 被外部条件阻塞，例如缺少权限、依赖、凭证 |
| FAILED | 运行失败，例如模型错误、协议校验失败 |
| CANCELLED | 用户或主 Agent 取消 |

## 8. 协作协议

### 8.1 单次委派协议

```text
Main Agent
  → 构造 DelegationSpec
  → DelegationManager 校验
  → SubAgentRuntime 运行
  → 返回 AgentResult
  → Main Agent 汇总
```

适用于：

```text
- Plan Mode 中的代码库研究
- 单模块风险分析
- 单次测试失败归因
- 单个日志文件摘要
```

### 8.2 并行 fan-out / fan-in 协议

```text
Main Agent
  → 拆成多个 DelegationSpec
  → 并行启动多个 SubAgent
  → 等待全部或部分结果
  → ResultSynthesizer 汇总
  → Main Agent 输出最终结论
```

适用于：

```text
- PR 审查：安全、测试、可维护性、性能分别审查
- 复杂功能规划：前端、后端、数据库、测试面并行分析
- 大型文档分析：按章节拆分
```

### 8.3 串行 chain 协议

```text
SubAgent A：事实探索
  ↓
SubAgent B：风险审查
  ↓
SubAgent C：测试面分析
  ↓
Main Agent：生成最终计划
```

适用于：

```text
- Plan Mode 的高质量计划生成
- 架构改造前的多阶段评估
- 安全审查后的修复计划
```

### 8.4 Reviewer Gate 协议

```text
Worker Agent 完成实现
  ↓
Code Reviewer SubAgent 审查 diff
  ↓
Test Analyzer SubAgent 验证测试覆盖
  ↓
Main Agent 决定是否继续修复
```

适用于 Goal Mode 中的持续改进闭环。

## 9. 权限设计

### 9.1 权限合成规则

```ts
function computeEffectivePolicy(
  parent: PermissionPolicy,
  sub: PermissionPolicy,
  runtime: PermissionPolicy,
  workspace: WorkspacePolicy
): EffectivePermissionPolicy {
  return intersectPolicies(parent, sub, runtime, workspace);
}
```

规则：

```text
1. deny 永远优先。
2. 子 Agent 不能扩大父 Agent 权限。
3. Plan Mode 下所有 SubAgent 默认 readonly。
4. SubAgent 不能 spawn SubAgent。
5. 写操作必须经过 workspace isolation 和 approval policy。
6. shell 命令必须分类：read-only、maybe-mutating、mutating、destructive。
```

### 9.2 工具分类

```ts
type ToolMutability =
  | "read"
  | "maybe_write"
  | "write"
  | "destructive"
  | "external_side_effect";

type ToolSpec = {
  name: string;
  category: "fs" | "shell" | "git" | "network" | "mcp" | "browser" | "database";
  mutability: ToolMutability;
  requiresApproval: boolean;
  planModeAllowed: boolean;
  safeInParallel: boolean;
};
```

示例：

| 工具 | mutability | Plan Mode | 并行安全 |
|---|---:|---:|---:|
| read_file | read | 允许 | 是 |
| search_code | read | 允许 | 是 |
| git_status | read | 允许 | 是 |
| git_diff | read | 允许 | 是 |
| npm test | maybe_write | 视情况 | 谨慎 |
| eslint --fix | write | 禁止 | 否 |
| apply_patch | write | 禁止 | 否 |
| rm | destructive | 禁止 | 否 |
| deploy | external_side_effect | 禁止 | 否 |

### 9.3 Plan SubAgent 权限

```ts
const planResearcherPolicy: PermissionPolicy = {
  mode: "readonly",

  tools: {
    allow: [
      "read_file",
      "list_files",
      "search_code",
      "grep",
      "git_status",
      "git_diff",
      "run_non_mutating_command"
    ],
    deny: [
      "write_file",
      "edit_file",
      "apply_patch",
      "delete_file",
      "deploy",
      "database_write"
    ]
  },

  filesystem: {
    read: [{ pattern: "**/*" }],
    write: [],
    deny: [
      { pattern: ".git/**" },
      { pattern: "node_modules/**" },
      { pattern: "dist/**" },
      { pattern: "build/**" }
    ],
    protectedPaths: [".env", ".env.*", "secrets/**"]
  },

  shell: {
    enabled: true,
    strategy: "allowlist",
    allowedCommands: [
      "ls",
      "find",
      "rg",
      "grep",
      "cat",
      "sed",
      "git status",
      "git diff",
      "git grep"
    ],
    deniedPatterns: [
      ">",
      ">>",
      "rm ",
      "mv ",
      "cp ",
      "chmod ",
      "chown ",
      "--write",
      "--fix",
      "format",
      "migrate",
      "apply",
      "deploy"
    ]
  },

  network: {
    enabled: false
  },

  mutation: {
    allowFileWrite: false,
    allowPatch: false,
    allowDelete: false,
    allowFormatWrite: false,
    allowMigration: false,
    allowDeploy: false
  }
};
```

## 10. 上下文隔离设计

### 10.1 Fresh Context

默认模式。

```text
输入：
- SubAgent system prompt
- DelegationSpec
- 环境摘要
- 必要路径 / 模块 / 约束

不输入：
- 完整用户历史对话
- 主 Agent 已读过的所有文件
- 主 Agent 的完整 scratchpad
```

优点：

```text
- 上下文干净
- 可并行
- 成本可控
- 安全边界清晰
```

缺点：

```text
- 需要 DelegationSpec 写得足够清楚
- 可能重复探索
```

### 10.2 Fork Context

高级能力，MVP 后再做。

```text
Fork SubAgent 继承：
- 主 Agent 当前上下文
- 主 Agent 系统提示
- 主 Agent 工具配置
- 当前对话中的关键材料
```

适用于：

```text
- 旁路验证
- 方案反证
- 让另一个 Agent 审查主 Agent 已经形成的计划
```

限制：

```text
- 成本高
- 权限复杂
- 容易继承上下文噪声
```

## 11. 工作区隔离设计

### 11.1 shared workspace

```text
SubAgent 和主 Agent 使用同一个工作目录。
```

适合：

```text
- 只读分析
- Plan Research
- Code Review
```

### 11.2 sandbox workspace

```text
SubAgent 在临时沙箱中运行命令。
```

适合：

```text
- 可能产生临时文件的测试
- 不可信命令
- 外部依赖探测
```

### 11.3 git worktree workspace

```text
为 SubAgent 创建独立 git worktree。
```

适合：

```text
- 并行实现不同方案
- 竞品方案比较
- 有写操作的 worker agent
```

MVP 阶段建议：

```text
Plan / Review / Test Analysis：shared readonly。
Worker / Experiment：worktree。
不允许多个写型 SubAgent 共享同一 checkout。
```

## 12. Plan Mode 中的 SubAgent 设计

### 12.1 目标

Plan Mode 中的 SubAgent 主要承担“只读研究”任务。

```text
Main Agent：
  输出最终 Proposed Plan。

Plan SubAgent：
  收集事实、定位代码路径、识别约束、提供计划输入。
```

### 12.2 推荐内置 SubAgent

#### plan-researcher

```yaml
name: plan-researcher
description: >
  Read-only research agent used in Plan Mode to inspect the repository,
  identify relevant files, understand current architecture, and provide
  evidence-backed planning inputs.

model:
  name: inherit
permission:
  mode: readonly
tools:
  allow:
    - read_file
    - list_files
    - search_code
    - grep
    - git_status
    - git_diff
    - run_non_mutating_command
budget:
  maxTurns: 8
  maxToolCalls: 40
isolation:
  context: fresh
  workspace: shared
  memory: none
```

#### risk-reviewer

```yaml
name: risk-reviewer
description: >
  Read-only reviewer that analyzes proposed implementation paths for
  compatibility, migration, security, and operational risks.

model:
  name: inherit
permission:
  mode: readonly
tools:
  allow:
    - read_file
    - search_code
    - git_diff
budget:
  maxTurns: 5
  maxToolCalls: 20
```

#### test-surface-analyzer

```yaml
name: test-surface-analyzer
description: >
  Read-only analyzer that identifies existing tests, missing test coverage,
  verification commands, and regression surfaces for a proposed plan.

model:
  name: fast
permission:
  mode: readonly
tools:
  allow:
    - read_file
    - list_files
    - search_code
    - grep
    - run_non_mutating_command
budget:
  maxTurns: 5
  maxToolCalls: 25
```

### 12.3 Plan Mode 协作流

```text
User Request
  ↓
Main Agent 判断需要 Plan Mode
  ↓
Mode Controller 设置 mode = plan
  ↓
Main Agent 构造 DelegationSpec
  ↓
Plan Researcher 只读探索
  ↓
Risk Reviewer 审查边界风险
  ↓
Test Surface Analyzer 补充验证方案
  ↓
Main Agent 汇总 Proposed Plan
  ↓
用户 approve / revise / reject
  ↓
approve 后切换 execute mode
```

## 13. Goal Mode 中的 SubAgent 设计

### 13.1 目标

Goal Mode 中，SubAgent 不负责决定 Goal 是否完成。它只负责局部工作。

```text
Goal Controller：
  判断是否继续下一轮。

Main Agent：
  决定本轮要做什么。

SubAgent：
  做局部分析、实现、审查或测试。

Goal Evaluator：
  基于证据判断是否完成。
```

### 13.2 Goal + SubAgent 协作流

```text
Goal active
  ↓
Main Agent 执行一轮
  ↓
需要局部任务时委派 SubAgent
  ↓
SubAgent 返回 AgentResult + Evidence
  ↓
Main Agent 更新 Evidence Ledger
  ↓
Goal Evaluator 判断 complete / continue / blocked
  ↓
continue 则 Goal Controller 触发下一轮
```

### 13.3 证据要求

SubAgent 结果要能进入 Evidence Ledger。

```ts
type EvidenceLedgerEntry = {
  id: string;
  goalId?: string;
  taskId: string;
  agentRunId: string;
  type: "test" | "command" | "diff" | "artifact" | "review" | "benchmark";
  summary: string;
  rawRef?: string;
  parsed?: Record<string, unknown>;
  createdAt: string;
};
```

Goal Evaluator 不应该凭模型自信判断完成，而应该依据测试、benchmark、命令输出、diff、artifact 等证据。

## 14. 类设计

### 14.1 核心类图

```text
MainAgent
  ├── ModeController
  ├── DelegationManager
  │     ├── AgentRegistry
  │     ├── SubAgentRuntime
  │     ├── PermissionEngine
  │     └── RunStore
  ├── ResultSynthesizer
  ├── GoalController
  └── EvidenceLedger

SubAgentRuntime
  ├── ModelClient
  ├── ToolGateway
  ├── ContextBuilder
  ├── OutputValidator
  └── TraceRecorder

ToolGateway
  ├── PermissionEngine
  ├── ToolRegistry
  ├── SandboxExecutor
  └── AuditLogger
```

### 14.2 AgentRegistry

```ts
class AgentRegistry {
  private agents = new Map<string, SubAgentDefinition>();

  register(def: SubAgentDefinition): void {
    const key = `${def.name}@${def.version}`;

    if (this.agents.has(key)) {
      throw new Error(`Duplicate subagent definition: ${key}`);
    }

    this.validateDefinition(def);
    this.agents.set(key, def);
  }

  get(name: string, version = "latest"): SubAgentDefinition {
    if (version === "latest") {
      return this.getLatest(name);
    }

    const key = `${name}@${version}`;
    const def = this.agents.get(key);

    if (!def) {
      throw new Error(`Unknown subagent: ${key}`);
    }

    return def;
  }

  list(): SubAgentDefinition[] {
    return [...this.agents.values()];
  }

  private getLatest(name: string): SubAgentDefinition {
    const candidates = [...this.agents.values()].filter(a => a.name === name);

    if (candidates.length === 0) {
      throw new Error(`Unknown subagent: ${name}`);
    }

    return candidates.sort((a, b) => b.version.localeCompare(a.version))[0];
  }

  private validateDefinition(def: SubAgentDefinition): void {
    if (!def.name || !def.description || !def.prompt.system) {
      throw new Error("Invalid subagent definition");
    }

    if (def.lifecycle.allowNestedDelegation !== false) {
      throw new Error("Nested delegation is not allowed in MVP");
    }
  }
}
```

### 14.3 DelegationManager

```ts
class DelegationManager {
  constructor(
    private registry: AgentRegistry,
    private runtime: SubAgentRuntime,
    private permissionEngine: PermissionEngine,
    private runStore: AgentRunStore
  ) {}

  async delegate(
    parentContext: MainAgentContext,
    spec: DelegationSpec
  ): Promise<AgentResult> {
    if (parentContext.role !== "main") {
      throw new Error("Only Main Agent can delegate to SubAgent");
    }

    const definition = this.registry.get(spec.agentName);

    const effectivePolicy = this.permissionEngine.computeEffectivePolicy(
      parentContext.permissionPolicy,
      definition.permission,
      parentContext.runtimePolicy,
      parentContext.workspacePolicy
    );

    const run = await this.runStore.create({
      taskId: spec.taskId,
      parentThreadId: spec.parentThreadId,
      agentName: definition.name,
      status: "QUEUED"
    });

    const subContext: SubAgentRunContext = {
      runId: run.id,
      taskId: spec.taskId,
      parentThreadId: spec.parentThreadId,
      definition,
      delegationSpec: spec,
      effectivePolicy,
      model: this.resolveModel(parentContext, definition),
      depth: parentContext.depth + 1
    };

    try {
      await this.runStore.updateStatus(run.id, "RUNNING");
      const result = await this.runtime.run(subContext);
      await this.runStore.finish(run.id, result.status);
      return result;
    } catch (error) {
      await this.runStore.fail(run.id, String(error));

      return {
        taskId: spec.taskId,
        agentRunId: run.id,
        agentName: definition.name,
        status: "failed",
        summary: "SubAgent execution failed.",
        findings: [],
        relevantFiles: [],
        risks: [],
        recommendations: [],
        openQuestions: [],
        suggestedNextSteps: [],
        metrics: {
          turnsUsed: 0,
          toolCallsUsed: 0,
          elapsedMs: 0
        },
        errors: [
          {
            code: "SUBAGENT_RUNTIME_ERROR",
            message: String(error),
            recoverable: true
          }
        ]
      };
    }
  }

  async delegateParallel(
    parentContext: MainAgentContext,
    specs: DelegationSpec[],
    options: ParallelDelegationOptions
  ): Promise<AgentResult[]> {
    const limitedSpecs = specs.slice(0, options.maxParallelAgents);

    const tasks = limitedSpecs.map(spec =>
      this.delegate(parentContext, spec)
    );

    if (options.waitStrategy === "all") {
      return Promise.all(tasks);
    }

    if (options.waitStrategy === "all_settled") {
      const settled = await Promise.allSettled(tasks);
      return settled.map((r, index) => {
        if (r.status === "fulfilled") return r.value;

        return this.buildFailedResult(specs[index], r.reason);
      });
    }

    throw new Error(`Unsupported wait strategy: ${options.waitStrategy}`);
  }

  private resolveModel(
    parentContext: MainAgentContext,
    definition: SubAgentDefinition
  ): ResolvedModel {
    if (definition.model.name === "inherit") {
      return parentContext.model;
    }

    return {
      provider: definition.model.provider,
      name: definition.model.name,
      reasoningEffort: definition.model.reasoningEffort,
      temperature: definition.model.temperature
    };
  }

  private buildFailedResult(spec: DelegationSpec, reason: unknown): AgentResult {
    return {
      taskId: spec.taskId,
      agentRunId: "unknown",
      agentName: spec.agentName,
      status: "failed",
      summary: "Parallel SubAgent failed.",
      findings: [],
      relevantFiles: [],
      risks: [],
      recommendations: [],
      openQuestions: [],
      suggestedNextSteps: [],
      metrics: {
        turnsUsed: 0,
        toolCallsUsed: 0,
        elapsedMs: 0
      },
      errors: [
        {
          code: "PARALLEL_SUBAGENT_FAILED",
          message: String(reason),
          recoverable: true
        }
      ]
    };
  }
}
```

### 14.4 SubAgentRuntime

```ts
class SubAgentRuntime {
  constructor(
    private modelClient: ModelClient,
    private contextBuilder: ContextBuilder,
    private toolGateway: ToolGateway,
    private outputValidator: OutputValidator,
    private traceRecorder: TraceRecorder
  ) {}

  async run(ctx: SubAgentRunContext): Promise<AgentResult> {
    if (ctx.depth > 1) {
      throw new Error("Nested subagent delegation is disabled");
    }

    const startedAt = Date.now();

    const messages = await this.contextBuilder.build(ctx);

    let turnsUsed = 0;
    let toolCallsUsed = 0;

    for (; turnsUsed < ctx.definition.budget.maxTurns; turnsUsed++) {
      const response = await this.modelClient.complete({
        model: ctx.model,
        messages,
        tools: this.toolGateway.visibleTools(ctx.effectivePolicy)
      });

      await this.traceRecorder.recordModelResponse(ctx.runId, response);

      if (response.toolCalls && response.toolCalls.length > 0) {
        for (const toolCall of response.toolCalls) {
          if (toolCallsUsed >= ctx.definition.budget.maxToolCalls) {
            return this.partialResult(ctx, startedAt, turnsUsed, toolCallsUsed, "Tool call budget exhausted");
          }

          const decision = await this.toolGateway.authorize(ctx, toolCall);

          if (!decision.allowed) {
            messages.push({
              role: "tool",
              toolCallId: toolCall.id,
              content: `Denied by policy: ${decision.reason}`
            });
            continue;
          }

          const toolResult = await this.toolGateway.execute(ctx, toolCall);
          toolCallsUsed++;

          messages.push({
            role: "tool",
            toolCallId: toolCall.id,
            content: summarizeToolResult(toolResult)
          });
        }

        continue;
      }

      const validation = await this.outputValidator.validateAgentResult(
        response.content
      );

      if (validation.valid) {
        return {
          ...validation.result,
          agentRunId: ctx.runId,
          metrics: {
            ...validation.result.metrics,
            turnsUsed,
            toolCallsUsed,
            elapsedMs: Date.now() - startedAt
          }
        };
      }

      messages.push({
        role: "user",
        content: [
          "Your output did not match the required AgentResult schema.",
          `Validation error: ${validation.error}`,
          "Return valid JSON only."
        ].join("\n")
      });
    }

    return this.partialResult(
      ctx,
      startedAt,
      turnsUsed,
      toolCallsUsed,
      "Turn budget exhausted"
    );
  }

  private partialResult(
    ctx: SubAgentRunContext,
    startedAt: number,
    turnsUsed: number,
    toolCallsUsed: number,
    reason: string
  ): AgentResult {
    return {
      taskId: ctx.taskId,
      agentRunId: ctx.runId,
      agentName: ctx.definition.name,
      status: "partial",
      summary: reason,
      findings: [],
      relevantFiles: [],
      risks: [],
      recommendations: [],
      openQuestions: [reason],
      suggestedNextSteps: [],
      metrics: {
        turnsUsed,
        toolCallsUsed,
        elapsedMs: Date.now() - startedAt
      }
    };
  }
}
```

### 14.5 PermissionEngine

```ts
class PermissionEngine {
  computeEffectivePolicy(
    parent: PermissionPolicy,
    sub: PermissionPolicy,
    runtime: PermissionPolicy,
    workspace: WorkspacePolicy
  ): EffectivePermissionPolicy {
    return {
      mode: this.minPrivilegeMode(parent.mode, sub.mode, runtime.mode),
      tools: this.intersectToolRules(parent.tools, sub.tools, runtime.tools),
      filesystem: this.intersectFilesystemRules(
        parent.filesystem,
        sub.filesystem,
        runtime.filesystem,
        workspace.filesystem
      ),
      shell: this.intersectShellRules(parent.shell, sub.shell, runtime.shell),
      network: this.intersectNetworkRules(parent.network, sub.network, runtime.network),
      mutation: {
        allowFileWrite:
          parent.mutation.allowFileWrite &&
          sub.mutation.allowFileWrite &&
          runtime.mutation.allowFileWrite,
        allowPatch:
          parent.mutation.allowPatch &&
          sub.mutation.allowPatch &&
          runtime.mutation.allowPatch,
        allowDelete:
          parent.mutation.allowDelete &&
          sub.mutation.allowDelete &&
          runtime.mutation.allowDelete,
        allowFormatWrite:
          parent.mutation.allowFormatWrite &&
          sub.mutation.allowFormatWrite &&
          runtime.mutation.allowFormatWrite,
        allowMigration:
          parent.mutation.allowMigration &&
          sub.mutation.allowMigration &&
          runtime.mutation.allowMigration,
        allowDeploy:
          parent.mutation.allowDeploy &&
          sub.mutation.allowDeploy &&
          runtime.mutation.allowDeploy
      }
    };
  }

  async authorizeToolCall(
    ctx: AgentRunContext,
    call: ToolCall
  ): Promise<ToolAuthorizationDecision> {
    const spec = ctx.toolRegistry.get(call.name);

    if (!this.isToolVisible(ctx.effectivePolicy, call.name)) {
      return {
        allowed: false,
        reason: `Tool ${call.name} is not visible under current policy`
      };
    }

    if (this.matchesDenyRule(ctx.effectivePolicy, call)) {
      return {
        allowed: false,
        reason: "Matched deny rule"
      };
    }

    if (ctx.effectivePolicy.mode === "readonly" && spec.mutability !== "read") {
      return {
        allowed: false,
        reason: "Readonly agent cannot invoke mutating tools"
      };
    }

    if (call.name === "shell") {
      return this.authorizeShellCall(ctx, call);
    }

    if (this.requiresApproval(ctx.effectivePolicy, spec, call)) {
      return this.askApproval(ctx, call);
    }

    return {
      allowed: true,
      reason: "Allowed by effective policy"
    };
  }

  private authorizeShellCall(
    ctx: AgentRunContext,
    call: ToolCall
  ): ToolAuthorizationDecision {
    const command = String(call.args.command ?? "");

    for (const pattern of ctx.effectivePolicy.shell.deniedPatterns ?? []) {
      if (command.includes(pattern)) {
        return {
          allowed: false,
          reason: `Shell command matched denied pattern: ${pattern}`
        };
      }
    }

    if (ctx.effectivePolicy.shell.strategy === "allowlist") {
      const allowed = ctx.effectivePolicy.shell.allowedCommands?.some(prefix =>
        command.startsWith(prefix)
      );

      if (!allowed) {
        return {
          allowed: false,
          reason: "Shell command is not in allowlist"
        };
      }
    }

    return {
      allowed: true,
      reason: "Shell command allowed"
    };
  }

  private minPrivilegeMode(...modes: PermissionPolicy["mode"][]) {
    const rank = {
      readonly: 0,
      deny_by_default: 1,
      default: 2,
      accept_edits: 3,
      auto: 4,
      bypass: 5
    };

    return modes.sort((a, b) => rank[a] - rank[b])[0];
  }
}
```

## 15. SubAgent Prompt 模板

### 15.1 通用 SubAgent System Prompt

```text
You are a specialized SubAgent.

You are not the final user-facing assistant.
Your job is to complete the delegated task within the given scope and return a structured AgentResult.

Rules:
1. Stay within the objective, scope, and constraints.
2. Use only allowed tools.
3. Do not perform actions listed as forbidden.
4. Do not spawn other agents.
5. Do not make global product or architecture decisions unless asked.
6. Support important claims with evidence.
7. Return concise structured output.
8. Do not include raw logs unless explicitly requested.
9. If blocked, return status = "blocked" and explain what would unblock progress.
```

### 15.2 Plan Researcher Prompt

```text
You are a Plan Research SubAgent.

Your job is to gather implementation-relevant facts for planning.
You do not implement changes.
You do not edit files.
You do not produce the final user-facing plan.

Focus on:
1. Relevant files and modules
2. Current architecture and data flow
3. Integration points
4. Constraints and compatibility risks
5. Test and verification surface
6. Open questions that affect implementation decisions

Return AgentResult JSON only.
Every key finding must include evidence.
```

### 15.3 Code Reviewer Prompt

```text
You are a Code Review SubAgent.

Your job is to review changes for correctness, maintainability, safety, and test adequacy.
Do not modify files.
Use git diff and relevant source files as evidence.

Prioritize:
1. Correctness bugs
2. Security risks
3. Data loss or migration risks
4. API compatibility issues
5. Missing tests
6. Maintainability problems

Return AgentResult JSON only.
```

## 16. 数据库存储设计

### 16.1 subagent_definitions

```sql
create table subagent_definitions (
  id text primary key,
  name text not null,
  version text not null,
  description text not null,
  definition_json text not null,
  created_at timestamp not null,
  updated_at timestamp not null,
  unique(name, version)
);
```

### 16.2 subagent_runs

```sql
create table subagent_runs (
  id text primary key,
  task_id text not null,
  parent_thread_id text not null,
  agent_name text not null,
  agent_version text not null,
  status text not null,
  delegation_spec_json text not null,
  effective_policy_json text not null,
  started_at timestamp,
  finished_at timestamp,
  error_code text,
  error_message text
);
```

### 16.3 subagent_messages

```sql
create table subagent_messages (
  id text primary key,
  run_id text not null,
  role text not null,
  content text not null,
  created_at timestamp not null
);
```

### 16.4 tool_audit_logs

```sql
create table tool_audit_logs (
  id text primary key,
  run_id text not null,
  agent_name text not null,
  tool_name text not null,
  args_json text not null,
  decision text not null,
  decision_reason text not null,
  result_summary text,
  created_at timestamp not null
);
```

### 16.5 evidence_ledger

```sql
create table evidence_ledger (
  id text primary key,
  parent_thread_id text not null,
  goal_id text,
  task_id text not null,
  agent_run_id text not null,
  evidence_type text not null,
  summary text not null,
  raw_ref text,
  parsed_json text,
  created_at timestamp not null
);
```

## 17. API 设计

### 17.1 注册 SubAgent

```http
POST /api/agents/subagents
Content-Type: application/json
```

```json
{
  "name": "plan-researcher",
  "version": "1.0.0",
  "description": "Read-only research agent used in Plan Mode",
  "model": {
    "provider": "openai",
    "name": "inherit"
  },
  "permission": {
    "mode": "readonly"
  }
}
```

### 17.2 发起委派

```http
POST /api/threads/{threadId}/delegations
Content-Type: application/json
```

```json
{
  "agentName": "plan-researcher",
  "objective": "研究当前认证模块实现方式",
  "scope": {
    "modules": ["auth", "session"]
  },
  "constraints": [
    "不得修改文件"
  ]
}
```

### 17.3 查询运行状态

```http
GET /api/agent-runs/{runId}
```

返回：

```json
{
  "runId": "run-001",
  "status": "RUNNING",
  "agentName": "plan-researcher",
  "startedAt": "2026-05-23T10:00:00Z",
  "metrics": {
    "turnsUsed": 3,
    "toolCallsUsed": 12
  }
}
```

### 17.4 取消 SubAgent

```http
POST /api/agent-runs/{runId}/cancel
```

### 17.5 获取 AgentResult

```http
GET /api/agent-runs/{runId}/result
```

## 18. Observability 设计

必须记录：

```text
1. Main Agent 为什么选择某个 SubAgent。
2. DelegationSpec 内容。
3. EffectivePermissionPolicy。
4. SubAgent 每次工具调用。
5. 工具调用授权结果。
6. 被拒绝的工具调用。
7. SubAgent 最终 AgentResult。
8. 主 Agent 如何使用 AgentResult。
9. 多 SubAgent 结果冲突如何解决。
10. Goal Mode 下哪些证据进入 Evidence Ledger。
```

建议指标：

| 指标 | 含义 |
|---|---|
| subagent_run_count | SubAgent 调用次数 |
| subagent_success_rate | 成功率 |
| subagent_blocked_rate | 阻塞率 |
| avg_subagent_latency_ms | 平均耗时 |
| avg_subagent_tool_calls | 平均工具调用数 |
| permission_denied_count | 权限拒绝次数 |
| result_schema_failure_count | 输出协议失败次数 |
| parallel_fanout_size | 平均并行 agent 数 |
| synthesis_conflict_count | 汇总冲突数 |
| token_cost_by_agent | 各类 SubAgent token 成本 |

## 19. 错误处理

### 19.1 权限拒绝

```json
{
  "status": "blocked",
  "summary": "The task requires a mutating tool that is not allowed in readonly mode.",
  "errors": [
    {
      "code": "PERMISSION_DENIED",
      "message": "apply_patch is denied in Plan Mode",
      "recoverable": true
    }
  ],
  "suggestedNextSteps": [
    "Ask the user to approve execution mode",
    "Continue with read-only analysis only"
  ]
}
```

### 19.2 输出协议失败

处理方式：

```text
1. 第一次失败：要求 SubAgent 修正 JSON。
2. 第二次失败：尝试用 OutputRepairModel 修复。
3. 第三次失败：返回 partial result。
```

### 19.3 工具执行超时

```text
- 记录 tool timeout。
- 把该工具结果标记为 unavailable。
- 允许 SubAgent 继续使用其他证据。
- 如果该工具是必要验证面，则返回 blocked。
```

### 19.4 并行结果冲突

冲突处理顺序：

```text
1. 有文件证据的结论优先。
2. 直接命令输出优先于推测。
3. 最新代码优先于旧文档。
4. 多个 SubAgent 一致结论优先。
5. 无法消解时由主 Agent 标记为 open question。
```

## 20. 安全控制

### 20.1 禁止嵌套 SubAgent

```ts
if (context.depth >= 1 && toolCall.name === "delegate_to_subagent") {
  return deny("Subagents cannot spawn subagents");
}
```

### 20.2 敏感文件保护

默认保护：

```text
.env
.env.*
secrets/**
credentials/**
*.pem
*.key
id_rsa
id_ed25519
.git/**
```

### 20.3 shell 命令防护

必须拦截：

```text
rm
mv
cp 到项目目录
chmod
chown
curl | sh
wget | sh
npm publish
docker push
kubectl apply
terraform apply
eslint --fix
prettier --write
alembic upgrade
rails db:migrate
prisma migrate
```

### 20.4 外部副作用控制

默认禁止：

```text
- 生产数据库写入
- 部署
- 发邮件
- 创建 issue / PR / comment
- 推送代码
- 发布包
- 调用真实支付 / 交易 / 下单接口
```

## 21. MVP 落地计划

### 阶段一：最小 SubAgent Runtime

实现：

```text
- SubAgentDefinition
- AgentRegistry
- DelegationSpec
- AgentResult
- Fresh context
- Tool allowlist
- Permission intersection
- Single SubAgent delegation
```

验收：

```text
- 主 Agent 能调用 plan-researcher。
- plan-researcher 只能读，不能写。
- SubAgent 返回结构化 AgentResult。
- 主 Agent 能汇总 AgentResult。
```

### 阶段二：Plan Mode 集成

实现：

```text
- mode = plan
- Plan SubAgent 自动可用
- mutation tools 全局禁止
- submit_plan artifact
- approve / revise / reject
```

验收：

```text
- Plan Mode 下任何写工具调用被拒绝。
- 计划前能自动做代码库研究。
- 用户批准前工作区无代码修改。
```

### 阶段三：并行 SubAgent

实现：

```text
- delegateParallel
- maxParallelAgents
- all / allSettled wait strategy
- ResultSynthesizer
```

验收：

```text
- 可并行启动 security-reviewer / test-analyzer / maintainability-reviewer。
- 所有结果汇总成一个统一报告。
- 失败的 SubAgent 不影响其他 SubAgent 返回。
```

### 阶段四：Goal Mode 集成

实现：

```text
- Evidence Ledger
- Goal Controller
- Goal Evaluator
- continuation loop
- SubAgent evidence ingestion
```

验收：

```text
- Goal 未完成时自动继续。
- Goal 完成必须有证据。
- SubAgent 结果可作为 Goal completion evidence。
```

### 阶段五：高级隔离

实现：

```text
- fork context
- sandbox workspace
- git worktree workspace
- resumable subagent
```

## 22. 推荐内置 SubAgent 集合

| SubAgent | 权限 | 场景 |
|---|---|---|
| plan-researcher | readonly | Plan Mode 代码库研究 |
| architecture-reviewer | readonly | 架构改造风险分析 |
| test-surface-analyzer | readonly / test-readonly | 测试入口和覆盖面分析 |
| code-reviewer | readonly | diff 审查 |
| security-reviewer | readonly | 安全风险审查 |
| log-analyzer | readonly | 日志、异常、trace 分析 |
| doc-summarizer | readonly | 文档摘要 |
| worker | write in worktree | 执行具体代码修改 |
| benchmark-runner | sandbox | benchmark / 性能验证 |

MVP 只需要前三个：

```text
plan-researcher
risk-reviewer
test-surface-analyzer
```

## 23. 关键设计取舍

### 23.1 为什么 SubAgent 不直接输出最终答案

因为 SubAgent 通常缺少完整用户上下文、产品偏好和审批状态。它应返回事实和证据，最终答案由主 Agent 生成。

### 23.2 为什么默认 fresh context

因为 SubAgent 的主要价值就是隔离噪声。Fresh context 能降低上下文污染、降低成本、增强可并行性。

### 23.3 为什么禁止 SubAgent 嵌套

嵌套会快速放大预算、权限、生命周期和可观测性复杂度。MVP 阶段应由主 Agent 统一链式调度。

### 23.4 为什么权限不能只靠 prompt

模型提示词只能影响模型“想做什么”，不能保证它“不能做什么”。权限必须由 Tool Gateway 和 Runtime 强制执行。

### 23.5 为什么并行写操作要谨慎

多个 Agent 同时修改同一代码库会产生冲突、重复实现、测试不一致和合并成本。初期只允许并行 read-heavy 任务；写型 Agent 需要 worktree 隔离。

## 24. 最终推荐架构摘要

```text
Main Agent
  管目标、模式、决策、汇总。

SubAgent
  管局部探索、局部验证、局部审查。

Delegation Manager
  管委派、生命周期、并发、取消、恢复。

Permission Engine
  管父子权限交集、deny 优先、工具授权。

Tool Gateway
  管工具可见性、工具执行、审计。

Evidence Ledger
  管可验证证据，支撑 Goal Mode 和结果审计。

Result Synthesizer
  管多 SubAgent 结果合并、冲突消解、计划输入生成。
```

推荐先按这个最小闭环实现：

```text
/plan
  → Main Agent 进入 Plan Mode
  → 调用 plan-researcher
  → 调用 test-surface-analyzer
  → 主 Agent 汇总 Proposed Plan
  → 用户批准
  → 切换执行模式
```

这套 SubAgent 机制打牢后，Plan Mode、Goal Mode、PR Review、多 Agent 并行探索、证据型自动续跑都可以自然复用。

## 25. 参考资料

- Claude Code Sub-agents 文档：https://code.claude.com/docs/en/sub-agents
- Claude Code Permissions 文档：https://code.claude.com/docs/en/permissions
- Claude Code Permission Modes 文档：https://code.claude.com/docs/en/permission-modes
- OpenAI Codex Subagents 概念文档：https://developers.openai.com/codex/concepts/subagents
- OpenAI Codex Subagents Workflow 文档：https://developers.openai.com/codex/subagents
- OpenAI Codex Goals Cookbook：https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex
