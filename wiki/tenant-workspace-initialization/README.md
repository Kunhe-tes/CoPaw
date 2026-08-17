# 租户请求与 Workspace 初始化

本文说明一条 HTTP 请求如何绑定租户上下文、确保租户目录可用，并在真正需要 Agent 时延迟启动完整 Workspace Runtime。这里的 “workspace” 有两层含义：请求阶段的轻量目录上下文，与承载 Runner、记忆、渠道和定时任务的完整运行时实例。

## 结论

- 应用启动时只创建 `TenantWorkspacePool` 和 `MultiAgentManager` 等管理容器，不会为每个租户启动 Runtime。
- 普通非豁免请求都会先完成 tenant/source 身份解析，再执行严格的租户 bootstrap 检查。
- bootstrap 成功后，请求里保存的是 `TenantWorkspaceContext`，不是完整 `Workspace`。
- 只有聊天、Runner 或显式 Agent 解析等路径需要运行时，才由 `MultiAgentManager.get_agent()` 创建并启动 `Workspace`。
- 新租户的初始化是幂等且可自愈的；同一租户跨请求/跨进程通过文件锁避免重复初始化。

## 请求主链路

```text
HTTP request
  -> TenantIdentityMiddleware
  -> SourceSystemConfigMiddleware
  -> TenantWorkspaceMiddleware
       -> TenantWorkspacePool.ensure_bootstrap()
       -> TenantWorkspaceContext
  -> AgentContextMiddleware
  -> Router / DynamicMultiAgentRunner
       -> MultiAgentManager.get_agent()（按需）
       -> Workspace.start()
```

应用的 middleware 注册顺序在 `src/swe/app/_app.py`。由于 Starlette 后注册的 middleware 先执行，业务上应把身份解析看作 workspace 解析的前置条件。

## 1. 身份与隔离键

`TenantIdentityMiddleware` 从请求头读取并验证：

| Header | 用途 |
| --- | --- |
| `X-Tenant-Id` | 逻辑租户或用户身份；非豁免路由必填 |
| `X-Source-Id` | 来源系统身份；非豁免路由必填 |
| `X-User-Id` | 请求用户身份 |
| `X-User-Name` / `X-Bbk-Id` | 初始化来源记录与展示身份的补充信息 |

它会把 tenant、user、source 和由 tenant/source 编码得到的 `scope_id` 同时写入 `request.state` 与 ContextVar，并在响应结束时复位。

路径与配置同时存在 runtime/storage 两套语义：

| 逻辑身份 | runtime scope | 实际 storage 目录 |
| --- | --- | --- |
| `default`，无 source | `default` | `WORKING_DIR/default` |
| `default + ruice` | tenant/source 的 scope | `WORKING_DIR/default_ruice` |
| `user-001 + ruice` | canonical scope | `WORKING_DIR/<canonical-scope>` |

`default + source` 是特殊模板目录语义；其他 source 租户一般使用编码 scope 作为隔离根。具体规则在 `src/swe/config/context.py` 的 `resolve_storage_tenant_id()` 与 `resolve_request_effective_tenant_id()`。

## 2. 请求阶段的轻量 Workspace Context

`TenantWorkspaceMiddleware` 先根据 storage 语义计算有效租户目录，再调用 `resolve_user_identity()` 补齐用户展示身份，随后调用：

```python
await pool.ensure_bootstrap(
    tenant_id,
    source_id=source_id,
    scope_id=scope_id,
    tenant_name=user_name,
    bbk_id=bbk_id,
)
```

成功后只构造：

```python
TenantWorkspaceContext(
    tenant_id=effective_storage_tenant_id,
    workspace_dir=<tenant-root>,
)
```

并将其放入 `request.state.workspace` / `request.state.tenant_workspace`，同时绑定当前 workspace 根目录。该对象不包含 Runner、MemoryManager、ChannelManager 或 CronManager；因此文件管理等只需目录的接口无需启动 Agent。

