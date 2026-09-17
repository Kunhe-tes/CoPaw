# src/swe 热点路径代码质量与性能优化分析

日期：2026-08-21

范围：继续阅读 `src/swe` 高频用户请求路径，重点分析 Query Runtime 与 Agent 装配；`TokenUsageManager` 不在本次范围内。

本文件保存当前分析结论和后续优化方案，不包含实现代码。

## 一、热点路径总览

普通聊天请求的主要路径如下：

```text
HTTP / Channel Request
  -> TenantIdentityMiddleware
  -> TenantWorkspaceMiddleware
  -> DynamicMultiAgentRunner
  -> AgentRunner._stream_query_entry
  -> _prepare_query_preflight
  -> _prepare_query_runtime
  -> SWEAgent.__init__
  -> register_mcp_clients
  -> load_session_state
  -> SWEAgent.__call__ / ReAct loop
  -> SafeJSONSession.mutate_session_state
  -> ChatManager.update_chat
  -> MCP / skill / tracing cleanup
```

当前固定成本主要集中在三处：

1. 请求开始前的 Agent、Skill、Prompt、MCP 和模型装配。
2. 每轮 Agent 构造中重复的文件读取、frontmatter 解析和配置解析。
3. 请求结束时对完整 Session JSON 的读、解析、合并、序列化、`fsync` 和替换。

上一轮已经完成并合并 Provider/模型装配优化。本轮建议优先处理下面两个模块：

| 优先级 | 模块 | 主要收益 | 风险 |
|---|---|---:|---:|
| P0 | `AgentRunner` Query Runtime | 降低首 token 延迟，减少每轮重复装配 | 高 |
| P1 | `SWEAgent` 工具/技能/Prompt 装配 | 降低 Agent 构造 CPU 和文件 I/O | 高 |
| P1 | Session 持久化 | 降低长会话尾延迟和写放大 | 高 |

## 二、模块一：AgentRunner Query Runtime

### 2.1 关键实现位置

- `_prepare_query_runtime()`：[`runner.py:3443`](/Users/shixiangyi/code/Swe/src/swe/app/runner/runner.py:3443)
- `_build_query_runtime_inputs()`：[`runner.py:3488`](/Users/shixiangyi/code/Swe/src/swe/app/runner/runner.py:3488)
- `_start_query_runtime_resources()`：[`runner.py:3573`](/Users/shixiangyi/code/Swe/src/swe/app/runner/runner.py:3573)
- `_finalize_query_runtime()`：[`runner.py:3742`](/Users/shixiangyi/code/Swe/src/swe/app/runner/runner.py:3742)
- `_stream_query_after_preflight()`：[`runner.py:4946`](/Users/shixiangyi/code/Swe/src/swe/app/runner/runner.py:4946)
- `stream_query()`：[`runner.py:5571`](/Users/shixiangyi/code/Swe/src/swe/app/runner/runner.py:5571)

### 2.2 当前问题

#### A. 每轮请求重新构造完整运行时

`_prepare_query_runtime()` 每轮执行：

- Provider manager 获取和 freshness 刷新；
- Agent 配置读取；
- Chat 查询或创建；
- Context reference 与 selected skill directive 解析；
- Lazy MCP client 构造；
- Session title 生成；
- Session start hook；
- `SWEAgent` 构造；
- MCP schema 注册；
- Session skill detector 绑定。

其中不少数据在同一个 tenant、Agent、channel 和 skill 版本下是只读的，但目前按请求重复计算。

#### B. 重复加载配置

- `_prepare_query_preflight()` 已调用 `load_agent_config()`。
- `_build_query_runtime_inputs()` 在缺失时再次调用 `load_agent_config()`。
- `_load_query_retry_settings()` 在每次 query 的重试循环前再次读取配置。[`runner.py:4624`](/Users/shixiangyi/code/Swe/src/swe/app/runner/runner.py:4624)

这会增加 JSON 读取和 Pydantic 校验，也使配置版本的判断分散在多个调用点。

#### C. 首 token 前的非核心等待

`_start_query_runtime_resources()` 在 Agent 首次输出前调用 `_generate_session_title_before_stream()`。标题服务创建新的 `httpx.AsyncClient` 并等待远端响应。[`title_generator.py:23`](/Users/shixiangyi/code/Swe/src/swe/app/title_generator.py:23)

标题生成失败不会影响主流程，但成功或超时都会延长首 token 延迟。

#### D. MCP schema discovery 的串行装配

