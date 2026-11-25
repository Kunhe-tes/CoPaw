# Agent 可观测平台增强设计：Span 体系、可解释性、可追溯性、异常与性能

> **最终项目设计入口**：[2026-11-15 独立 Agent 可观测设计](docs/superpowers/specs/2026-11-15-independent-agent-observability-design.md)。本文保留为能力蓝图；其中SDK、正文采集、存储或范围与最终设计不一致时，以用户已确认的独立方案为准。

> **2026-11-15 项目边界确认**：本次采用完全独立的可观测方案，新增埋点仅输出元数据日志，正文按业务标识从 NAS 授权查询。既有 swe.tracing、AgentTraceSDK、埋点、配置、输出及查询逻辑均不作为本方案依赖，也不修改。下文的 OTel/GenAI 字段仅作为语义参考，不表示接入既有 SDK 或出口。当前已确认决策与待决项以 [独立设计草案](.scratch/agent-observability/spec.md)、[决策树](.scratch/agent-observability/map.md) 和 [ADR 0047](docs/adr/0047-independent-agent-observability-uses-metadata-logs.md) 为准；正文采集相关旧描述须服从“仅日志元数据、正文读取 NAS”的边界。

> 版本：MVP 设计增强稿 V1.1；范围：功能、OpenTelemetry 埋点与界面，不包含数据库结构。
> 对齐原则：本项目的 Span 业务分类与 OpenTelemetry 的 SpanKind/GenAI 操作语义彼此独立；标准字段优先、业务字段补充、敏感正文默认不采集。

## 1. 总体结论

将平台功能从“Trace 查看”增强为五大分析闭环：**执行过程可观测、结果可解释、过程可追溯、异常可定位、性能可分析**。MVP 保留 Trace Explorer 和 Trace Detail 两个主要入口，Trace Detail 内置 Tree + Waterfall 和 Span Inspector，并增加证据、资产、错误、性能四种专项信息面板，而非扩张成大量孤立页面。

### 1.1 三层语义约定

1. **原生 OTel**：Trace ID / Span ID / Parent、Start/End、Status、Kind、Events、Links、Resource。
2. **标准 GenAI**：`gen_ai.operation.name`、`gen_ai.request.model`、`gen_ai.retrieval.*`、`gen_ai.tool.*`、`gen_ai.prompt.*` 等。遵循项目锁定的语义约定版本。
3. **Agent 平台扩展**：`agentobs.*` 记录当前标准不能表达的 Run、Attempt、知识来源引用、资产快照、审批、错误传播等。提供对外规范字段别名映射，但不在埋点端重复写入相同含义字段。

> `Agent/Workflow/LLM/RAG/…` 是业务 `agentobs.span.type`，不是 OTel 的 `SpanKind`。OTel SpanKind 仍为 INTERNAL、CLIENT、SERVER、PRODUCER、CONSUMER。

## 2. Span 类型设计（对应 3.5）

| 业务 Span 类型 | 语义边界 | 典型子 Span / 操作 | OTel 对齐 | MVP |
|---|---|---|---|---|
| **Agent** | 一次 Agent 的调用或运行，记录入口、目标和结果 | LLM、Tool、RAG、Skill | `gen_ai.operation.name=invoke_agent` | P0 |
| **Workflow** | 固定的流程或业务编排，不等同 Agent 自主决策 | Agent、Tool、LLM、条件流程节点 | `invoke_workflow` | P1 |
| **LLM** | 一次模型推理请求，包括模型规划、分类、抽取等 | 可有网络子调用，通常是叶子 | `chat`、`generate_content` 等 | P0 |
| **Tool** | 一次实际工具执行；不包含模型作出工具调用决策的过程 | HTTP/DB/进程等 | `execute_tool` | P0 |
| **Guardrail** | 一次输入、输出或中间步骤的安全/质量判定 | 可包含 LLM | 自定义 INTERNAL | P1 |
| **RAG** | 一次检索增强流程容器；是否含生成依真实流程 | Retrieval、Rerank、LLM | 自定义 INTERNAL 容器 | P1 |
| **Retrieval** | 一次实际检索/召回操作 | DB/Vector Search Client | `retrieval` | P1 |
| **Rerank** | 一次排序服务或排序模型执行 | 模型/HTTP Span | 自定义，另挂模型属性 | P1 |
| **Embedding** | 一次向量化调用 | 模型 API | `embeddings` | P1 |
| **Memory** | 一次记忆查找、写入、更新、删除 | 存储操作 | `search_memory`、`create_memory` 等 | P1 |
| **Human** | 人工审核、确认、修改、接管 | 等待与完成事件 | 自定义 INTERNAL | P1 |
| **Skill** | 一项 Skill 加载/应用流程 | Tool、LLM、Agent | 执行步骤可复用 `gen_ai.skill.*` | P1 |
| **Custom** | 语义无法归于上述类型的节点 | 依具体操作 | 自定义操作名称 | 仅允许注册后使用 |