bootstrap 不可用会被 middleware 映射为 `503 Tenant bootstrap unavailable`，并带 `Retry-After: 2`。

## 3. 已初始化租户：fast path

`TenantWorkspacePool.ensure_bootstrap()` 先通过 `TenantInitializer.has_seeded_bootstrap()` 进行严格 readiness 检查。通过检查时：

1. 若内存 registry 没有该租户，仅创建一个 `TenantWorkspaceEntry(workspace=None)`。
2. 更新访问时间和计数。
3. 直接返回，不复制模板文件，也不启动 Runtime。

strict readiness 会检查：

- 租户 `config.json` 和 default agent 的引用路径；
- `workspaces/default/agent.json`；
- `AGENTS.md`、`HEARTBEAT.md`、`MEMORY.md`、`PROFILE.md`、`SOUL.md`；
- `sessions/`、`memory/`、`skills/`；
- `chats.json`、`jobs.json`、`token_usage.json`；
- skill pool 与 workspace skill manifest 所声明的每个 `SKILL.md`。

检查逻辑在 `src/swe/app/workspace/bootstrap_state.py` 的 `inspect_bootstrap_readiness()`。

## 4. 新租户或不完整租户：bootstrap 与自愈

若 strict readiness 不通过，pool 会获取 `<tenant-root>/.bootstrap.lock` 跨进程文件锁，并在获得锁后再次检查，避免并发请求重复复制目录。锁超时或不可用会转换为可重试的 `TenantBootstrapUnavailable`。

随后 `TenantInitializer.recover_seeded_bootstrap()`：

1. 将仅被严格检查确认无效的 bootstrap JSON 移到临时 `.bak`；
2. reconcile 已存在的 default workspace skill manifest；
3. 执行 `ensure_seeded_bootstrap()`；
4. 重新进行严格检查；
5. 成功后写入 `.bootstrap.ready`，并删除本次恢复产生的临时备份。

bootstrap 成功后还会：

- 向 tenant-init-source store 记录逻辑 tenant、source、直接初始化模板、用户名和 BBK；该记录失败仅告警。
- 同步 `swe_skills`；同步失败同样不阻断已就绪的租户。

## 5. 首次初始化具体产物

`ensure_seeded_bootstrap()` 依次完成以下工作，所有步骤都以“不覆盖已有有效状态”为原则：

1. 创建 `<tenant>/workspaces`、`media`、`secrets`，并保证 default agent 引用存在。
2. 当租户 `config.json` 缺失时，从选中的模板复制，并把其中 `workspace_dir` 改写到目标租户。
3. 从模板复制 providers 文件目录到 `SECRET_DIR/<effective-tenant>/providers`（若目标不存在）。ProviderManager 实例和模型创建仍是 feature boundary 上的延迟行为。
4. 初始化 `skill_pool`：优先复制模板 skill pool 并重建 manifest；没有可复制技能时，回退到 builtin skills。
5. 初始化 default workspace 已注册技能，并保留 enabled、channels、config、source 等 manifest 状态。
6. 补齐 default workspace：`sessions/`、`memory/`、`skills/`、`agent.json`、系统 Markdown 文件和 `token_usage.json`。`enable_bootstrap_chat=False` 时会移除 `BOOTSTRAP.md`。

正常请求 bootstrap 不创建 QA Agent；QA Agent 仅由 full initialization / 专门功能路径创建。

## 6. source 模板前置条件

普通带 `X-Source-Id` 的流量不会隐式创建 `default_<source>` 模板。`TenantWorkspacePool` 会要求以下内容已经 strict-ready：

```text
WORKING_DIR/default_<source>/
SECRET_DIR/default_<source>/providers/
```

模板缺失或损坏时，请求会返回 503；应由受内部 token 保护的接口显式准备：

```text
POST /api/internal/source-templates/ensure
```