`SWEAgent.register_mcp_clients()` 逐个执行 `list_tools()` 和注册。[`react_agent.py:1361`](/Users/shixiangyi/code/Swe/src/swe/agents/react_agent.py:1361)

多个远程 MCP client 时，首 token 延迟近似为各 client discovery 延迟之和。Lazy client 已有 process-local discovery cache，但未消除一次冷请求中的串行等待。

#### E. 清理阶段串行执行多个可独立操作

`_cleanup_query_resources()` 顺序执行：

1. Session state 保存；
2. Chat 更新；
3. MCP 关闭；
4. Skill detector 收尾。

这些操作都设置了独立超时，但总清理时间可能是多个超时之和，造成请求结束慢和资源占用时间变长。[`runner.py:4372`](/Users/shixiangyi/code/Swe/src/swe/app/runner/runner.py:4372)

### 2.3 优化方案

#### 阶段一：先固化行为边界

不新增运行时埋点或日志。先以已有测试补足以下行为边界：

- 同一 query 只读取一次 Agent 配置；
- 标题生成失败、取消或延迟不阻断 Agent 首次输出；
- 多个 MCP client 的注册仍保留配置顺序、重名冲突和失败隔离语义；
- 清理中的 Session 写入、Chat 更新、MCP 关闭和 detector 收尾均会执行；
- 重试使用首轮确定的配置快照，不因配置读取时机不同改变行为。

#### 阶段二：删除同一请求内的重复工作

1. 将 `preflight.agent_config` 作为本轮唯一配置快照，传给 retry settings 解析。
2. 将 `tenant_hooks`、`hook_overlay`、system prompt injections 统一放入 `_QueryRuntimeInputs`，避免二次读取。
3. 将标题生成移到首个模型事件之后的后台任务；标题写回失败不影响 query 成功路径。
4. 对清理操作使用受控并发：Session 保存、Chat 更新、MCP 关闭和 detector 收尾可以并发，但必须保留最终错误隔离和 `QUERY_CLEANUP_TIMEOUT` 语义。

#### 阶段三：引入不可变 Runtime Artifact 缓存

只缓存请求无关的数据：

- system prompt 内容；
- 有效 Skill 的元数据和 runtime profile；
- Skill tool declaration；
- source tool 描述；
- MCP discovery schema；
- 模型能力和只读配置快照。

缓存键至少包含：

```text
storage_scope + agent_id + channel
+ source_config_version + agent_config_token + skill_freshness_token
```

明确禁止缓存：

- `SWEAgent`；
- Toolkit；
- Memory；
- Hook overlay；
- trace context；
- request headers、cookie、auth token；
- approval state；
- 当前用户消息。

同一 key 使用 single-flight；不同 tenant/scope 必须互不阻塞。缓存失效必须接入 Agent 配置写入、Skill 发布/启停、Source System 配置刷新和 Provider 写操作。

## 三、模块二：SWEAgent 工具、技能与 Prompt 装配

### 3.1 关键实现位置

- `SWEAgent.__init__()`：[`react_agent.py:397`](/Users/shixiangyi/code/Swe/src/swe/agents/react_agent.py:397)
- `_create_toolkit()`：[`react_agent.py:536`](/Users/shixiangyi/code/Swe/src/swe/agents/react_agent.py:536)
- `_register_skills()`：[`react_agent.py:961`](/Users/shixiangyi/code/Swe/src/swe/agents/react_agent.py:961)
- `_build_skill_tool_registry()`：[`react_agent.py:1091`](/Users/shixiangyi/code/Swe/src/swe/agents/react_agent.py:1091)
- `_build_sys_prompt()`：[`react_agent.py:1164`](/Users/shixiangyi/code/Swe/src/swe/agents/react_agent.py:1164)
- `register_mcp_clients()`：[`react_agent.py:1361`](/Users/shixiangyi/code/Swe/src/swe/agents/react_agent.py:1361)
- `build_skill_tool_registry()`：[`skill_tool_registry.py:186`](/Users/shixiangyi/code/Swe/src/swe/agents/skill_tool_registry.py:186)
- `build_skill_use_directives()`：[`skill_selection.py:42`](/Users/shixiangyi/code/Swe/src/swe/app/runner/skill_selection.py:42)

### 3.2 当前问题

#### A. 构造函数承担过多职责

`SWEAgent.__init__()` 连续完成：

1. 请求上下文复制；
2. Toolkit 创建；
3. 内置工具注册；
4. Skill 目录扫描和注册；
5. Source tool 注册；
6. System prompt 文件读取；
7. Model/formatter 创建；
8. Memory manager 绑定；
9. Command handler 创建；
10. Hook 注册。

