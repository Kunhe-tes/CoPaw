# SubAgent 意图与专家发现排查

## 工具没有出现

先区分启动权限与管理权限。当前真实用户文本命中“子代理”“子智能体”“subagent”“sub-agent”，或结构化 `enable_subagents=true`，才开放新启动。英文忽略大小写，历史、工具结果及模型生成的 Contract 不产生授权。关闭专家主执行开关时，显式 `selected_expert_id` 是独立且排他的单轮 SubAgent 入口；开启后的普通 Chat 使用服务端持久专家绑定。

## 专家主执行与绑定冲突

- Source 管理员开关：`feature_switches.expert_as_main_enabled`，默认关闭，与自主发现开关独立。只有现有结构化选择器建立绑定，正文提及专家不建立绑定。
- 绑定接口：`GET/PUT /chats/{id}/expert-binding`；PUT 显式提交 `expected_revision` 与 `expert_id`（null 解除）。JSON 仓储在跨进程 flock 内比较修订；通用 Chat 更新不能覆盖绑定。
- 发送前：`runner/expert_main_admission.py` 在发布 user turn 前校验修订、开关和专家。409 `expert_binding_changed` 同步最新身份；`expert_main_disabled` 解除绑定；`expert_unavailable` 保留绑定并阻止执行。前端保留草稿与附件供手动重发，不自动重试。
- 执行：`runner/expert_main.py` 捕获每条消息的最新有效本地定义和私有依赖；`expert_main_runtime.py` 管理内部执行身份、预算和审批快照。专家直接流式回复，不创建 SubAgent Run，不读取 Profile 长期记忆，不能继续委派。
- 审批：原进程的 pending lease 续接原身份与预算。进程重启或请求落到没有该 lease 的实例时安全拒绝，reason=`expert_execution_unavailable`，需重新发起任务；不能用最新配置重放旧工具。
- 开关关闭、Plan/Goal、`/new`/`/clear` 解除绑定；`/compact` 保留。失效专家按精确 ID 恢复，同名重建不接替。
- 回归入口：`test_expert_main_binding.py`、`test_console_chat_expert_main.py`、`test_expert_main_preparation.py`、`test_expert_main_runtime.py` 与 `test_expert_main_dependency_versions.py`。本地两个进程的 CAS 测试不代表 Kubernetes/NAS 已验收。

- 判定：`src/swe/app/subagents/intent.py`。
- 注册：`SWEAgent._register_background_subagent_tools`。
- Source 默认关闭开关：`feature_switches.subagent_expert_discovery_enabled`；Console 文案“允许自主选择我的专家”。开关不代替用户意图，也不控制 Skill-owned 定义。
- 当前租户/Profile 的专家还须有效且已启用。不可见定义应同时从工具描述和名称解析排除。

## 能管理旧运行但不能启动

这是无新意图轮次的预期行为。`run_access.py` 用逻辑 session 及记录中的 Chat ID 校验归属；缺少可靠 session 不开放管理。get/cancel 在 supervisor 副作用前验证，wait 从持久记录投影当前会话，不消费其他 Chat 的终态通知。预读 bool 仅控制工具展示，不替代每次访问校验。

普通异步 Query 在 `_prepare_query_agent_context` 的 worker 中扫描保留记录，再在事件循环安装工具。不要将文件扫描移回 Agent 构造。刷新必须清除预读缓存；Goal 的工具刷新也在 worker 执行。回归入口为 `test_event_loop_request_preparation.py` 与 `test_chat_runtime_access.py`。

## 社区专家依赖与并发首次启动

每个 Chat/专家使用独立冻结视图，每次启动使用自己的 context 副本。不要将专家绑定 Skill/MCP 注册到父 Agent 通用目录。

同 Chat、同专家并发首次发布时，不能删除已发布目标。原子发布失败的一方须验证并复用赢家，只在 finally 清理自己的临时目录。回归：`test_discovered_expert_dependency_views.py::test_same_expert_concurrent_first_starts_reuse_published_view`。

## Goal 意图丢失或模式退出泄漏

初始授权在服务端 Chat meta 的 `goal_draft_subagent_delegation_enabled` 跨澄清保存，确认创建后消费；普通/Plan/明确专家入口及关闭 Goal 模式清除。客户端不能写此内部字段，回传 Plan meta 时须过滤。

正式 Goal 使用快照 JSON 字段 `subagent_delegation_enabled`，旧记录缺省 false。Steering 可提升为 true；同一 Goal 内不能被旧快照降级。MySQL save 在同一事务 SELECT FOR UPDATE 后 OR 合并，内存存储同语义。不要只给部分 service 写者补锁，否则 completion review 等旧快照仍能覆盖授权。后续轮刷新 Source 配置与目录，已启动运行保持原快照。

回归入口：`tests/unit/app/goals/test_delegation_intent.py`。SQL 事务单测不替代真实 Kubernetes 多实例 MySQL/NAS 验收。