**分类判定规则**：

- LLM 完成的 Plan/推理仍是 **LLM** Span；如果存在独立的可计时“规划阶段”而非一次推理本身，可加自定义内部流程 Span，但不应重复计数。OTel 有 `plan` 操作语义，和平台业务类型不是一回事。
- RAG 是**组合过程**，不能把 Retrieval、Rerank 和 LLM 的耗时与父 RAG 时间直接相加；并行阶段有重叠。
- SubAgent 归为 Agent，而不是额外创建没有独立执行语义的 SubAgent 类型；用 `agentobs.agent.role=subagent`、`agentobs.run.parent_id` 标识。
- Skill 如果只是加载一个文件，可只记录 Tool/文件访问 Span 并加 Skill 属性；只有确实存在独立的 Skill 调度与执行生命周期时才建 Skill 容器，避免重复计算。
- Guardrail 如果通过模型执行，容器是 Guardrail，内部真正的推理调用为 LLM；若无独立环节，可用事件/属性代替容器。
- Workflow 的条件、循环等内部控制节点只有耗时或状态具有诊断价值时才生成 Span；否则使用 Event。

### 2.1 Span 的共用最小字段

| 字段 | 级别 | 说明 |
|---|---|---|
| `trace_id`, `span_id`, `parent_span_id` | P0 | 原生 OTel 标识；parent 可不存在 |
| `name`, `kind`, `start_time`, `end_time`, `status` | P0 | 原生 OTel 生命周期 |
| `agentobs.span.type` | P0 | 业务类型，开放枚举但受治理 |
| `agentobs.run.id`, `agentobs.attempt.id` | P0 | 业务 Run 与本次执行尝试 |
| `agentobs.project.id`, `agentobs.tenant.id` | P0 | 可信源绑定的项目及租户归属 |
| `gen_ai.conversation.id` | 按条件 | 会话标识；存在会话时采集 |
| `agentobs.execution.status` | P0 | `running/success/failed/cancelled/timeout/rejected`，与 OTel Status 分开 |
| `agentobs.step.index` | 可选 | AgentLoop 步骤序号 |
| `agentobs.run.parent_id` | 子任务时 | 任务业务关联，与 OTel ParentSpan 不同 |
| `agentobs.schema.version` | P0 | 自研属性规范版本 |

Resource 使用 `service.name`、`service.version`、`service.instance.id`、`deployment.environment.name` 等标准字段。执行上下文经 W3C `traceparent` / `tracestate` 传播。跨 Trace 的恢复/异步关联使用 Span Link；不能把 Link 假装成树形 Parent。

## 3. 结果可解释（对应 3.6）

### 3.1 目标与边界

这里的“可解释”应定义为**可核对的输出形成证据**：模型请求参数和输出、检索片段、工具结果、被引用的来源、人工介入以及上下游关联。它能支持事后说明和复核，但不能证明模型内部思考完全可见，也不能仅靠 Trace 证明答案正确。

### 3.2 规范字段映射

