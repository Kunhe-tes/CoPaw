# User Identity Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不影响对话与定时任务主流程的前提下，补齐 `tenant_name` / `bbk_id` 的初始化写入与后续本地读取链路，确保 cron 广播与 tracing 后续尽量拿到非空身份字段。

**Architecture:** 将身份补齐能力收口到统一 helper。只有租户初始化写入 `swe_tenant_init_source` 的链路允许使用 `USER_INFO_API_URL` 做兜底；对话、定时任务和 cron 广播后续链路只读取本地 `swe_tenant_init_source`，不再触发远端查询。广播场景优先使用请求显式传入的目标身份，缺失时再回退本地表。

**Tech Stack:** Python, FastAPI, httpx, pytest, MySQL-backed store

---

### Task 1: 收口统一身份补齐 helper

**Files:**
- Create: `src/swe/app/identity_resolver.py`
- Test: `tests/unit/app/test_identity_resolver.py`

- [x] **Step 1: 写 helper 单测，覆盖已有值优先、本地表优先、远端兜底、本地链路禁用远端**

```python
resolved = await resolve_user_identity(
    tenant_id="tenant-a",
    source_id="source-a",
    user_name=None,
    bbk_id=None,
    allow_remote_lookup=False,
)
assert resolved.user_name is None
assert resolved.bbk_id is None
```

- [x] **Step 2: 运行测试确认失败或缺能力**

Run: `pytest tests/unit/app/test_identity_resolver.py -q`
Expected: 初始阶段因 helper 或依赖逻辑未完整实现而失败

- [x] **Step 3: 实现 `resolve_user_identity(...)`**

```python
async def resolve_user_identity(
    *,
    tenant_id: str | None,
    source_id: str | None,
    user_name: str | None,
    bbk_id: str | None,
    headers: Optional[dict[str, str]] = None,
    allow_remote_lookup: bool = True,
) -> ResolvedIdentity:
    ...
```

- [x] **Step 4: 运行测试确认 helper 行为通过**

Run: `pytest tests/unit/app/test_identity_resolver.py -q`
Expected: PASS


### Task 2: 为 `swe_tenant_init_source` 增加本地身份读取方法

**Files:**
- Modify: `src/swe/app/workspace/tenant_init_source_store.py`
- Test: `tests/unit/workspace/test_tenant_init_source.py`

- [x] **Step 1: 写 store 单测，覆盖按 `tenant_id + source_id` 查询身份字段**

```python
result = await store.get_tenant_source_info("tenant-1", "RMASSIST")
assert result == {"tenant_name": "张三", "bbk_id": "3301"}
```

- [x] **Step 2: 运行相关测试确认失败**

Run: `pytest tests/unit/workspace/test_tenant_init_source.py -q -k "TestGetTenantSourceInfo"`
Expected: FAIL，提示缺少查询方法

- [x] **Step 3: 实现本地查询方法**

```python
async def get_tenant_source_info(
    self,
    tenant_id: str,
    source_id: str,
) -> dict | None:
    query = (
        "SELECT tenant_name, bbk_id FROM swe_tenant_init_source "
        "WHERE tenant_id = %s AND source_id = %s LIMIT 1"
    )
```

- [x] **Step 4: 运行测试确认通过**

Run: `pytest tests/unit/workspace/test_tenant_init_source.py -q -k "TestGetTenantSourceInfo"`
Expected: PASS


### Task 3: 仅在租户初始化链路允许远端兜底

**Files:**
- Modify: `src/swe/app/middleware/tenant_workspace.py`
- Reference: `src/swe/app/routers/user_info.py`
- Test: `tests/unit/app/test_identity_resolver.py`

- [x] **Step 1: 在 `TenantWorkspaceMiddleware` 中接入 helper**

```python
resolved_identity = await resolve_user_identity(
    tenant_id=getattr(request.state, "tenant_id", None) or tenant_id,
    source_id=source_id,
    user_name=user_name,
    bbk_id=bbk_id,
    headers={...},
    allow_remote_lookup=True,
)
```

- [x] **Step 2: 确认 header 优先，只有字段缺失时才会触发远端兜底**

Run: `pytest tests/unit/app/test_identity_resolver.py -q`
Expected: PASS，已有值时不调用远端

