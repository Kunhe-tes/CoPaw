# Source Template Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 `default + source` 的模板存储语义为 `default_{source}`，并保持普通租户 runtime scope 与 Cron、分发、运维链路兼容。

**Architecture:** 在配置层新增统一 storage resolver，保留 runtime resolver 兼容语义；随后让 workspace、provider、env、config、skills、mcp、cron、运营查询统一复用该规则，最终通过测试验证模板态与运行态路径不再分裂。

**Tech Stack:** Python、FastAPI、Pydantic、pytest、项目现有多租户 workspace/provider/cron 基础设施

---

## 文件结构与职责

- `src/swe/config/context.py`
  - 新增 storage resolver，承载模板目录解析规则
- `src/swe/config/utils.py`
  - 拆分 storage/runtime 路径 helper
- `src/swe/app/workspace/tenant_initializer.py`
  - 负责模板目录初始化与 agent scaffold 补齐
- `src/swe/app/workspace/tenant_pool.py`
  - 负责 bootstrap 与 workspace 目录获取
- `src/swe/app/middleware/tenant_workspace.py`
  - 负责请求进入后的 workspace 目录绑定
- `src/swe/app/agent_context.py`
  - 负责 tenant-scoped config / agent 读取
- `src/swe/providers/provider_manager.py`
  - 负责 provider 存储解析
- `src/swe/app/routers/providers.py`
  - 负责 provider / active model 分发
- `src/swe/app/routers/envs.py`
  - 负责模板 env 写入
- `src/swe/app/routers/config.py`
  - 负责 channel 配置与分发
- `src/swe/app/routers/skills.py`
  - 负责 skills 广播
- `src/swe/app/routers/mcp.py`
  - 负责 MCP 广播
- `src/swe/app/crons/api.py`
  - 负责 Cron 广播 job 创建
- `src/swe/app/crons/executor.py`
  - 负责 Cron 执行时解析模板与运行态目录
- `src/swe/app/crons/manager.py`
  - 负责 job 生命周期兼容
- `src/swe/app/workspace/tenant_init_source_store.py`
  - 负责新增 `tenant_type` 与查询过滤
- `src/swe/app/routers/user_info.py`
  - 负责运营视图过滤模板记录
- `tests/unit/...`
  - 覆盖 resolver、workspace、provider、env、cron、store 的回归测试

## Task 1: 新增 storage resolver

**Files:**
- Modify: `src/swe/config/context.py`
- Test: `tests/unit/config/test_storage_tenant_resolution.py`

- [ ] **Step 1: 编写失败测试，定义 storage 解析规则**

```python
from swe.config.context import resolve_storage_tenant_id


def test_default_without_source_resolves_to_default():
    assert resolve_storage_tenant_id("default", None) == "default"


def test_default_with_source_resolves_to_template_dir():
    assert resolve_storage_tenant_id("default", "ruice") == "default_ruice"


def test_non_default_with_source_keeps_runtime_scope():
    value = resolve_storage_tenant_id("user-001", "ruice")
    assert value is not None
    assert value != "default_ruice"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `venv/bin/python -m pytest tests/unit/config/test_storage_tenant_resolution.py -v`

Expected: FAIL，提示 `resolve_storage_tenant_id` 未定义或断言失败。

- [ ] **Step 3: 在 `context.py` 中实现 storage resolver**

实现要点：

- 新增 `resolve_storage_tenant_id(tenant_id, source_id, scope_id=None)`
- 规则：
  - `default + no source -> default`
  - `default + source -> default_{source}`
  - `non-default + source -> 保留现有 runtime scope`
  - `non-default + no source -> 原样`
  - 历史 scope 输入继续 canonicalize

- [ ] **Step 4: 运行测试，确认通过**

Run: `venv/bin/python -m pytest tests/unit/config/test_storage_tenant_resolution.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/swe/config/context.py tests/unit/config/test_storage_tenant_resolution.py
git commit -m "feat: add storage tenant resolver"
```

## Task 2: 重构路径 helper，避免 `default_{source}` 二次 scope 化

**Files:**
- Modify: `src/swe/config/utils.py`
- Test: `tests/unit/config/test_storage_path_helpers.py`

- [ ] **Step 1: 编写失败测试**

```python
from pathlib import Path

from swe.config.utils import get_tenant_config_path


def test_storage_template_path_does_not_get_reencoded(monkeypatch, tmp_path):
    monkeypatch.setattr("swe.constant.WORKING_DIR", tmp_path)
    path = get_tenant_config_path("default_ruice")
    assert path == tmp_path / "default_ruice" / "config.json"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `venv/bin/python -m pytest tests/unit/config/test_storage_path_helpers.py -v`

Expected: FAIL，当前 helper 仍可能把 `default_ruice` 继续做 runtime 解析。

- [ ] **Step 3: 拆分 storage/runtime 路径解析**

实现要点：

- 在 `utils.py` 内新增 storage 版本路径解析 helper
- 让 `get_tenant_config_path()`、`get_tenant_secrets_dir()` 等调用场景可明确使用 storage 语义
- 确保 `default_{source}` 不被二次解析