| 你提供的业务字段 | 推荐 OpenTelemetry / 平台字段 | MVP 建议 | 备注 |
|---|---|---|---|
| `requestModelProviderName` | `gen_ai.provider.name` + `agentobs.model.service_provider_name`（如需要） | P0 | provider 语义是遥测格式/提供方标识；商业平台显示名可能不是同一概念 |
| `requestModelName` | `gen_ai.request.model` | P0 | 模型请求标识 |
| `responseModelName` | `gen_ai.response.model` | P0，若可取 | 实际响应模型 |
| `responseId` | `gen_ai.response.id` | 可取时 | 模型返回的响应 ID |
| `toolName` | `gen_ai.tool.name` | P0 | 实际工具名称 |
| `toolDescription` | `gen_ai.tool.description` | P1 | 注意内容大小和敏感信息 |
| `retrievedQuery` | `gen_ai.retrieval.query.text` | P1，默认脱敏/按需 | 原文可能敏感 |
| `retrievedTopK` | `gen_ai.retrieval.top_k` | P1 | 请求的 TopK，不等于实际返回数量 |
| `retrievedDocs` | `gen_ai.retrieval.documents` | P1 | 推荐至少包含稳定文档 ID、评分，可附平台文档版本与片段 ID |
| `retrievedStore` | `gen_ai.data_source.id`（单一）或 `agentobs.retrieval.store_ids`（多源） | P1 | 多源不能用单字符串伪装 |
| `citation` | `agentobs.answer.citations` 或专用 `agentobs.answer.citation` Event | P1 | 包含输出片段到来源文档/Chunk 的映射 |
| `memoryOperationName` | `gen_ai.operation.name` 的 `search_memory/create_memory/update_memory/upsert_memory/delete_memory` | P1 | 依据真实记忆操作 |
| `interventionType` | `agentobs.human.intervention.type` | P1 | `review/confirm/modify/reject/takeover` |
| `interventionReason` | `agentobs.human.intervention.reason` | P1，脱敏 | 人工原因与决策结果分开 |

**对最终引用补充的推荐证据对象**（放在受限内容区或经治理的结构化属性中）：

```json
{
  "answer_segment": "本次回答第2段",
  "retrieval_span_id": "span-retrieve-2",
  "document_id": "doc-201",
  "document_version": "2026-10-20",
  "chunk_id": "chunk-17",
  "source_uri": "kb://knowledge-3/doc-201",
  "retrieval_score": 0.86,
  "citation_status": "linked"
}
```

至少保证 **答案引用 → Retrieval Span → 文档 ID + 版本 + Chunk ID → 知识库 ID/版本** 可以导航。没有引用关系时应显示“无可追溯引用”，不能把召回文档简单等同于答案证据。

### 3.3 对应 UI

在 Span Inspector 增加 **证据（Evidence）** 页签：

- LLM：Prompt / 输入输出摘要、模型名、模型参数、最终响应、引用的证据数。
- Retrieval：Query、Store、TopK、实际返回数、文档列表（文档 ID、标题、分数、版本、Chunk、来源）。
- RAG：阶段级摘要，支持点击 Retrieval/Rerank/LLM 子 Span。
- Final Answer：答案段落与引用来源交互跳转，引用文档可跳到原检索 Span。
- Tool：参数、实际结果、结果摘要、下游哪些模型调用消费了此结果。

## 4. 过程可追溯（对应 3.7）

**目标**：回答“这次执行到底使用了哪个版本的模型、Prompt、工具、Agent、知识库与配置”，并可按资产版本筛选 Trace。

### 4.1 LLM 参数及结果字段完整映射

| 规范字段 | OTel / 自定义字段 | 备注 |
|---|---|---|
| `requestModelVersion` | `agentobs.model.version` | 如果模型名不含部署修订版则记录单独版本 |
| `requestModelMaxTokens` | `gen_ai.request.max_tokens` | 可用时 |
| `requestModelTemperature` | `gen_ai.request.temperature` | 可用时 |
| `requestModelTopP` | `gen_ai.request.top_p` | 可用时 |
| `requestModelTopK` | `gen_ai.request.top_k` | 可用时 |
| `requestModelFrequencyPenalty` | `gen_ai.request.frequency_penalty` | 可用时 |
| `requestModelPresencePenalty` | `gen_ai.request.presence_penalty` | 可用时 |
| `requestModelSeed` | `gen_ai.request.seed` | 可用时 |
| `requestModelStopSequences` | `gen_ai.request.stop_sequences` | 数组 |
| `requestModelReasoningLevel` | `gen_ai.request.reasoning.level` | 可用时 |
| `requestModelExtraParams` | `agentobs.model.extra_params_json` | 过滤密钥、控制大小并记录 schema |
| `responseModelFinishReasons` | `gen_ai.response.finish_reasons` | 数组；不要写成单一字符串 |
| `promptId` | `agentobs.prompt.id` | 模板稳定 ID |
| `promptText` | `gen_ai.system_instructions` 或 `gen_ai.input.messages` 等 | **仅按需采集**；区分模板和渲染后实际输入 |
| `promptVariable` | `gen_ai.prompt.variable.<name>` | 值默认脱敏，禁止无控制地输出 |
| `promptVersion` | `gen_ai.prompt.version` | 另可用 `gen_ai.prompt.name` |
| `knowledgeId` | `gen_ai.data_source.id` / `agentobs.knowledge.id` | 多库时逐个关联 |
| `knowledgeVersion` | `agentobs.knowledge.version` | 重要的资产追溯字段 |
| `toolId` | `agentobs.tool.id` | 工具注册表稳定 ID |
| `toolVersion` | `agentobs.tool.version` | 不同部署修订需区分 |
| `agentId` | `gen_ai.agent.id` | 可用时 |
| `agentVersion` | `gen_ai.agent.version` | 可用时 |

