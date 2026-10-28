# Expert-as-Main Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 实现已确认的 Source 可控专家主执行模式：持久化 Chat 绑定，专家直接处理普通聊天，保留能力边界、审批、停止和关闭开关时的既有路径。

**Architecture:** 复用 Source 配置、Chat API 和主聊天执行链，增加小型绑定模块与按消息冻结的专家执行准备模块，不启动专家 SubAgent worker。当前分支仍使用 JsonChatRepository，绑定原子比较更新沿用其跨进程锁；后续 MySQL 迁移保持同一语义，本功能不实现整套存储迁移。社区专家从最新有效本地版本捕获一致的私有依赖，已开始消息使用原快照。

**Tech Stack:** Python / FastAPI / Pydantic / pytest；React / TypeScript / Zustand / Vitest；共享文件锁、现有 Source 配置存储。

**Status:** 实施完成，本地代码、独立审查与定向回归已完成；真实部署验收边界见交付报告。整体设计及实施由用户于 2026-10-27 确认并授权小步提交。

**Authority:** docs/superpowers/specs/2026-10-27-expert-as-main-execution-design.md；docs/adr/0042-explicit-expert-main-execution-keeps-capability-boundaries.md。

## 执行边界

- 保留原工作区已有修改，在独立 feat/expert-as-main worktree 实施；按用户授权小步提交并独立审查，不推送或创建 PR，不全局 stash，不重构无关代码。
- 每个既有函数/类/方法修改前，执行精确符号的 GitNexus upstream impact，向用户报告调用者、受影响流程和风险；HIGH / CRITICAL 先告知。提交前执行 detect_changes。
- 索引过期时运行 npx gitnexus analyze --index-only；图和源码交叉核对，FTS 降级不能解释成没有依赖。
- 普通函数复杂度建议不超过 15，参数建议不超过 7，重复错误代码/文案集中定义。
- 前端实施前读取 console/DESIGN.md 和适用 copaw-f2e-review 技能，沿用现有样式、统一保存和错误处理。
- 只覆盖普通 Chat。原专家 SubAgent、自主发现开关、Plan / Goal 规则及市场发布/分发均不扩大范围。

## 文件与职责

| 文件 | 职责 |
| --- | --- |
| src/swe/app/source_system_config/registry.py | Source 开关注册、缺省与运行时读取 |
| console/src/pages/SystemConfigPage/registry.ts、workbench.ts | 开关文案、归组和统一保存 |
| 新增 src/swe/app/runner/expert_binding.py | 绑定模型、服务端状态、统一冲突异常、授权校验 |
| src/swe/app/runner/repo/base.py、repo/json_repo.py | 原子比较更新、防止旧 ChatSpec 写者覆盖绑定 |
| src/swe/app/runner/api.py、manager.py | 绑定 API、模式转移、当前 Chat 授权 |
| 新增 src/swe/app/runner/expert_main.py | 专家定义、角色、模型、能力、预算及依赖快照准备 |
| src/swe/app/runner/runner.py | 普通聊天分支装配，复用历史、流式、审批续接和停止 |
| src/swe/app/routers/console.py | 新消息启动前校验预期绑定修订，保留重连语义 |
| src/swe/agents/react_agent.py | 专家角色/能力、禁长期记忆和委派、保持 main 审批身份 |
| src/swe/agents/tool_guard_mixin.py | 仅按需增加权限/工具预算防线，复用交互审批 |
| src/swe/app/subagents/session_dependencies.py | 独立主执行版本化私有依赖捕获入口 |
| src/swe/app/runner/command_dispatch.py | 显式重置解除绑定 |
| console/src/api/modules/chat.ts、console/src/api/types/chat.ts | 绑定 API、冲突视图与回答执行身份类型 |
| 新增 console/src/pages/Chat/useExpertBinding.ts | 保存、恢复、跨 Chat 异步隔离和冲突同步 |
| console/src/pages/Chat/index.tsx、expertSelection.ts、ExpertSelector/index.tsx | 持续选中、默认退出、预期修订提交、草稿恢复 |
| console/src/pages/Chat/components/RuntimeResponseCard/index.tsx | 展示每条回答启动时身份，刷新后不改名 |

