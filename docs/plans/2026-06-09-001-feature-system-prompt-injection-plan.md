---
title: Chat And Source System Config Prompt Injection
status: active
created: 2026-06-09
origin: user request
depth: standard
---

# Chat And Source System Config Prompt Injection Plan

## Problem Frame

CoPaw 当前 system prompt 主要来自工作区提示词文件配置：
`AgentProfileConfig.system_prompt_files` 经过
`swe.agents.prompt.build_system_prompt_from_working_dir` 生成基础 system
prompt，`SWEAgent._build_sys_prompt` 再追加运行时环境上下文和 source 系统配置相关提示词。

新功能要增加一条直接的系统提示词注入通道，但持久化配置入口不是
`/agent/running-config`，而是“系统设置 -> 系统特性配置”，也就是
source system config：

- chat 接口调用可以携带本次请求级 system prompt 注入内容。
- 系统特性配置可以保存 source 级 system prompt 注入内容。
- 实际运行时同时使用两边内容，按并集去重后注入到本次 Agent system prompt。

## Requirements

- R1: chat 接口入参支持传入系统提示词注入内容，只影响本次调用，不写入系统特性配置。
- R2: 系统特性配置支持保存 source 级系统提示词注入内容，并通过当前 source 的配置接口读写。
- R3: Agent 实际运行时取“source 系统特性配置注入内容”和“chat 请求注入内容”的并集。
- R4: 并集要稳定去重：过滤空白项，保留首次出现顺序，同一段文本只注入一次。
- R5: source 系统特性配置来源先于 chat 请求来源，chat 请求作为本次调用的补充项追加。
- R6: 不能破坏现有 `system_prompt_files` 的提示词文件机制，也不能把请求级注入持久化。
- R7: 系统特性配置的默认值、继承状态、显式覆盖和保存校验要保持现有页面语义。

## Scope

In scope:

- source system config 增加 `system_prompt_injections` 配置项。
- chat 请求结构和前端 API 类型增加请求级字段。
- runner 创建 `SWEAgent` 前合并 source 配置和请求级注入内容，并追加到 system prompt 的运行时上下文中。
- “系统设置 -> 系统特性配置”页面增加可编辑的系统提示词注入配置块。
- 添加覆盖 source 配置归一化、runner 合并、前端 registry/page 的测试。

Out of scope:

- 修改 Agent 运行配置页 `/agent-config`。
- 修改 `/agent/running-config` 或 `AgentsRunningConfig`。
- 重写提示词文件选择能力。
- 引入新的数据库表或迁移。
- 将请求级注入内容同步到 source 系统特性配置。
- 对 prompt injection 安全策略做完整治理设计；本次只做字段归一化和注入边界清晰化。
- 变更模型 provider 或消息协议底层实现。

## Existing Entry Points

- `console/src/layouts/Sidebar.tsx`
  - `system-settings` 下面的 `system-config-page` 是“系统特性配置”菜单项。
- `console/src/layouts/MainLayout/index.tsx`
  - `/system-config-page` 路由渲染 `SystemConfigPage`。
- `console/src/pages/SystemConfigPage/index.tsx`
  - 当前 source 系统特性配置页面，负责加载、编辑、保存和删除 source config。
- `console/src/pages/SystemConfigPage/registry.ts`
  - 前端读取、写入、校验 source config 各配置块。
- `console/src/api/types/sourceSystemConfig.ts`
  - 前端 source system config 类型。
- `src/swe/app/source_system_config/models.py`
  - `SourceSystemConfig` 是 source 系统配置载荷模型。
- `src/swe/app/source_system_config/registry.py`
  - 后端 source 系统配置默认值、归一化、裁剪和运行时读取 helper。
- `src/swe/app/source_system_config/*`
  - 当前 source config 的加载、持久化和有效配置合成入口。
- `src/swe/app/runner/runner.py`
  - `_prepare_query_runtime` 生成 `env_context`。
  - `_create_agent_for_query` 将 `env_context` 和 `request_context` 传给 `SWEAgent`。
- `src/swe/agents/react_agent.py`
  - `SWEAgent._build_sys_prompt` 组装最终 system prompt，并追加 `env_context`。
- `console/src/api/types/agent.ts`
  - `AgentRequest` 前端类型，可增加请求级 `system_prompt_injections`。

## Key Decisions