这使构造函数成为高复杂度、难以单独基准和测试的浅接口：调用者只想得到一个 Agent，却必须承担所有装配副作用。

#### B. Skill 文件被多次读取和解析

同一轮可能重复处理 `SKILL.md`：

- `toolkit.register_agent_skill()` 读取技能；
- `build_skill_runtime_profiles()` 读取 frontmatter 和 hooks；
- `build_skill_tool_registry()` 再次读取 frontmatter 和全文；
- `build_skill_use_directives()` 再次读取全文和 frontmatter；
- `get_skill_freshness_token()` 遍历技能目录。

单个 Skill 的重复读取在技能数量增加后会放大为明显的冷启动成本。

#### C. 全局可变 SkillToolRegistry 存在隔离风险

`build_skill_tool_registry()` 每次构造都会先 `registry.clear()`，然后写入当前请求的技能。[`skill_tool_registry.py:207`](/Users/shixiangyi/code/Swe/src/swe/agents/skill_tool_registry.py:207)

该 registry 被 `SkillInvocationDetector` 和 tracing 使用。如果两个 tenant 的请求并发构造 Agent，后一个请求可能覆盖前一个请求的技能归因数据。这既是代码质量问题，也是多租户隔离风险。

#### D. Prompt 读取重复且配置来源分散

`_build_sys_prompt()` 调用 `build_system_prompt_from_working_dir()`，后者可能重新加载 global config 或 agent config。[`prompt.py:199`](/Users/shixiangyi/code/Swe/src/swe/agents/prompt.py:199)

Query 主流程在 session state load 后又强制调用 `rebuild_sys_prompt()`，会再次读取 Prompt 文件。[`runner.py:4897`](/Users/shixiangyi/code/Swe/src/swe/app/runner/runner.py:4897)

### 3.3 优化方案

#### 阶段一：分离“只读装配数据”和“请求可变对象”

将 Agent 构造内部逻辑分为两类：

只读装配数据：

- Prompt 文件内容；
- Skill metadata、frontmatter、runtime profile；
- Skill tool declarations；
- source tool specs；
- MCP schema。

请求可变对象：

- Toolkit 实例；
- Model wrapper；
- InMemoryMemory / chat-bound memory；
- Command handler；
- Hook instances；
- request context。

只读数据可以通过 Runtime Artifact 缓存复用；请求可变对象必须每轮新建。

#### 阶段二：将 SkillToolRegistry 改为实例级或 scope 级

推荐顺序：

1. 首选：把 registry 作为 `SkillInvocationDetector` 的显式依赖，由 Runner 按 runtime artifact 创建。
2. 过渡：保留全局 getter，但将内部缓存改为 `storage_scope -> immutable registry snapshot`。
3. 最终：tracing 事件携带本轮 registry snapshot，不从全局状态读取。

验收要求：并发 tenant A/B 构造 Agent 时，A 的工具归因结果不能包含 B 的 Skill。

#### 阶段三：统一单次 Skill metadata 解析

为一次 artifact 构建建立单一读取过程：

```text
skill directory
  -> read SKILL.md once
  -> parse frontmatter once
  -> inspect hooks once
  -> compute profile / declarations / description
  -> publish immutable SkillMetadata
```

`build_skill_use_directives()`、`build_skill_runtime_profiles()` 和 `build_skill_tool_registry()` 只消费 `SkillMetadata`，不再自行读文件。

#### 阶段四：Prompt 快照和显式失效

Prompt 快照键包含：

- tenant storage scope；
- Agent id；
- enabled prompt file list；
- prompt files 的 mtime/size 或内容 digest；
- heartbeat enabled 状态；
- source system prompt injections 版本。

当 `AGENTS.md`、`SOUL.md`、`PROFILE.md`、`MEMORY.md` 或 Agent 配置变更时，旧快照不可命中。`rebuild_sys_prompt()` 只在 freshness token 变化时执行。

## 四、大文件拆分模式

### 4.1 拆分原则

不要按“每 N 行一个文件”拆分，也不要先移动私有函数再改变行为。拆分目标是让 Module 的 Interface 更小、Depth 更深，并保持请求状态的 Locality。

每次拆分遵守：

1. 先建立行为测试。
2. 先提取纯数据结构或纯函数，再移动有副作用的逻辑。
3. 只通过一个新的 seam 连接旧调用方。
4. 新 Module 不直接读取全局租户、请求或 tracing 状态，除非它的 Interface 明确声明这些依赖。
5. 每次只拆一个职责组，完成测试后再拆下一个。