以上是候选改动范围，不为满足列表而强制修改每个文件。新增逻辑放相邻小模块，不整体重写 runner 或聊天页面。

## 实现契约

### 开关

~~~text
key: feature_switches.expert_as_main_enabled
default: false
title: 所选专家作为主 Agent
description: 开启后，普通聊天中选择的专家会持续接管当前会话并直接回复；关闭后仍按单条消息作为子代理执行。
~~~

沿用 SourceSystemConfig 的动态注册和管理员保存，不新增另一套固定配置模型。普通用户只读取有效值；该开关独立于 subagent_expert_discovery_enabled。

### 绑定与 API

expert_binding.py 定义如下模型和模块级保留键；修订是单调状态版本，不是专家配置版本。

~~~python
from pydantic import BaseModel, ConfigDict, Field

EXPERT_BINDING_META_KEY = "expert_main_binding"

class ChatExpertBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    revision: int = Field(default=0, ge=0)
    expert_id: str | None = None

class ExpertBindingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    expert_id: str | None

class ExpertBindingView(ChatExpertBinding):
    enabled: bool
    available: bool
    expert_name: str | None = None
    reason: str | None = None
~~~

- 新增 GET /chats/{chat_id}/expert-binding 和 PUT /chats/{chat_id}/expert-binding。沿用 Chat API 的用户、Source 和 workspace 所有权校验，只允许当前 Profile 专家；name、available、权限和定义快照不能由客户端提交。
- 状态保存在服务端 meta.expert_main_binding；旧 Chat 缺省 revision=0 / expert_id=null。选专家、切换、解除与重置成功后修订前进，解除保留 null 和修订，不能删回 revision 0。相同身份无变化可返回原修订。
- 仓储新增 compare_and_set_expert_binding(chat_id, expected_revision, expert_id)，返回 ChatExpertBinding。修订冲突抛 ExpertBindingConflict，其 current 为当前绑定；统一处理 Chat 不存在错误。空 expert_id 只允许 null，空白字符串验证拒绝。
- 将保留键加入 _SERVER_OWNED_CHAT_META_KEYS；普通 create/update 不得伪造绑定。旧标题、状态和 Goal meta 写者不能用旧 ChatSpec 覆盖最新绑定，保护须在仓储写锁内完成。
- PUT expert_id:null 才是解除；遗漏字段由模型拒绝。服务端保留的有效性和清除状态不能被通用 meta 重放。
- 普通新消息携带 expert_binding_revision，以服务端绑定确定执行身份。开启后不通过每条 selected_expert_id 隐式更新持久绑定；关闭时保留旧单条 selected_expert_id 路径。
- 409 响应 detail 包含 code 和 expert_binding 视图。代码固定 expert_binding_changed / expert_main_disabled / expert_unavailable；不返回私有路径、定义、凭据。客户端收到后同步视图、提示并保留消息，绝不自动重试发送。
- 有绑定但旧客户端没有预期修订时拒绝并要求刷新；无绑定旧请求保持兼容。Plan / Goal 模式更新与解除绑定在同一原子修改中进行，跨页面旧写者不能重新激活旧绑定。

### 消息执行

- 在 post_console_chat 的新执行路径中，于排队/发布用户轮次之前校验修订并捕获服务端执行身份。重连仅订阅原执行，不重新挑专家；审批续接也使用原执行快照。
- 每条准入快照记录专家 ID/name、绑定修订、最新有效本地配置及一致的私有依赖；后续选择变更不影响已开始消息。
- 请求上下文使用 expert_main_execution=true 且 agent_role=main，复用主聊天审批。不得设置 forced_tool_call_json=start_subagent；不得创建 SubAgent run record。
- 专家主执行禁止平台 SubAgent 启动及管理工具，不因关键词、enable_subagents、自主发现开关、Skill 或 MCP 声明重新开放委派。使用工具注册和执行防线，不仅靠提示词。
- 保留普通 Chat 历史、压缩和 checkpoint 恢复；memory_manager=None、enable_memory_manager=False 只禁 Profile 长期记忆，不能抹掉聊天上下文。
- 角色 instruction 替代 Profile 角色；平台安全规则、环境、工具提示和 Source 公共规则仍注入。裸 system_prompt_override 会提前返回，必须组合公共层，不能直接套专家文本漏掉公共规则。
- 专家可用模型优先，否则当前 Chat 模型；权限用父策略、专家策略、工作区策略交集。每维预算取现有专家与适用 Main Agent 全局限制的最小值，不虚构不存在的全局配置。
- 每条新消息独立预算，消息内重连、内部重试、人工审批续接不得重置预算；失败/停止/超限记录原因而不解除绑定。
- 回答 metadata 保存 execution_identity，含 kind=expert_main、expert_id、expert_name、binding_revision；历史和重连按这条快照渲染，不用当前选择器给旧回答改名。

