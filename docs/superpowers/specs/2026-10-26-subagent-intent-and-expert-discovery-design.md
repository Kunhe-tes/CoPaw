# SubAgent 意图开放与专家自主选择

状态：已确认。用户已确认 Q1–Q13，并授权按目标文件实现。

## 目标

允许用户通过明确的子代理关键词开放 Main Agent 的委派工具，并由 Source 级配置控制当前 Agent Profile 的已有专家是否可供 Main Agent 自主选择。保留显式选择专家的独立入口。

## 已确认决策

2026-10-26，用户确认第一轮 Q1–Q4 均选择 A：

1. “主 Agent 创建专家”指提供 Run-scoped SubAgent Definition 并启动临时子代理；不保存、不自动启用持久化专家，不增加专家 CRUD 工具。
2. 自主选择的专家范围为当前租户、当前 Agent Profile 的有效且已启用 Agent-owned 专家，包括已接收的社区专家；不跨 Profile 汇总，不直接调用社区市场条目。
3. 开关放在现有系统配置页，沿用 Source 级管理与配置作用域。该 Source 下各租户遵循相同开关，但专家内容仍按租户与 Profile 隔离。
4. 当前用户消息以固定关键词表达子代理意图，采用确定性判定而非语义分类。候选词为“子代理”“子智能体”“subagent”“sub-agent”，英文忽略大小写；普通“专家”不作为泛化触发词。命中仅开放工具，不强制启动。
5. 开关控制已有专家的自主可见性；关闭不会阻止临时子代理，也不会阻止用户显式指定专家。开关开启本身不替代子代理意图。

同日，用户确认第二轮 Q5–Q10 均选择 A：

6. 新 Source 级开关默认关闭；未配置时不向 Main Agent 开放 Agent-owned 专家自主发现。
7. 开关只控制 Agent-owned 专家。当前有效 Skill 所附带的 Skill-owned Definition 在意图门禁开放后仍可列出、按精确限定名启动，不因开关关闭而隐藏。
8. 临时子代理沿用已有能力：继承父 Agent 当前启用的内置工具和 MCP，不自动加载 Skill，不为启动请求新增依赖选择参数。实际权限继续受模式、SubAgent 策略、Tool Guard 和审批规则限制。
9. 显式指定专家仅指聊天专家选择器产生的 `selected_expert_id`；普通文字点名不绕过开关。显式选择优先，目录仅含所选专家，不可用时报告错误，不替换其他专家或回退临时子代理。
10. `enable_subagents=true` 是与关键词等价的结构化委派意图，不绕过专家自主选择开关。无需调用方向用户文本拼接关键词。
11. 普通聊天、Plan、Goal 都适用上述意图入口，保留原有权限及显式专家互斥规则；Plan 中的子代理继续只读，所有子代理仍禁止嵌套委派。

## 已确认行为矩阵

以下“意图”指关键词命中或结构化启用；显式专家选择只适用于现有模式允许的入口。

| 显式选择 | 委派意图 | 自主选择开关 | 可启动范围 |
| --- | --- | --- | --- |
| 有 | 任意 | 任意 | 仅所选有效已启用专家，保留既有强制执行语义 |
| 无 | 有 | 关闭或未配置 | 临时定义，以及当前有效 Skill 自带定义 |
| 无 | 有 | 开启 | 临时定义、当前有效 Skill 自带定义、当前 Profile 已启用专家 |
| 无 | 无 | 任意 | 不提供 start；存在当前会话运行记录时提供 get/wait/cancel，Goal 另沿用其持久意图 |

隐去专家应同时排除目录展示与名称解析，不能只移除工具描述而仍按名称解析到隐藏专家。未知名称附带 instruction 的临时定义不读取或复制隐藏专家配置。

## 现有代码与领域约束

- `src/swe/agents/react_agent.py` 的 `_background_subagent_registration_blocked` 当前要求 `selected_expert_id`，尚不支持上述关键词入口；`enable_subagents` 虽被 Runner 传入，目前并非该门禁的放行条件。
- `src/swe/agents/tools/subagent_background.py` 已有精确名称解析及未知名称附带 instruction 的 run_scoped fallback。当前显式选择分支只允许所选专家，不允许临时 fallback。
- `src/swe/app/routers/experts.py` 和 `AgentOwnedDefinitionRepository` 以当前 Profile 工作区定位专家。
- `src/swe/app/source_system_config/` 与 `console/src/pages/SystemConfigPage/` 已有 Source 级功能开关注册机制。
- 社区专家继续遵循 ADR 0028 的冻结私有依赖约束，不把所绑定 Skill/MCP 注册为父 Agent 的通用资源。自主选择入口需要核对并衔接现有运行快照与 Chat 私有视图。
- 现有 SubAgent 工具只供 Main Agent 使用；嵌套委派、Tool Guard、审批和租户隔离不因意图开放而扩大。

## 最终确认的运行边界

12. 关键词使用当前真实用户文本的字面匹配，不排除否定、引用或代码片段；只开放工具，Main Agent 仍须遵守“不使用”的用户指令。英文忽略大小写，不扫描历史消息、工具输出或模型生成文本。
13. 当前 Chat／会话有保留的运行记录时，后续无新意图也提供 get/wait/cancel，不提供 start。所有管理工具按当前 Chat／会话过滤，不能仅依靠 Profile 级 scope。缺少可靠会话身份时不开放跨轮管理。
14. Goal 委派意图随 Goal 保存并在后续自动轮、恢复及重启后继续有效，不传播到其他 Goal 或普通 Chat；后续真实用户 Steering 首次授权也须持久化并刷新下一轮工具。
15. GoalSnapshot 增加 subagent_delegation_enabled=false，沿用 snapshot_json，无新增数据库列；旧快照缺省关闭。Goal 创建请求可选 enable_subagents=false；模型生成的 Contract 或摘要不能产生用户授权。
16. Source 开关和可见目录在后续主 Agent 轮次重新解析；已启动运行及其权限和依赖快照不改变。

## 沿用的专家依赖语义

自主选择的本地专家沿用其声明的依赖和模型解析；社区专家沿用冻结私有依赖、Chat 隔离及运行快照，不把绑定的 Skill/MCP 加入 Main Agent 通用资源目录。需要在自主选择启动处衔接现有 Chat 私有视图，而非从父 Agent 同名资源回退。

## 后续实现的验证边界

- 门禁：四个固定词、大小写、结构化启用、无意图、Main Agent 身份、禁止子代理与 completion judge 委派。
- 目录与解析：开关默认关闭、Source 隔离、Profile 隔离、Skill-owned 独立生命周期、启用/禁用专家、隐藏专家同名请求、显式选择优先与不可用错误。
- 模式：普通聊天、Plan 只读、Goal 意图传播与后续轮、既有互斥规则。
- 依赖：临时定义不加载 Skill、本地专家声明、社区专家冻结私有依赖及同名隔离、已有运行快照不因开关变化而改写。
- 管理页：Source 级默认值、读写持久化与现有管理员权限。

## 文档兼容性

更新 `CONTEXT.md` 中 Explicit SubAgent Intent Gate 与 Explicit Expert Selection 的冲突描述，并增加 Expert Autonomous Discovery Switch 术语。保留既有临时定义与持久化专家分离的领域边界；本轮不重新引入专家注册工具。

ADR 0028 原有“Main Agent routing never discovers experts implicitly”不再能描述本轮已确认的配置控制自主选择。ADR 0041 记录这一可见性边界的演进，并保留 ADR 0028 的冻结私有依赖、发布与分发约束。