`SourceTemplateProvisioner` 会在专用锁内：校验全局 `default` 模板和 providers、复制到 staging 目录、重写 workspace 路径、严格校验，然后以替换方式发布 working/secret 两个目标目录。它不会覆盖已 ready 的 source 模板。

## 7. 完整 Workspace Runtime 的延迟启动

需要执行 Agent 的路径会调用 `get_agent_for_request()` 或 `DynamicMultiAgentRunner`：

1. 从租户 config 解析目标 Agent（路径参数、`X-Agent-Id` 或 active agent）。
2. 检查 Agent 存在且启用。
3. 调用 `MultiAgentManager.get_agent(agent_id, tenant_id=effective_tenant_id)`。
4. 使用 `<effective-tenant-id>:<agent-id>` 作为 cache key。
5. cache miss 时创建 `Workspace` 并调用 `start()`；同 key 的并发请求共享同一个启动 task。

`Workspace.start()` 的服务顺序为：

```text
10  AgentRunner
20  MemoryManager + ChatManager（并发）
25  AgentRunner.start()
30  ChannelManager
40  CronManager
50  AgentConfigWatcher
```

其中聊天记录、任务、记忆、渠道配置均基于对应 Agent 的租户 workspace；不同有效 tenant 的同名 `default` Agent 不会复用同一个 Runtime。

## 8. 排查入口

| 现象 | 首先检查 |
| --- | --- |
| 请求直接 400 | `X-Tenant-Id` / `X-Source-Id` 是否存在且合法；路由是否应为豁免路由 |
| 请求 503 且有 `Retry-After` | `.bootstrap.lock` 是否被长时间占用；bootstrap 日志中的 `tenant_bootstrap_*` |
| source 请求 503 | `default_<source>` 与其 providers 是否由内部 ensure 接口准备完成 |
| Agent 404 | 目标租户 `config.json` 是否包含并启用了所请求 Agent |
| 首次聊天慢 | 区分 `ensure_bootstrap` 耗时与 `MultiAgentManager` 首次 Runtime 启动耗时 |
| provider/model 缺失 | 查看 `SECRET_DIR/<effective-tenant>/providers`；ProviderManager 在 provider/model feature boundary 才初始化实例 |

主要源码入口：

- `src/swe/app/middleware/tenant_identity.py`
- `src/swe/app/middleware/tenant_workspace.py`
- `src/swe/app/workspace/tenant_pool.py`
- `src/swe/app/workspace/tenant_initializer.py`
- `src/swe/app/workspace/source_template_provisioner.py`
- `src/swe/app/agent_context.py`
- `src/swe/app/multi_agent_manager.py`
- `src/swe/app/workspace/workspace.py`

## 9. 流程审视与优化建议

### 9.1 `X-Source-Id` 的 source 模板前置条件是否过强

当前规则是：带 `X-Source-Id: ruice` 的首次 source-scoped bootstrap，必须先存在并通过严格检查的：

```text
WORKING_DIR/default_ruice/
SECRET_DIR/default_ruice/providers/
```

这不是普通租户流量“顺便创建模板”，而是 fail-closed 约束。`TenantWorkspacePool.ensure_bootstrap()` 只在确认现有租户已 ready 后走 fast path；新建或损坏租户在文件锁内调用 `_require_ready_source_template()`，模板未 ready 就抛出 `SourceTemplateUnavailable`，由 middleware 返回 503（见 `tenant_pool.py:463-505`、`tenant_pool.py:541-558`）。

判断：**安全和所有权语义上合理，运营体验上偏硬，但不建议对普通请求放宽为隐式创建。** 模板复制会同时处理 config、workspace、providers、skills、路径重写、严格复核和发布/回滚；把它放到未授权租户请求中会让共享 source 模板成为可被流量驱动修改的状态。更合适的优化是：