- [x] **Step 3: 确认补齐结果继续传入 bootstrap / `swe_tenant_init_source` 写入链路**

```python
await pool.ensure_bootstrap(
    ...,
    tenant_name=resolved_identity.user_name,
    bbk_id=resolved_identity.bbk_id,
)
```


### Task 4: 对话与定时任务后续链路只读本地，不走远端

**Files:**
- Modify: `src/swe/app/runner/runner.py`
- Modify: `src/swe/app/crons/executor.py`
- Test: `tests/unit/app/test_identity_resolver.py`

- [x] **Step 1: 在对话 trace 创建前只允许本地读取**

```python
resolved_identity = await resolve_user_identity(
    tenant_id=getattr(request, "user_id", None),
    source_id=_request_source_id(request),
    user_name=_request_user_name(request),
    bbk_id=_request_bbk_id(request),
    allow_remote_lookup=False,
)
```

- [x] **Step 2: 在 cron text / agent trace 创建前只允许本地读取**

```python
resolved_identity = await resolve_user_identity(
    tenant_id=getattr(job, "tenant_id", None),
    source_id=job.source_id,
    user_name=job.tenant_name,
    bbk_id=job.bbk_id,
    allow_remote_lookup=False,
)
```

- [x] **Step 3: 运行 helper 测试确认禁用远端查询时不会访问外部接口**

Run: `pytest tests/unit/app/test_identity_resolver.py -q`
Expected: PASS


### Task 5: 保持 cron 广播身份传递闭环

**Files:**
- Modify: `src/swe/app/crons/api.py`
- Test: `tests/unit/app/test_external_cron_scope_refresh.py`

- [x] **Step 1: 统一广播请求身份优先级**

```python
target_identity = context.target_identity_by_tenant.get(tenant_id, {})
target_tenant_name = _optional_text(target_identity.get("tenant_name"))
target_bbk_id = _optional_text(target_identity.get("bbk_id"))
if not target_tenant_name or not target_bbk_id:
    fallback_name, fallback_bbk_id = await _resolve_broadcast_target_identity(
        tenant_id,
        context.source_id,
    )
```

- [x] **Step 2: 保证写入广播子任务时使用补齐后的身份字段**

```python
return source_job.model_copy(
    update={
        "tenant_name": target_tenant_name,
        "bbk_id": target_bbk_id,
    },
)
```

- [x] **Step 3: 运行广播相关测试或记录环境阻塞项**

Run: `pytest tests/unit/app/test_external_cron_scope_refresh.py -q`
Expected: 若环境缺少 `croniter`，记录收集阶段失败原因；否则应通过


### Task 6: 回归验证与文档补充

**Files:**
- Modify: `AGENTS.md`
- Verify: `src/swe/app/identity_resolver.py`
- Verify: `src/swe/app/workspace/tenant_init_source_store.py`
- Verify: `src/swe/app/middleware/tenant_workspace.py`
- Verify: `src/swe/app/runner/runner.py`
- Verify: `src/swe/app/crons/executor.py`
- Verify: `src/swe/app/crons/api.py`

- [x] **Step 1: 运行当前环境可执行的回归测试**

Run: `.venv/bin/python -m pytest tests/unit/app/test_identity_resolver.py tests/unit/workspace/test_tenant_init_source.py -q`
Expected: PASS

- [x] **Step 2: 运行语法校验**

Run: `.venv/bin/python -m py_compile src/swe/app/identity_resolver.py src/swe/app/workspace/tenant_init_source_store.py src/swe/app/middleware/tenant_workspace.py src/swe/app/runner/runner.py src/swe/app/crons/executor.py src/swe/app/crons/api.py`
Expected: 无输出，返回码 0

- [x] **Step 3: 补充协作规则**

```markdown
- 对于涉及 3 个及以上模块、调用链较长、需要跨入口统一行为约束的问题，先使用 superpowers 进行分析；如果需求边界、数据流或改动策略还不够明确，先补充轻量 spec/plan，再进入实现
```

- [x] **Step 4: 记录当前遗留环境问题**

```text
tests/unit/app/test_external_cron_scope_refresh.py
当前环境收集失败：ModuleNotFoundError: croniter
```