- [ ] **Step 4: 运行测试，确认通过**

Run: `venv/bin/python -m pytest tests/unit/config/test_storage_path_helpers.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/swe/config/utils.py tests/unit/config/test_storage_path_helpers.py
git commit -m "refactor: split storage path resolution from runtime scope"
```

## Task 3: 修复 workspace 初始化与请求绑定

**Files:**
- Modify: `src/swe/app/workspace/tenant_initializer.py`
- Modify: `src/swe/app/workspace/tenant_pool.py`
- Modify: `src/swe/app/middleware/tenant_workspace.py`
- Modify: `src/swe/app/agent_context.py`
- Test: `tests/unit/workspace/test_tenant_init_source.py`
- Test: `tests/unit/app/test_tenant_workspace_storage_resolution.py`

- [ ] **Step 1: 先改失败测试断言**

关键断言：

- `default + source -> tenant_dir == default_{source}`
- 非 default + source 仍走 scope
- workspace middleware 实际命中 storage 目录

- [ ] **Step 2: 运行相关测试，确认失败**

Run: `venv/bin/python -m pytest tests/unit/workspace/test_tenant_init_source.py tests/unit/app/test_tenant_workspace_storage_resolution.py -v`

Expected: FAIL

- [ ] **Step 3: 实现 workspace 主链改造**

实现要点：

- `tenant_initializer.py` 使用 storage resolver
- `tenant_pool.py` 的 bootstrap / get workspace dir 统一改为 storage 语义
- `tenant_workspace.py` 绑定 workspace 目录时不再直接信任 runtime scope
- `agent_context.py` 的 tenant-scoped config 读取与 storage 目录对齐

- [ ] **Step 4: 顺手补齐模板 `agent.json` 的 channels 继承**

实现要点：

- 模板 `agent.json` 存在时，复制后也要补齐 `channels=tenant_config.channels`

- [ ] **Step 5: 运行测试，确认通过**

Run: `venv/bin/python -m pytest tests/unit/workspace/test_tenant_init_source.py tests/unit/app/test_tenant_workspace_storage_resolution.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/swe/app/workspace/tenant_initializer.py src/swe/app/workspace/tenant_pool.py src/swe/app/middleware/tenant_workspace.py src/swe/app/agent_context.py tests/unit/workspace/test_tenant_init_source.py tests/unit/app/test_tenant_workspace_storage_resolution.py
git commit -m "fix: align template workspace storage resolution"
```

## Task 4: 对齐 Provider、Env、Channel、Skills、MCP 模板目录

**Files:**
- Modify: `src/swe/providers/provider_manager.py`
- Modify: `src/swe/app/routers/providers.py`
- Modify: `src/swe/app/routers/envs.py`
- Modify: `src/swe/app/routers/config.py`
- Modify: `src/swe/app/routers/skills.py`
- Modify: `src/swe/app/routers/mcp.py`
- Test: `tests/unit/providers/test_provider_storage_resolution.py`
- Test: `tests/unit/app/test_env_target_storage_resolution.py`
- Test: `tests/unit/app/test_channel_defaults_from_agent_or_model.py`

- [ ] **Step 1: 编写失败测试**

覆盖：

- Provider template dir 命中 `default_{source}`
- `/envs/target` 命中模板目录
- `/channels` 缺省值不再误判 `enabled=false`

- [ ] **Step 2: 运行测试，确认失败**

Run: `venv/bin/python -m pytest tests/unit/providers/test_provider_storage_resolution.py tests/unit/app/test_env_target_storage_resolution.py tests/unit/app/test_channel_defaults_from_agent_or_model.py -v`

Expected: FAIL

- [ ] **Step 3: 实现 provider/env/config 广播修复**

实现要点：

- `ProviderManager` 改用 storage resolver
- `/envs/target` 支持写模板 env
- `config.py` 的 channel 分发和默认值逻辑与 storage 规则对齐
- `skills.py` / `mcp.py` 广播目标统一命中模板目录

- [ ] **Step 4: 运行测试，确认通过**

Run: `venv/bin/python -m pytest tests/unit/providers/test_provider_storage_resolution.py tests/unit/app/test_env_target_storage_resolution.py tests/unit/app/test_channel_defaults_from_agent_or_model.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/swe/providers/provider_manager.py src/swe/app/routers/providers.py src/swe/app/routers/envs.py src/swe/app/routers/config.py src/swe/app/routers/skills.py src/swe/app/routers/mcp.py tests/unit/providers/test_provider_storage_resolution.py tests/unit/app/test_env_target_storage_resolution.py tests/unit/app/test_channel_defaults_from_agent_or_model.py
git commit -m "fix: route template config assets to storage tenant"
```

## Task 5: 兼容 Cron 广播与执行链