- 在 source onboarding、部署或内部任务中预先调用 `POST /api/internal/source-templates/ensure`；
- 503 detail/日志/指标明确区分 `source_template_not_ready`、锁超时和恢复失败；
- 对已有 ready 租户不重复依赖模板，保留当前 fast path 行为；
- 若未来确实要按请求自动准备模板，应增加管理员授权、source 所有权校验和单独的模板状态机，而不是简单移除检查。

### 9.2 严格 readiness 的必要性分层

`inspect_bootstrap_readiness()` 是“完整 bootstrap 合同”的校验器，不等同于“每个文件都是 Agent 首次运行的硬依赖”（见 `bootstrap_state.py:18-139`）。建议按以下语义理解：

| 产物 | 首次运行是否硬依赖 | 当前严格检查的价值 |
| --- | --- | --- |
| `config.json`、`workspaces/default/agent.json` 及路径/启用状态 | 是 | 必须保留；`load_agent_config()` 在 agent.json 缺失时直接失败（`config.py:1912-1949`） |
| `skill_pool/skill.json`、声明的 skill 目录及 `SKILL.md` | 基本是 | 保证技能分发、manifest 与磁盘状态确定一致；建议保留 |
| `sessions/`、`memory/`、`skills/` 目录 | 多数可惰性创建 | 属于 scaffold 完整性；`ensure_default_workspace_scaffold()` 会创建（`tenant_initializer.py:513-517`），session 写路径也会 `makedirs`（`runner/session.py:205-218`） |
| `chats.json`、`jobs.json` | 否 | 两个 JSON repository 缺文件时分别回退为空，保存时创建父目录和文件（`runner/repo/json_repo.py`、`crons/repo/json_repo.py`） |
| `token_usage.json` | 否 | manager 缺文件时返回空数据，写入时创建父目录（`token_usage/manager.py:129-163`） |
| `AGENTS.md`、`HEARTBEAT.md`、`MEMORY.md`、`PROFILE.md`、`SOUL.md` | 提示词文件可选；heartbeat 缺文件会跳过 | 当前检查保证模板/租户可复制且行为确定，但不是全部运行时硬依赖；prompt builder 明确允许缺失并回退默认 prompt（`agents/prompt.py:212-221`），heartbeat 缺文件直接 skip（`app/crons/heartbeat.py:156-160`） |
| `BOOTSTRAP.md` | 否，且应允许删除 | 已正确排除 strict readiness；`enable_bootstrap_chat=False` 会主动删除 |

因此不建议直接删减检查项。更稳妥的是拆成两个 profile：

1. `bootstrap_integrity`：模板发布、batch 初始化和恢复使用，保留当前严格合同；
2. `runtime_liveness`：普通请求 fast path 可选使用较小不变量，但明确哪些缺失文件不自动修复，避免把用户主动删除的文件悄悄恢复。

### 9.3 batch-initialize 与自动初始化的一致性

两条路径最终都调用同一个 `pool.ensure_bootstrap()`，所以真正的创建、恢复、跨进程文件锁和 source 模板门槛是一致的。

但 batch 在调用前有独立短路：`_is_tenant_already_bootstrapped()` 只调用 `TenantInitializer.has_seeded_bootstrap()`（`internal.py:603-621`），而不会复用 pool 对 `default_<source>` 的 `inspect_source_template_readiness()`。结果是：

- 对 `default + source`，batch 可能将已有 seeded scaffold 标记为 `skipped`；
- 普通 source 请求随后仍会因为 `SECRET_DIR/default_<source>/providers` 缺失而返回 503；
- batch 的 `created/skipped` 结果也不是 `ensure_bootstrap()` 的真实结果，因为 `ensure_bootstrap()` 当前返回 `None`。

另外，batch 要求远程解析同时得到 `user_name` 和 `bbk_id`（`internal.py:806-832`）；普通请求在身份补充不完整时仍可能继续 bootstrap。这是数据质量策略差异，不是底层 bootstrap 语义，应在接口契约中显式说明。