**补充字段**：`agentobs.workflow.version`、`agentobs.guardrail.policy.id/version`、`agentobs.skill.id/version`、`agentobs.runtime.image_digest`、`agentobs.config.revision`、`agentobs.prompt.rendered_sha256`、`agentobs.asset.snapshot_id`。这些字段只在确有资产版本系统、具有可信来源时记录，不能合成虚假的版本。

**MVP 资产视图**：Span Inspector 的 **Assets** 页签展示实际使用的模型、Prompt、知识库、工具、Agent 及其版本；点击资产可搜索“所有使用同版本的 Trace”。若外部资产已不可读取，保留 ID/版本摘要并明确显示不可用，不用最新版本替代历史版本。

**关系语义**：一个 Root Run 可以跨多个 Attempt/Trace；`trace_id` 是技术链路，`run.id` 是业务任务；Checkpoint 恢复时开启新的 Attempt，使用 Link 指向历史 Trace，避免人为延长已结束的 Span。

## 5. 异常可定位（对应 3.8）

仅有错误码、堆栈和红色节点不够，必须能识别“**发生点、传播路径、业务影响、恢复处置**”。

| 层次 | 需要记录/展示的内容 | 实现方式 |
|---|---|---|
| 发生点 | 哪个 Span、哪个 Agent/Tool、错误类型 | OTel `status=ERROR`、`error.type` |
| 原始异常 | 诊断错误信息，必要时脱敏堆栈 | `exception` Event；`exception.type/message/stacktrace` |
| 阶段 | 请求前、模型流式、工具执行、RAG 召回、审查等 | `agentobs.error.phase` |
| 影响 | 引起了哪个 Run 失败、结果缺失、工具部分失败 | `agentobs.error.impact`、关联 Run |
| 传播 | 原始错误 Span → 调用方 → 最终失败节点 | `agentobs.error.root_span_id` / `caused_by_span_id` |
| 处置 | 是否重试、降级、人工处理、最终恢复 | `agentobs.recovery.action`、`agentobs.recovery.outcome` |

**异常语义必须避免误报**：

- 原始工具调用失败，应在工具 Span 上记录 ERROR；若上层捕获并成功恢复，整个 Agent Run 仍可成功，不应把根 Span 自动判错。
- OTel 建议在异常导致 Span 最终失败时记录 `exception` Event；被捕获并完全恢复的内部错误可使用自定义重试/恢复 Event 与诊断属性，避免每次瞬态重试都被误认为最终失败。
- 所有异常必须做消息和堆栈脱敏；可关联内部日志但不把明文凭据带入 Trace。
- 三类状态独立展示：**技术状态（OTel）**、**业务状态（Run）**、**数据完整性（Span 是否缺失）**。

**异常 UI**：Trace 详情顶部“错误摘要（首个根因错误、传播路径、是否已恢复）”；左侧树红色标记原始错误，橙色标记已恢复错误；Inspector 的 Errors 页签显示错误事件、重试序号和影响范围，支持跳转到根因 Span。

## 6. 性能可分析（对应 3.9）

### 6.1 指标分层