**Files:**
- Modify: `src/swe/app/crons/api.py`
- Modify: `src/swe/app/crons/executor.py`
- Modify: `src/swe/app/crons/manager.py`
- Modify: `src/swe/app/crons/coordination.py`
- Modify: `src/swe/app/crons/heartbeat.py`
- Modify: `src/swe/app/tenant_context.py`
- Test: `tests/unit/app/test_cron_template_storage_resolution.py`

- [ ] **Step 1: 编写失败测试**

测试目标：

- 广播 job 结构不新增字段
- `default + source` 的模板态配置访问命中 `default_{source}`
- 普通租户 Cron 执行仍可正常命中 runtime scope

- [ ] **Step 2: 运行测试，确认失败**

Run: `venv/bin/python -m pytest tests/unit/app/test_cron_template_storage_resolution.py -v`

Expected: FAIL

- [ ] **Step 3: 实现 Cron 兼容改造**

实现要点：

- `api.py` 保持 `tenant_id/source_id/scope_id` 结构不变
- `executor.py` 不盲信 `scope_id` 决定模板配置路径
- 对 `default + source` 的配置访问改用 storage resolver
- 对普通租户运行态执行继续沿用 runtime scope
- `heartbeat.py` 等配置读取链统一跟随新规则

- [ ] **Step 4: 运行测试，确认通过**

Run: `venv/bin/python -m pytest tests/unit/app/test_cron_template_storage_resolution.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/swe/app/crons/api.py src/swe/app/crons/executor.py src/swe/app/crons/manager.py src/swe/app/crons/coordination.py src/swe/app/crons/heartbeat.py src/swe/app/tenant_context.py tests/unit/app/test_cron_template_storage_resolution.py
git commit -m "fix: keep cron runtime compatible with template storage"
```

## Task 6: 新增 `tenant_type` 并过滤模板记录

**Files:**
- Modify: `src/swe/app/workspace/tenant_init_source_store.py`
- Modify: `src/swe/app/routers/user_info.py`
- Test: `tests/unit/workspace/test_tenant_init_source_store_template_filter.py`

- [ ] **Step 1: 编写失败测试**

测试目标：

- 模板记录写入 `tenant_type=template`
- 普通租户记录写入 `tenant_type=tenant`
- 默认查询不返回模板记录

- [ ] **Step 2: 运行测试，确认失败**

Run: `venv/bin/python -m pytest tests/unit/workspace/test_tenant_init_source_store_template_filter.py -v`

Expected: FAIL

- [ ] **Step 3: 实现 store 与 user_info 过滤逻辑**

实现要点：

- 增加 `tenant_type`
- 模板记录仅超管显式包含时可见
- `get_by_source()`、`get_all()`、`get_by_tenant_prefix()`、`get_bbk_by_source()` 默认过滤模板

- [ ] **Step 4: 运行测试，确认通过**

Run: `venv/bin/python -m pytest tests/unit/workspace/test_tenant_init_source_store_template_filter.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/swe/app/workspace/tenant_init_source_store.py src/swe/app/routers/user_info.py tests/unit/workspace/test_tenant_init_source_store_template_filter.py
git commit -m "feat: classify template tenant records with tenant_type"
```

## Task 7: 补齐 backup / 边缘链路与回归验证

**Files:**
- Modify: `src/swe/app/backup/service.py`
- Modify: `src/swe/app/backup/worker.py`
- Modify: `src/swe/app/backup/shell_service.py`
- Modify: `src/swe/app/backup/shell_worker.py`
- Modify: `src/swe/app/routers/tracing.py`
- Modify: `src/swe/app/routers/internal.py`
- Test: `tests/unit/app/test_backup_template_storage_resolution.py`

- [ ] **Step 1: 编写失败测试**

覆盖：

- 模板目录纳入 backup / restore
- tracing/internal 读取不再错误命中旧 scope

- [ ] **Step 2: 运行测试，确认失败**

Run: `venv/bin/python -m pytest tests/unit/app/test_backup_template_storage_resolution.py -v`

Expected: FAIL

- [ ] **Step 3: 实现边缘链路兼容**

实现要点：

- backup/restore 包含模板目录
- tracing/internal 的 tenant 解析与 storage 规则对齐

- [ ] **Step 4: 运行针对性测试与一轮回归**

Run: `venv/bin/python -m pytest tests/unit/config tests/unit/workspace tests/unit/providers tests/unit/app -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/swe/app/backup/service.py src/swe/app/backup/worker.py src/swe/app/backup/shell_service.py src/swe/app/backup/shell_worker.py src/swe/app/routers/tracing.py src/swe/app/routers/internal.py tests/unit/app/test_backup_template_storage_resolution.py
git commit -m "fix: align backup and edge paths with template storage"
```

## 自检结论

- 需求覆盖：已覆盖模板目录、普通租户、Provider、Env、Channel、Skills、MCP、Cron、DB、Backup
- 占位符检查：无 `TODO/TBD`
- 类型一致性：全篇使用 `tenant_type`，未再使用已否决的 `storage_tenant_id`

## 执行交接

Plan complete and saved to `docs/superpowers/plans/2026-06-09-source-template-storage-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