## Task 1：Source 注册与配置界面

**Files:** Source registry、SystemConfigPage registry/workbench；测试 tests/unit/app/test_source_system_config.py、SystemConfigPage/registry.test.ts 与 workbench.test.ts。

- [x] 添加默认关闭、Source A/B 隔离、恢复默认、独立于发现开关的失败测试。基础用例：

~~~python
def test_expert_main_defaults_off():
    from swe.app.source_system_config.registry import (
        build_default_source_system_config_payload,
        is_expert_as_main_enabled,
    )
    defaults = build_default_source_system_config_payload()
    assert defaults["feature_switches"]["expert_as_main_enabled"] is False
    assert is_expert_as_main_enabled(None) is False
    assert is_expert_as_main_enabled({
        "feature_switches": {"expert_as_main_enabled": True}
    }) is True
~~~

- [x] 运行 venv/bin/python -m pytest tests/unit/app/test_source_system_config.py -k expert_main -v，确认新增行为尚不存在。
- [x] 仿照相邻开关新增 EXPERT_AS_MAIN_ENABLED_SWITCH、is_expert_as_main_enabled，加入注册集合和 __all__；复用 bool 规范化。
- [x] 前端对话与执行分组增加上文开关，沿用统一管理员保存。
- [x] 验证 venv/bin/python -m pytest tests/unit/app/test_source_system_config.py -q；npm --prefix console run test:run -- src/pages/SystemConfigPage/registry.test.ts src/pages/SystemConfigPage/workbench.test.ts src/pages/SystemConfigPage/index.test.tsx。预期通过。

## Task 2：原子绑定与 API

**Files:** 新增 expert_binding.py；修改 runner repo/base、repo/json_repo、manager、api；新增 tests/unit/app/test_expert_main_binding.py，扩展 test_chat_json_repo.py、test_chat_api_update.py。

- [x] 先添加必填修订、明确 null、未知字段拒绝及同一文件两个仓储实例的 CAS 竞争测试。核心用例：

~~~python
import pytest
from swe.app.runner.models import ChatSpec
from swe.app.runner.repo.json_repo import JsonChatRepository

@pytest.mark.asyncio
async def test_stale_writer_cannot_replace_binding(tmp_path):
    from swe.app.runner.expert_binding import ExpertBindingConflict
    left = JsonChatRepository(tmp_path / "chats.json")
    right = JsonChatRepository(tmp_path / "chats.json")
    await left.upsert_chat(ChatSpec(
        id="chat-1", session_id="session-1", user_id="alice",
    ))
    saved = await left.compare_and_set_expert_binding("chat-1", 0, "expert-a")
    assert (saved.revision, saved.expert_id) == (1, "expert-a")
    with pytest.raises(ExpertBindingConflict):
        await right.compare_and_set_expert_binding("chat-1", 0, "expert-b")
    current = await right.get_chat("chat-1")
    assert current.meta["expert_main_binding"]["expert_id"] == "expert-a"
~~~