| 维度 | 核心指标 | 来源/注意事项 | 优先级 |
|---|---|---|---|
| Run | 总时长、P50/P95/P99、成功率、取消率 | Run 摘要，不依赖采样后的详细 Trace | P0 |
| Span | duration、耗时占比、父子关系 | `end-start`；父子 Span 可能重叠，禁止简单累加 | P0 |
| LLM | TTFT、总时长、输入/输出/推理 Token | `gen_ai.response.time_to_first_chunk`、`gen_ai.usage.*` | P0 |
| Tool | 耗时、超时率、失败率、重试次数 | Tool Span、错误事件 | P0 |
| 运行效率 | AgentLoop 次数、Tool 调用次数、无效循环 | 自研 `agentobs.*` | P0 |
| 吞吐与流式 | TPOT、生成速率、流式中断率 | 需要更细粒度的时间戳和提供方 Usage | P1 |
| 检索质量 | Retrieval/Rerank 耗时、返回数、TopK、空结果率 | Retrieval 子 Span | P1 |
| 队列与资源 | SubAgent 等待、审批时间、CPU/RSS | Agent Runtime 及容器 Metrics | P1 |
| 成本 | 按模型、Run、Agent 的估算成本 | 价格版本 + Usage；不等于账单金额 | P1 |

TTFT 与 OTel 的 `gen_ai.response.time_to_first_chunk` 要区分：标准字段指**首个有效输出 Chunk**，可能包含非可见的推理内容，并不必然等于用户看到的第一个文本 Token。若业务必须分析首个可见文本延迟，另记录 `agentobs.llm.time_to_first_visible_text_ms`。

TPOT 必须定义口径。建议仅在具有可靠的首末输出时间戳和实际输出 Token 数时给出近似值：

`TPOT ≈ (last_output_time - first_output_time) / max(output_tokens - 1, 1)`

同时标记 `metric_quality=estimated`；按 Streaming Chunk 时间估计无法等价于真实逐 Token 间隔。如没有可靠时间戳，就不要显示精确 TPOT。

### 6.2 性能 UI

- **Trace 总览**：总时长、LLM Calls、Tool Calls、Token、关键异常、成本（估算）。
- **瀑布图**：真实起止时间、同一坐标轴、多 Span 并行；缩放与选择高亮。
- **Performance 页签**：选中 Span 的时长、TTFT、Token、Retry、排队/等待、运行 CPU/RSS（如有）。
- **热点分析**：P0 根据 Span 类型和耗时聚合；P1 支持 Critical Path 和跨 Trace 对比。
- **数据质量标识**：无 Usage、未采集流式数据、部分 Span 缺失时，显示“不可计算/数据不足”，而非 0。

## 7. Trace Explorer 与 Trace Detail 交互扩展

### 7.1 Trace 列表页

P0 列：时间、Agent、Run ID、Status、Duration、Span 数、错误数、LLM/Tool 调用数、Token。筛选条件：时间、项目、Agent、模型、Span 类型、状态、错误类型、Run/Trace/Session ID；支持从模型版本或 Tool 版本反查相关 Trace（P1）。