- D1: 新字段命名为 `system_prompt_injections`，类型为 `list[str]` / `string[]`。
  该字段用于 source 系统特性配置和 chat 请求入参。
- D2: `system_prompt_injections` 是直接注入的提示词片段，不是文件名，也不参与
  `system_prompt_files` 的文件加载逻辑。
- D3: source 系统特性配置里使用顶层字段
  `system_prompt_injections: string[]`。不要放入 `feature_switches`，因为它不是 boolean switch。
- D4: 合并顺序为 source config 的 `system_prompt_injections` 在前，
  request 的 `system_prompt_injections` 在后。去重按归一化后的完整文本精确匹配。
- D5: 归一化规则为 `str(value).strip()`，过滤空字符串，保留换行和正文内部空白。
- D6: 注入位置放在 runner 层生成的 `env_context` 末尾，通过
  `SWEAgent._build_sys_prompt` 现有追加机制进入 system prompt。这样不会改动基础
  prompt 文件构建，也便于测试捕获。
- D7: 注入块使用固定标题，例如 `[System prompt injections]`，每段内容分隔渲染，
  避免和普通用户输入混在一起。
- D8: 默认值为 `[]`。如果 source 没有显式覆盖，运行时读取默认空列表。

## Implementation Plan

### 1. Source System Config Schema And Normalization

Files:

- `src/swe/app/source_system_config/registry.py`
- `src/swe/app/source_system_config/models.py`
- `tests/unit/app/test_source_system_config.py`

Tasks:

- 在后端 source config registry 中增加系统提示词注入默认值和 helper：
  - `SYSTEM_PROMPT_INJECTIONS_PATH = ("system_prompt_injections",)`
  - `normalize_system_prompt_injections(value: Any) -> list[str]`
  - `get_system_prompt_injections(config: Any | None) -> list[str]`
- 扩展 `normalize_registered_setting_values` 或在 `SourceSystemConfig._validate_object`
  中调用专用归一化逻辑，确保保存时过滤空项和去重。
- 扩展默认 config payload，让有效配置始终包含
  `system_prompt_injections: []`。
- 扩展 prune 逻辑：显式覆盖如果等于默认空列表，应能裁剪掉，保持继承状态语义。

Tests:

- 默认 source config 包含空列表。
- 旧配置缺少该字段时，合成后的有效配置返回 `[]`。
- 包含空字符串、空白字符串、重复字符串时归一化为去重后的列表。
- 多行文本内部换行不被破坏。
- 显式保存空列表时可以按默认值裁剪，页面回到继承状态。

### 2. Chat Request Contract

Files:

- `console/src/api/types/agent.ts`
- backend tests under `tests/unit/app/`

Tasks:

- 在前端 `AgentRequest` 类型上增加可选字段
  `system_prompt_injections?: string[]`。
- 后端 runner 通过 `getattr(request, "system_prompt_injections", None)` 读取。
- 如果 channel native 请求只把扩展字段放在 `channel_meta`，runner helper 同时检查
  `channel_meta["system_prompt_injections"]`，保证 chat API 和 channel 构造都能透传。

Tests:

- 请求对象直接带 `system_prompt_injections` 时能被 runner 读取。
- 请求对象只在 `channel_meta` 带该字段时也能被 runner 读取。

### 3. Runtime Union Injection

Files:

- `src/swe/app/runner/runner.py`
- `tests/unit/app/test_runner_system_prompt_injections.py`
- `tests/unit/app/test_runner_hook_runtime.py` as reference only

Tasks:

- 从 source system config 读取持久化注入内容：
  - 使用 `get_current_source_system_config()` 或 runner 当前已有的 source config 载荷。
  - 通过新 helper `get_system_prompt_injections(config)` 得到规范化列表。
- 增加 runner 小 helper：
  - `_request_system_prompt_injections(request: Any) -> list[str]`
  - `_merge_system_prompt_injections(*sources: Any) -> list[str]`
  - `_with_system_prompt_injections(env_context: str, injections: list[str]) -> str`
- 在进入 `SWEAgent` 前合并：
  - source system config 的 `system_prompt_injections`
  - request 或 `channel_meta` 上的 `system_prompt_injections`
- 将合并结果追加到 `env_context`，保持 hook additional context 的现有行为不变。

Tests:

- 只有 source 系统特性配置时，`_FakeAgent.last_env_context` 包含配置提示词。
- 只有请求入参时，`_FakeAgent.last_env_context` 包含请求提示词。
- 两边都有且有重复时，只出现一次，顺序为 source 配置项先、请求项后。
- 没有注入内容时，`env_context` 不新增空标题。
- hook additional context 仍能和系统提示词注入同时存在。

### 4. System Feature Config UI

Files:

- `console/src/pages/SystemConfigPage/index.tsx`
- `console/src/pages/SystemConfigPage/registry.ts`
- `console/src/api/types/sourceSystemConfig.ts`
- `console/src/pages/SystemConfigPage/index.module.less`
- `console/src/pages/SystemConfigPage/index.test.tsx`
- `console/src/pages/SystemConfigPage/registry.test.ts`

Tasks:

- 在 `registry.ts` 增加前端读取、写入、校验 helper：
  - `readSystemPromptInjections(config)`
  - `writeSystemPromptInjections(config, prompts)`
  - `normalizeSystemPromptInjections(prompts)`
- 在 `SystemConfigPage` 增加独立配置卡片，建议放在“受控功能开关”之后：
  - 标题：系统提示词注入
  - 内容：多段 prompt 列表编辑器或多行编辑器。
  - 保存值保持 `string[]`，不要把多段提示词拼成一个字符串。
- 保持系统特性配置页面现有保存、删除、继承、错误提示流程。
- 补充中文/英文/日文/俄文文案，或按现有页面 defaultValue 模式补足默认文案。

Tests:

- 页面能渲染已有 `system_prompt_injections`。
- 新增、删除、编辑后 `draftConfig.system_prompt_injections` 仍是 `string[]`。
- 空项和重复项在前端保存前被归一化。
- 删除当前 source config 后恢复默认空列表。

### 5. Compatibility And Documentation Cleanup

Files:

- `tests/unit/app/test_source_system_config.py`
- `tests/unit/app/test_task_progress_switch.py` if source config helper imports change
- `analysis/playbook/` only if this change introduces a new reusable troubleshooting entry

Tasks:

- 确认现有 `feature_switches`、`tool_result_compact`、`file_read_truncation`、
  `cron_unread_auto_pause` 的默认合成和裁剪逻辑不回归。
- 不修改 Agent 运行配置分发逻辑；这个功能属于 source 系统特性配置，不属于
  `CONFIG_GROUP_FIELDS`。
- 如果实际实现发现系统提示词注入会成为常见排查入口，再补充 playbook。

## Verification Commands

Backend:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/app/test_source_system_config.py
.\.venv\Scripts\python.exe -m pytest tests/unit/app/test_runner_system_prompt_injections.py tests/unit/app/test_runner_hook_runtime.py
.\.venv\Scripts\python.exe -m pytest tests/unit/app/test_task_progress_switch.py
```

Frontend:

```powershell
cd console
npm.cmd test -- SystemConfigPage
npm.cmd run typecheck
```

Repository review before commit:

```powershell
node .gitnexus/run.cjs detect-changes
git diff --stat
git diff --check
```

## Impact And Risk Notes

- Runtime risk is moderate because `env_context` affects every chat execution path using
  `AgentRunner`.
- Source config risk is moderate because default合成、显式覆盖裁剪和页面继承状态需要保持一致。
- Prompt-file risk is low if implementation only appends to `env_context` and leaves
  `build_system_prompt_from_working_dir` untouched。
- UI risk is moderate；系统特性配置页当前主要是 switch 和数字配置，需要为 `string[]`
  增加清晰的编辑控件。

Before implementation edits, run symbol-specific GitNexus impact checks, for example:

```powershell
node .gitnexus/run.cjs impact SourceSystemConfig
node .gitnexus/run.cjs impact normalize_registered_setting_values
node .gitnexus/run.cjs impact AgentRunner._prepare_query_runtime
node .gitnexus/run.cjs impact AgentRunner._create_agent_for_query
```

## Open Assumptions

- “取并集”按文本精确去重理解，不做语义去重。
- source 系统特性配置项先注入，请求项后注入；如果后续需要请求项优先，应在实现前调整 D4。
- chat 接口传入的是提示词文本片段，不是提示词文件名。
- 请求级注入属于调用方可信输入，本计划不增加新的审批流程。
