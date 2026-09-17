# 场景预设目录 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Source 中管理三级场景目录，并在新 Chat 首次提交时安全快照其市场 Skill/MCP 资源。

**Architecture:** 新增独立的 `scenario_preset` Source 数据模块，提供管理员写接口和终端只读有效树接口。聊天请求通过 `scenario_preset_id` 触发仅一次的提交时解析，结果存入既有 `ChatSpec.meta`，再映射至现有上下文引用与运行器链路；前端只持有场景 ID 和能力原子标记。

**Tech Stack:** Python/FastAPI/Pydantic/MySQL/pytest；React/TypeScript/Ant Design/Vitest。

---

## 文件职责

- `src/swe/app/scenario_preset/{models,store,service,router}.py`：目录模型、数据库、业务规则和 HTTP 路由。
- `src/swe/app/scenario_preset/runtime.py`：首次提交的重校验、市场资源解析、快照编解码与安全日志。
- `src/swe/app/_app.py`、`src/swe/app/routers/__init__.py`：模块和路由注册。
- `src/swe/app/routers/console.py`、`src/swe/app/runner/{models,manager,runner,context_references}.py`：请求参数、Chat 元数据、运行期引用注入。
- `console/src/api/modules/scenarioPreset.ts` 与 `console/src/api/types/scenarioPreset.ts`：控制台 API 协议。
- `console/src/pages/Control/ScenarioPresets/`：三级树、抽屉和资源绑定管理。
- `console/src/components/agentscope-chat/ScenarioPresetSelector/`：新会话三级选择器与能力原子标记。
- `console/src/pages/Chat/{index,welcomeSkillMentions}.ts(x)`、`WelcomeCenterLayout`：选择器接入、首条提交参数透传。

### Task 1: 建立 Source 场景目录的数据模型和迁移

**Files:**
- Create: `src/swe/app/scenario_preset/models.py`
- Create: `src/swe/app/scenario_preset/store.py`
- Test: `tests/unit/app/scenario_preset/test_store.py`

- [ ] 先写失败测试：空 Source 返回空树；创建域/能力/场景产生不同稳定 ID；同级名称规范化重复被拒绝；父节点有子节点时不可删除；移动追加到目标队列末尾。
- [ ] 运行 `venv/bin/python -m pytest tests/unit/app/scenario_preset/test_store.py -v`，确认因模块或行为缺失失败。
- [ ] 最小实现 Pydantic 请求/响应模型与三张按 `source_id` 隔离的表，包含 ID、父 ID、名称、启用、排序、提示草稿和时间戳；绑定表保存稳定市场 ID、类型、最后标签、排序。
- [ ] 用同级 `SELECT ... FOR UPDATE` 和事务实现创建、排序、移动、叶删除；为 `source_id + parent_id + normalized_name` 加唯一性约束。
- [ ] 重新运行上述测试，确认通过。

### Task 2: 目录服务、有效树与管理员路由

**Files:**
- Create: `src/swe/app/scenario_preset/service.py`
- Create: `src/swe/app/scenario_preset/router.py`
- Modify: `src/swe/app/_app.py`
- Modify: `src/swe/app/routers/__init__.py`
- Test: `tests/unit/app/scenario_preset/test_service.py`
- Test: `tests/unit/routers/test_scenario_preset_router.py`

- [ ] 写失败测试：普通用户只能读取已启用完整路径；`manager` 和 `isSuperManager` 可变更当前 Source；非管理员收到 403；停用域或能力使其后代不出现在有效树。
- [ ] 运行相关 pytest，确认失败原因是路由/权限尚未实现。
- [ ] 实现服务层，在 `X-Source-Id` 解析后隔离所有读写；注册 `/scenario-presets/catalog` 的公开有效树和管理员 CRUD、启停、排序、移动、绑定接口。
- [ ] 在 `_initialize_database_backed_modules` 初始化模块并在路由工厂挂载；沿用现有 Source 管理权限 helper。
- [ ] 运行路由和服务测试，确认通过。

### Task 3: 管理页与市场绑定选择

**Files:**
- Create: `console/src/api/types/scenarioPreset.ts`
- Create: `console/src/api/modules/scenarioPreset.ts`
- Create: `console/src/pages/Control/ScenarioPresets/index.tsx`
- Create: `console/src/pages/Control/ScenarioPresets/components/ScenarioDrawer.tsx`
- Modify: `console/src/layouts/Sidebar.tsx`
- Modify: `console/src/layouts/MainLayout.tsx`
- Test: `console/src/pages/Control/ScenarioPresets/index.test.tsx`