### 4.2 `runner.py` 推荐拆分

当前 `runner.py` 同时包含请求解析、审批、Hook、MCP、Session、重试、流式输出和清理逻辑。建议最终形成以下 Module：

```text
src/swe/app/runner/
├── runner.py                    # 保留 AgentRunner 外部 Interface 和生命周期编排
├── query_models.py              # QueryPreflight / Runtime / Attempt / Outcome 数据结构
├── query_preflight.py           # 审批、命令识别、prompt hook 前置处理
├── query_runtime.py             # Runtime Inputs、artifact 获取、Agent 装配
├── query_turns.py               # turn plan、agent turn、stop completion gate
├── query_retry.py               # retry config、classification、backoff
├── query_cleanup.py             # state/chat/MCP/detector cleanup
├── query_persistence.py         # session state 保存、cron merge、failure records
├── runtime_artifacts.py         # immutable artifact key/value/cache
└── stream_adapter.py            # SSE/Event/trace/progress 适配
```

拆分后的 `AgentRunner` 只保留：

- 外部 Runner Interface；
- 请求级 context 绑定；
- 上述 Module 的编排顺序；
- 最终异常和取消语义。

不建议把每个 helper 都变成公开 Module。以下函数应继续保持在内部：

- 单个字段解析器；
- 只被一个流程调用的状态转换器；
- 不需要独立替换的纯格式化函数。

### 4.3 `react_agent.py` 推荐拆分

```text
src/swe/agents/
├── react_agent.py               # SWEAgent 外部 Interface、reply/reasoning 生命周期
├── agent_runtime_artifacts.py   # Prompt/Skill/Tool/MCP immutable metadata
├── agent_toolkit_builder.py     # builtin/source/background tool 注册
├── agent_skill_runtime.py       # Skill metadata、profile、directive、registry
├── agent_prompt_builder.py      # prompt 文件快照和 prompt 组合
├── agent_model_builder.py       # model/formatter 选择和 request-bound wrapper
├── agent_memory_runtime.py      # memory manager 绑定和 chat checkpoint
├── agent_mcp_runtime.py         # MCP client 注册、recovery、progress callback
└── agent_hooks.py               # bootstrap、compaction、tool/runtime hooks
```

推荐的拆分 seam 是 `SWEAgent.__init__()` 内部的装配阶段，而不是把 `SWEAgent` 拆成多个继承类。继承拆分会扩大状态面，降低测试 Locality。

### 4.4 Session 相关拆分

`session.py` 当前同时承担路径安全、JSON 读写、锁、状态变更和技能快照。建议拆为：

```text
session.py                     # SafeJSONSession public Interface
session_paths.py               # filename sanitization / path resolution
session_io.py                  # worker-side read/write/atomic replace
session_lock.py                # in-process + cross-process advisory lock
session_mutation.py            # read-modify-write transaction and state merge
session_snapshot.py            # skill snapshot and state normalization
```

中期再引入 append-only repository seam：

```text
SessionStore Interface
├── SafeJSONSessionAdapter      # 兼容现有 JSON 文件
└── AppendOnlySessionAdapter    # 后续 turn/event + snapshot 实现
```

在没有第二个 Adapter 前，不建议提前抽象出复杂 Repository Interface。

## 五、实施顺序与验收门槛

### 第 1 阶段：低风险删除重复工作

- 复用本轮 `agent_config`；
- 标题生成后台化；
- 统一 Skill metadata 读取；
- 只在 prompt freshness 变化时 rebuild；
- 清理阶段受控并发。

### 第 2 阶段：缓存和隔离修复

- immutable Runtime Artifact cache；
- scope-aware SkillToolRegistry；
- MCP schema discovery single-flight；
- 跨进程 Session advisory lock。

### 第 3 阶段：大文件渐进拆分

每次只移动一个职责组，要求：

- 全量相关测试通过；
- GitNexus `detect_changes()` 只显示预期流程；
- 无新增跨租户全局状态；
- 无新增事件循环阻塞 I/O；
- 请求输出、取消、重试、Hook、Skill 归因与租户隔离语义不回退。

## 六、明确暂不处理的内容

- `TokenUsageManager`。
- Session 从 JSON 迁移到数据库或 append-only 存储的完整实现。
- 以继承层次拆分 `SWEAgent`。
- 仅为减少文件行数而引入的薄 Module。
- 在没有基准数据前启用大范围缓存。