- [x] 运行 venv/bin/python -m pytest tests/unit/app/test_expert_main_binding.py -v 确认新增契约缺失。
- [x] 按固定模型实现服务端状态。在 _write_lock_sync 内执行 _load_sync、修订比较、只更新保留键、_save_and_prepare_snapshot_sync(already_locked=True)；异步用 run_runtime_state_work 与 _set_snapshot，文件 I/O 不回事件循环。
- [x] _upsert_chat_sync 内保护读到的最新绑定；CAS 为专用修改入口。测试旧 title/status/meta 写者不覆盖绑定且其他 meta 正常保存。Base 仓储不提供假原子的 load/save 默认实现。
- [x] GET/PUT 接入当前 workspace 授权；不可用保留身份并返回 available=false；Source 关闭解除且修订前进；通用 create/update 禁止保留键注入。
- [x] 添加 403/404/409、Source/Profile 隔离、重建仓储恢复、解除后修订不倒退及 A→B→A 冲突用例。
- [x] 验证 venv/bin/python -m pytest tests/unit/app/test_expert_main_binding.py tests/unit/app/test_chat_json_repo.py tests/unit/app/test_chat_api_update.py tests/unit/app/test_chat_manager_agent_metadata.py -q。预期通过。

## Task 3：准入、模式转移与显式重置

**Files:** routers/console、runner/api、runner/command_dispatch、runner/runner；新增 tests/unit/routers/test_console_chat_expert_main.py。

- [x] 复用 Console API fixture 添加正确修订启动一次、旧修订/缺修订拒绝、Source 关闭与不可用拒绝。拒绝断言 enqueue、模型调用、user turn 发布次数均为 0。运行新测试先确认行为失败。
- [x] 新消息准入校验服务端最新绑定；排队前捕获执行身份。重连与审批重放不套新修订校验、不换专家。若响应已进入 SSE，错误帧沿用相同 code 且模型调用仍为 0。
- [x] Plan/Goal 写入与解除在同一仓储原子操作内完成；模式开启成功才提示解除。命令路径 /new 与显式清空解除绑定，/compact 保留绑定。
- [x] 关闭开关保持原单条 selected_expert_id 的强制 start/wait/summarize；开启后的持久绑定不受正文提及或伪造 execution_identity 控制。
- [x] 添加运行中 A 切 B 仍由 A 完成、模式切换与绑定保存竞态、重置修订前进、重连不重启专家、关闭后重新开启不恢复已失效绑定。
- [x] 验证 venv/bin/python -m pytest tests/unit/routers/test_console_chat_expert_main.py tests/unit/routers/test_console_chat_stream.py tests/unit/routers/test_console_chat_reconnect.py tests/unit/app/test_chat_api_update.py tests/unit/app/test_runner_goal_lifecycle.py -q。预期通过。

## Task 4：按消息捕获专家与版本一致依赖

**Files:** 新增 runner/expert_main.py；subagents/session_dependencies.py；新增 tests/unit/app/test_expert_main_preparation.py、tests/unit/subagents/test_expert_main_dependency_versions.py。

- [x] 定义冻结的 PreparedExpertMainExecution：身份/名称/修订、指令、模型、权限交集、BudgetConfig、Skill roots、独立 MCP configs、当前本地版本身份。只作为运行内部数据，不暴露到 Chat API。
- [x] 先构造 A v1/v2 包，指令/Skill 文件/MCP 名单均不同；断言第二条全为 v2，第一条快照仍为 v1；运行两个新文件确认缺入口失败。
- [x] 从当前 Profile 精确 ID 读有效启用专家并校验撤回；模型租户可解析才使用，否则继承 Chat 模型；不转移任意凭据或 endpoint。
- [x] 新主执行入口按 Chat + definition_id + 当前本地版本身份构建视图，临时目录原子发布，单消息再复制独立快照。原 SubAgent 首次 Chat 视图默认保持不变。
- [x] 读取期间更新必须重读一致版本或明确失败，不混用新指令旧资源。社区包使用本地接收版本的冻结依赖，不自行从市场拉更新。
- [x] 复用权限交集、私有路径检查和复制；并发失败方只清自己的临时目录，不删除赢家或在途快照。Skill/MCP 不进入 Profile 通用目录，不回退同名 Profile 资源。
- [x] 测试同版本并发、跨版本并发、禁用/删除/撤回、结构损坏、暂时 MCP 不可达及同身份恢复；保留已有非致命 MCP 降级规则并报告能力减少。
- [x] 验证 venv/bin/python -m pytest tests/unit/app/test_expert_main_preparation.py tests/unit/subagents/test_expert_main_dependency_versions.py tests/unit/app/test_runner_selected_expert_dependency_views.py tests/unit/subagents/test_discovered_expert_dependency_views.py -q。预期通过。