- [ ] 写失败测试：空态仅显示创建能力域；管理员创建三级节点；场景抽屉可保存草稿和 Skill/MCP 服务 ID；失效绑定可删除。
- [ ] 运行 `pnpm test:run -- ScenarioPresets`，确认新模块导致失败。
- [ ] 实现 API 客户端；复用市场 Skill/MCP 浏览接口和现有管理页权限。树节点提供创建、编辑、启停、排序、移动，场景抽屉只展示完整 MCP 服务而非工具。
- [ ] 以 `console/DESIGN.md` 的管理控制台样式实现 loading、错误、禁用、长文本和窄容器状态。
- [ ] 运行前端测试与 TypeScript 校验，确认通过。

### Task 4: 新会话三级选择与能力原子标记

**Files:**
- Create: `console/src/components/agentscope-chat/ScenarioPresetSelector/index.tsx`
- Create: `console/src/components/agentscope-chat/ScenarioPresetSelector/useScenarioPreset.ts`
- Modify: `console/src/components/agentscope-chat/WelcomeCenterLayout/index.tsx`
- Modify: `console/src/pages/Chat/index.tsx`
- Modify: `console/src/pages/Chat/welcomeSkillMentions.ts`
- Test: `console/src/components/agentscope-chat/ScenarioPresetSelector/index.test.tsx`

- [ ] 写失败测试：完整路径才显示选择器；初始展开第一条路径而不选场景；选择场景以 `@二级能力` 原子标记加草稿；草稿可清空；删除标记取消 ID；只含标记允许提交；首条提交后不可切换。
- [ ] 运行对应 Vitest 用例，确认失败。
- [ ] 复用受控 contenteditable 的原子 token 技术实现能力标记，但不使用 Skill/MCP token，不提供资源的可见或移除入口。空目录回落为普通欢迎输入。
- [ ] 让 `beforeSubmit` 把待提交 `scenario_preset_id` 交给 `customFetch`，并在成功的首次请求后清空仅前端的待选状态。
- [ ] 运行组件测试、`pnpm test:run` 和 `pnpm build`，确认通过。

### Task 5: 提交时快照、幂等和运行时资源绑定

**Files:**
- Create: `src/swe/app/scenario_preset/runtime.py`
- Modify: `src/swe/app/routers/console.py`
- Modify: `src/swe/app/runner/models.py`
- Modify: `src/swe/app/runner/manager.py`
- Modify: `src/swe/app/runner/runner.py`
- Modify: `src/swe/app/runner/context_references.py`
- Test: `tests/unit/routers/test_console_chat_stream.py`
- Test: `tests/unit/app/scenario_preset/test_runtime.py`

- [ ] 写失败测试：首次请求重校验场景且在 `ChatSpec.meta` 保存快照；相同 Chat ID 重试复用快照；刷新读取快照不查市场；场景已删/停用时拒绝初始化；不可用资源被记录并静默忽略；仅能力标记可发送。
- [ ] 运行 pytest，确认因缺少快照路径失败。
- [ ] 在 console 路由提取 `scenario_preset_id` 并仅针对 Chat 首消息调用 runtime；runtime 按租户/Agent 优先常驻资源、否则临时资源视图解析市场最新版本。保存非敏感来源、稳定 ID、版本、可用性、冻结 MCP 工具集合、锁定 Agent 和目录节点 ID。
- [ ] 将快照化 Skill 转为现有可信上下文指令，将快照 MCP 工具转为现有结构化上下文引用。始终重走现有可见性、凭证、Tool Guard、审批链；绝不写回常驻配置或保存凭证。
- [ ] 以结构化 logger 输出不含草稿、内容、配置和凭证的初始化事件；永久删除路径释放临时连接/快照。
- [ ] 运行全部新增 pytest 与相关 runner/console 路由用例，确认通过。

### Task 6: 回归验证、文档与检查

**Files:**
- Modify: `CONTEXT.md`（仅术语变动时）
- Modify: `docs/adr/0027-scenario-marketplace-resources-are-session-scoped.md`（仅架构决策变动时）

- [ ] 检查实现与设计的验收标准逐项对应，补足遗漏测试。
- [ ] 运行 `venv/bin/python -m pytest tests/unit/app/scenario_preset tests/unit/routers/test_scenario_preset_router.py tests/unit/routers/test_console_chat_stream.py -v`。
- [ ] 在 `console/` 运行 `pnpm test:run`、`pnpm build` 和项目可用的 lint/format 检查。
- [ ] 用 GitNexus `detect_changes` 检查实际受影响符号与执行流；对高风险变更复核上下游。
- [ ] 对控制台改动执行 `copaw-f2e-review` 检查并修复 P0/P1。
- [ ] 只在验证完成后，按逻辑阶段提交不包含用户既有脏改动的文件。

## 自查

- 覆盖：目录管理、权限、空态、三级选择、原子标记、首次提交解析、资源/凭证边界、快照、失效降级、日志和生命周期均有明确任务。
- 一致性：前端字段、API 字段和运行时字段统一使用 `scenario_preset_id`；长期状态统一写入 `ChatSpec.meta`。
- 范围：未引入种子数据、独立审计库、资源可见移除控件或常驻资源写回。