建议：移除 batch 自己维护的 readiness 谓词，提供一个**纯查询、不修改 registry 的 pool-level readiness API**，其判定完全复用 `_check_existing_bootstrap()`；或者让 `ensure_bootstrap()` 返回 `created/recovered/already_ready` 等结构化结果，由 batch 直接据此记录状态。

### 9.4 优化项（按优先级）

**高优先级、低行为风险**

- 消除 batch 的重复 readiness 逻辑，统一 source 模板和租户 ready 判定；
- 让 `ensure_bootstrap()` 返回结构化 outcome，并记录耗时、原因、恢复路径，减少 batch 再次扫描文件；
- 修正 `ensure_bootstrap()`、`TenantWorkspacePool` 中仍称“minimal/directories only”的过时注释，避免误导调用方。

**中优先级、需要压测/回归测试**

- 当前 `ensure_bootstrap()` 创建了 `bootstrap_lock`，但从未 `async with bootstrap_lock`；实际同步只依赖 `AsyncFlock`（`tenant_pool.py:146-161`、`tenant_pool.py:478-483`）。这会造成每个 tenant 的 asyncio.Lock 字典持续增长且没有进程内效果，应删除这段死状态或真正使用并配套清理；
- `recover_seeded_bootstrap()` 的 copytree、JSON 解析和 skill reconciliation 是同步文件操作，可能阻塞事件循环。可在保留文件锁的范围内用 `asyncio.to_thread` 包住阻塞阶段；
- batch 当前按 tenant 串行处理（`internal.py:802-904`）。可考虑有上限的并发 worker，但要限制远程身份查询压力，并保留每租户文件锁和结果顺序。

**长期治理项**

- `_workspaces` 与 `_bootstrap_locks` 都按 tenant 增长，建议增加 TTL/LRU 或显式清理；
- 非豁免请求每次都会执行 `resolve_user_identity(... allow_remote_lookup=True)`，远程身份服务会进入请求关键路径。可增加短 TTL 缓存，或仅在 batch/admin 流程强制远程补全；
- 严格检查会在 fast path、文件锁后 double-check、恢复后 final-check 多次解析 manifest。保留并发安全前提下，可通过 readiness snapshot/outcome 减少重复 I/O。

### 9.5 GitNexus 影响范围提示

若落地上述修改，需先重新执行影响分析：`TenantWorkspacePool.ensure_bootstrap` 为 **HIGH**（17 个直接调用方、43 个受影响符号），`inspect_bootstrap_readiness` 为 **CRITICAL**（影响配置/provider 分发链路）。因此应先补充 batch/source/缺失可选文件的回归测试，再实施小范围改动；提交前运行 `detect_changes()` 检查受影响执行流。

## 10. 推荐实施方案

当前已完成前两项基础优化，后续治理项仍需基于生产指标决策：

1. **语义收敛（已完成）**：保持 source template fail-closed；`ensure_bootstrap()` 返回唯一的 `already_ready` / `bootstrapped` outcome；batch 无条件调用 pool，并仅据 outcome 标记 `skipped` / `created`。这消除了 batch 自行判定 ready 所造成的语义分歧。
2. **关键路径减负（已完成）**：删除未使用的进程内 bootstrap lock map；保留 `AsyncFlock`，并把 `recover_seeded_bootstrap()` 的同步文件复制、JSON/skill 处理移到 worker thread。
3. **治理型优化（观察后启动）**：基于指标决定是否拆分 `bootstrap_integrity` 与 `runtime_liveness`、是否做 batch 有界并发、租户 registry TTL/LRU 和身份查询缓存。此期不得以性能为由降低 provider/config/skill 的严格完整性。

详细的 TDD 任务、文件清单、验收标准和回归命令见 [Tenant Bootstrap Optimization Implementation Plan](../../docs/superpowers/plans/2026-08-13-tenant-bootstrap-optimization.md)。