### 7.2 Trace Detail 组合布局

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ Trace Header: Agent / Run / Attempt / Status / Duration / Tokens / Error │
├────────────────────────┬────────────────────────┬────────────────────────┤
│ Span Tree              │ Waterfall              │ Span Inspector         │
│ Agent                  │ ████████████           │ Overview               │
│  ├ LLM                 │  ████                  │ Input / Output         │
│  ├ RAG                 │   ███████              │ Evidence (P1)          │
│  │ ├ Retrieval         │   ██                   │ Assets (P1)            │
│  │ ├ Rerank            │     ██                 │ Errors                 │
│  │ └ LLM               │       ███              │ Performance            │
│  ├ Tool                │       ███              │ Events / Links / Raw   │
│  └ Human               │          ███           │                        │
└────────────────────────┴────────────────────────┴────────────────────────┘
```

左树右瀑布**共用同一行数据模型**，选中 Span 后 Inspector 同步刷新；跳转引用文档/Asset 时仍保留来源 Span 上下文；错误定位支持原始错误、传播错误、已恢复错误三态。

### 7.3 每类 Span 的默认详情

| 类型 | 第一屏优先展示 |
|---|---|
| Agent/Workflow | 总览、子步骤概况、模型/工具调用总数、结果状态 |
| LLM | 请求/响应模型、Prompt/Output 摘要、Token、TTFT、参数、Prompt 版本 |
| Tool | 工具名/版本、输入参数摘要、输出结果、耗时、错误和重试 |
| RAG | 检索→排序→生成的阶段信息，引用文档数 |
| Retrieval | Query、知识库版本、TopK、返回文档列表及来源 |
| Rerank | 排序模型、候选数、排序前后结果摘要 |
| Embedding | 模型、输入项数、向量维度、耗时 |
| Memory | 操作名称、记录 ID/数量、目标存储与版本 |
| Guardrail | 策略版本、检测阶段、结论、阻断/放行和理由 |
| Human | 介入类型、等待时长、审批结论、脱敏原因 |
| Skill | Skill 名称、版本、加载路径、运行的子 Tool/LLM |

## 8. MVP 划分与验收

### P0（第一版必须）

1. **Span 类型注册与展示**：支持所有约定类型的接收、识别、颜色/图标与兜底展示；真正埋点优先覆盖 Agent、LLM、Tool、现有 Runner 的控制流。
2. **规范字段适配层**：将业务规范字段转换为标准 GenAI 和 `agentobs.*`；保留 schema/version；未知类型和字段不丢失。
3. **基础 Trace 诊断**：列表筛选、Tree + Waterfall、Inspector、状态、异常、Events、Links。
4. **模型与工具的可解释数据**：模型/provider/Token、工具名/状态、请求/响应摘要；支持脱敏和授权采集。
5. **最低限度资产追踪**：记录模型、Agent、Tool、Prompt 的 ID/版本（可用时）。
6. **异常与性能**：工具/模型失败定位、重试/恢复标识、P95、LLM TTFT、Token，指标不依赖详情采样。
7. **平台可靠性**：异步上报、队列容量限制、丢弃监测、权限隔离、默认敏感内容关闭。

### P1（紧接 MVP）

- RAG/Retrieval/Rerank/Embedding 的专项内容展示及引用证据跳转。
- Memory、Human、Guardrail、Skill 专项详情及策略/资产版本。
- Prompt/知识库/工具的版本反向查询。
- TPOT 估算、关键路径、细粒度资源分解。
- 基础质量反馈、规则评测和历史 Trace 对比。

### 关键验收用例

| 用例 | 期望结果 |
|---|---|
| Agent → LLM → Tool → LLM | 正确的父子关系及真实耗时，决策和执行不混淆 |
| RAG → Retrieval → Rerank → LLM | 文档来源可追溯，引用可点击回检索 Span |
| Tool 首次超时、重试成功 | Tool 错误保留，Agent Run 最终成功，标记恢复成功 |
| Agent 多次恢复 | Run 统一、Attempt/Trace 分离、Link 可跳转 |
| LLM 流式取消 | 有明确中断状态，不伪造完整输出与 TPOT |
| Prompt/知识库版本变化 | 不同版本的 Trace 可区分，不能用最新资产覆盖历史 |
| 敏感输入存在 | 默认无明文；未授权用户不能通过 Inspector/Raw 查看 |
| Span 缺失或无 Usage | 明确标注“不完整/不可计算”，不填 0 |

## 9. 落地注意点

- **用户提供的“是/必填”是业务规范的要求，不等于任意执行环境总能获得该值。** 采集应通过“适用时必须、未知时显式缺失”处理，不能为了通过校验填造假值。
- **业务规范的 `object`/`array` 不意味着 Python OTel Attributes 天然接受任意嵌套对象。** 需要兼容所采用 SDK/OTLP 的 AnyValue 表达能力、序列化与后端索引限制，较大/敏感载荷应仅存受控引用。
- **Trace 数据采样不能用于无偏的 Run 成功率和调用量统计。** 独立记录完整 Run 摘要或原生 Metrics，保持分母准确。
- **变更管理**：锁定一个 GenAI 语义约定版本；变更映射需兼容老 Trace；元数据里记录平台 schema 版本。
- **关键安全约束**：Prompt 文本、参数、Tool 输出、知识文档、人工理由可能含隐私、凭据和商业机密，必须默认脱敏、访问鉴权、最小保留与审计。

## 10. 参考标准（核对日期：2026-11-12）

- [OpenTelemetry Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/)
- [OpenTelemetry GenAI Client Inference](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/client-inference.md)
- [OpenTelemetry GenAI Agent Spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md)
- [OpenTelemetry GenAI Spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md)
- [OpenTelemetry Execute Tool](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/execute-tool.md)
- [OpenTelemetry GenAI Registry](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/registry/attributes/gen-ai.md)
- [OpenTelemetry Exceptions](https://opentelemetry.io/docs/specs/otel/trace/exceptions/)