## Task 5：主执行、上下文、预算、审批与停止

**Files:** runner/runner、agents/react_agent；必要时 tool_guard_mixin；新增 tests/unit/app/test_expert_main_runtime.py。

- [x] 先添加运行矩阵：专家角色/main 身份、历史可读/长期记忆关闭、无 forced start、supervisor.start 调用数为 0、返回专家流；关闭开关装配不变。运行新测试确认行为失败。
- [x] 从 PreparedExpertMainExecution 装配受限的 Profile 配置副本，不写回配置；memory_manager=None / enable_memory_manager=False，正常装载当前 Chat 历史/压缩/checkpoint。
- [x] 最小公共 prompt helper 保留平台/Source/环境层、替换 Profile 角色层；测试专家与默认角色冲突、Source 注入仍存在、原普通聊天 prompt 不变。
- [x] 在 _background_subagent_role_blocked 及调用防线识别 expert_main_execution，防关键词/结构化意图/自主发现重新开放委派。保留 main 身份进入原审批链。
- [x] 工具、技能与 MCP 按准备快照限制；工具计数、轮数、超时逐维取严格上限，超限走主聊天终止与资源清理，消息内重试不重置预算。
- [x] 人工审批复用 pending/approval_action：批准只重放原快照调用，拒绝/停止/超时报告原因；用户切换专家不改变待批准调用权限。
- [x] 保存 execution_identity 与终态原因，绑定不因失败/停止而解除；回答 identity 重进/重连保持，主执行不写 SubAgent run store。
- [x] 验证 venv/bin/python -m pytest tests/unit/app/test_expert_main_runtime.py tests/unit/subagents/test_react_agent_and_guard_integration.py tests/unit/subagents/test_runtime_and_delegation.py tests/unit/app/test_console_chat_system_prompt_injections.py tests/unit/app/test_event_loop_request_preparation.py -q。预期通过。

## Task 6：前端持久选择、冲突草稿与回答身份

**Files:** chat API/types、Chat/index、ExpertSelector、expertSelection、RuntimeResponseCard/index.tsx；新增 useExpertBinding.ts 与测试，使用已有 runtimeMessageHeader.test.tsx 验证回答身份。

- [x] 新增 console/src/api/modules/chat.expertBinding.test.ts 验证 GET/PUT 路径、expected_revision、null 原样序列化；类型与服务端固定契约一致。
- [x] 新增 useExpertBinding.test.tsx，用受控 Promise 测立即保存、保存失败、跨 Chat 乱序、重复点击与冲突同步；先运行这些测试确认缺功能失败。
- [x] hook 以 Source/Profile/Chat 隔离状态，保存中禁发，失败回到已保存视图并提示；旧 Chat 请求不能覆盖新 Chat。首次选择先复用已有 createChat 创建空 Chat，再 PUT，不等待发送首条消息。
- [x] 主执行选择器持续显示绑定，提供默认 Agent 项；不可用 ID 即使被 selectable 列表过滤也显示不可用，不误显示默认。关闭模式继续提交后清空原单轮选择。
- [x] 每条新发送提交预期 revision；在成功准入前保留文本和附件引用副本。409 同步状态、提示、恢复草稿，不自动重试、不生成重复乐观行。保存未成功不能假装已选中。
- [x] Plan/Goal、新建、显式重置解除并提示；实际回答名称来自 metadata，不跟随选择器变化。主执行使用聊天停止按钮，不新增 SubAgent 监控项，历史监控仍可见。
- [x] 保留 Chat 模型控件，不因切换模型解除绑定；服务端按专家可用模型优先。回答持久显示启动时专家身份，本次不增加实际模型字段。
- [x] 验证 npm --prefix console run test:run -- src/api/modules/chat.expertBinding.test.ts src/pages/Chat/useExpertBinding.test.tsx src/pages/Chat/expertSelection.test.ts src/pages/Chat/index.test.tsx src/pages/Chat/components/runtimeMessageHeader.test.tsx src/pages/Chat/components/SubAgentRunMonitor/index.test.tsx；再运行 npm --prefix console run typecheck。预期通过。

## Task 7：完整验收与交付

- [x] 每个 Q1–Q26 及 Q16a/Q16b 都对应实际测试名与结果；单一代表用例不能代替矩阵。
- [x] 后端合并回归（已运行，既有失败单列）：

~~~bash
venv/bin/python -m pytest tests/unit/app/test_expert_main_binding.py tests/unit/app/test_expert_main_preparation.py tests/unit/app/test_expert_main_runtime.py tests/unit/routers/test_console_chat_expert_main.py tests/unit/subagents/test_expert_main_dependency_versions.py tests/unit/app/test_chat_json_repo.py tests/unit/app/test_chat_api_update.py tests/unit/app/test_source_system_config.py tests/unit/app/test_runner_goal_lifecycle.py tests/unit/subagents/ -q
~~~

- [x] 前端回归（定向与全范围已运行，既有失败和超时单列）：

~~~bash
npm --prefix console run test:run -- src/pages/SystemConfigPage src/pages/Chat src/api/modules/chat.expertBinding.test.ts
npm --prefix console run typecheck
~~~

- [x] 执行 git diff --check 和必要 pre-commit。新增行为需实际红/绿验证；缺依赖/收集错误不是业务复现成功，既有无关失败单独记录。
- [x] 按无真实环境的替代验收：两个独立 Python 进程验证同 Chat CAS 一方拒绝，另测仓储重建、在途版本隔离和 Source 关闭；真实 Kubernetes/NAS/多副本重启未验收。
- [x] 完成隔离浏览器可执行范围：立即保存、刷新恢复、409 身份同步及可见文本/附件重发；独立报告区分 mock API 与真实后端。
- [ ] 真实环境后续验收：双页面实时竞争、禁用恢复、流式停止、人工审批、版本更新及窄屏/键盘完整矩阵，不以本地组件测试或模拟 API 代替。
- [x] 更新 playbook 的尚未实现状态仅在功能完成后进行。交付报告列实际完成、命令结果和未验证环境，不把设计确认视为上线。
- [x] 任何后续提交前运行 GitNexus detect_changes，核对预期符号和流程；未获提交指令则保留可审查工作区变更。

## 需求覆盖

| 决策 | 任务 |
| --- | --- |
| Q1/Q13 Source 权限、缺省关闭 | 1、3、7 |
| Q2/Q3 结构化选择、持续接管 | 2、3、6 |
| Q4/Q9/Q11 能力、无长期记忆、不委派 | 4、5 |
| Q5/Q15 普通聊天、模式退出 | 3、6、7 |
| Q6/Q7/Q14 切换退出、恢复、保存时机 | 2、3、6 |
| Q8/Q21 Chat 上下文、角色替换 | 5 |
| Q10/Q12/Q22 模型与单消息严格预算 | 4、5 |
| Q16/Q16a/Q16b 关闭失效、不恢复、消息保留 | 2、3、6 |
| Q17/Q26 不可用阻止、同身份恢复 | 2、3、4、6 |
| Q18 最新本地版本、在途快照 | 3、4、5 |
| Q19/Q20 失败保留、直接流式和身份 | 5、6 |
| Q23 交互审批 | 5、7 |
| Q24 多页面一致性 | 2、3、6、7 |
| Q25 新建/显式重置 | 3、6 |

**执行方式：** 沿用 executing-plans，按任务实施并在有测试与独立审查证据后小步提交。用户已经授权子代理审查与提交；推送及 PR 不在本次授权范围。计划勾选仅在相应验收完成后更新。

## 实际交付证据

- [功能完成报告](../reports/2026-10-27-expert-as-main-functionality-report.md)
- [测试报告](../reports/2026-10-27-expert-as-main-test-report.md)：后端 502 passed、前端 223 passed/2 baseline skipped，完整 SubAgent 57 项既有失败集合一致。
- [覆盖矩阵](../reports/2026-10-27-expert-as-main-coverage.md) 与 [浏览器记录](../reports/2026-10-27-expert-as-main-browser-validation.md)。
- 上述完成框表示实际执行并记录结果，不表示所有原有测试已通过。pending 审批跨进程续接未实现，缺失原快照时安全拒绝。
