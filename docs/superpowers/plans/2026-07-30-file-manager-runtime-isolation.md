# File Manager Runtime Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Serve every Chat File Manager operation from the selected tenant-Agent directory without starting that Agent's Workspace runtime, while moving synchronous filesystem work off the async event loop.

**Architecture:** Add a narrow workspace-directory resolver in src/swe/app/agent_context.py. It preserves route/header/active-Agent selection but reads tenant-local configuration and validates the configured path under the request's tenant workspaces directory instead of calling MultiAgentManager.get_agent(). Route handlers use a bounded AnyIO worker helper to execute the existing descriptor-safe FileManagerService; no security-sensitive filesystem method is rewritten in this phase.

**Tech Stack:** Python 3.10+, FastAPI, AnyIO, Pydantic, pytest, Starlette streaming responses, GitNexus.

---

## Scope and sequencing

This is Phase 1 of the approved File Manager runtime and performance design. It intentionally excludes three independently deployable changes:

- streaming upload bodies and bounded large-file preview classification;
- directory snapshot cache and snapshot-aware cursors;
- recycle-index pagination and SQLite/WAL migration.

Implement those in separate plans only after Phase 1 metrics establish the current filesystem and archive workloads. Do not weaken O_NOFOLLOW, descriptor fstat checks, revision rechecks, atomic publication, or archive transition recovery in this plan.

## File map

| File | Responsibility |
| --- | --- |
| src/swe/app/agent_context.py | Add the public, runtime-free workspace directory resolver while retaining the existing Agent selection helpers. |
| src/swe/app/file_manager_execution.py | Provide typed, bounded read and mutation worker lanes for synchronous File Manager calls. |
| src/swe/app/routers/console.py | Resolve the directory once per File Manager request, dispatch service work to the appropriate lane, and set download Content-Length. |
| src/swe/app/file_manager.py | Cache the process cursor secret and construct a successful text-save response without reopening the file. |
| tests/unit/routers/test_agents_tenant_scope.py | Test direct resolver selection, tenant/source scope, and fail-closed path validation. |
| tests/unit/routers/test_console_chat_stream.py | Prove all File Manager HTTP operations use the direct resolver and retain route behavior. |
| tests/unit/app/test_file_manager_execution.py | Test bounded worker-lane dispatch and exception propagation. |
| tests/unit/app/test_file_manager.py | Test cursor-secret caching and the no-reread successful save path. |

### Task 1: Define direct workspace-resolution behavior with tests

**Files:**
- Modify: tests/unit/routers/test_agents_tenant_scope.py
- Test: tests/unit/routers/test_agents_tenant_scope.py

- [ ] **Step 1: Write the failing success-path tests**

Construct a TenantWorkspaceContext rooted at tmp_path / "default_ruice", a tenant config with two enabled profiles, and a MultiAgentManager whose get_agent raises AssertionError. Cover route Agent, X-Agent-Id, and active-Agent fallback precedence.

~~~python
def test_file_manager_workspace_resolver_uses_path_agent_without_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_root = tmp_path / "default_ruice"
    selected = tenant_root / "workspaces" / "writer"
    selected.mkdir(parents=True)
    request = SimpleNamespace(
        state=SimpleNamespace(
            tenant_id="default",
            source_id="ruice",
            workspace=TenantWorkspaceContext("default_ruice", tenant_root),
            agent_id="writer",
        ),
        headers={"X-Agent-Id": "reader"},
        app=SimpleNamespace(
            state=SimpleNamespace(
                multi_agent_manager=SimpleNamespace(
                    get_agent=lambda *_args, **_kwargs: pytest.fail(
                        "File Manager must not start an Agent runtime",
                    ),
                ),
            ),
        ),
    )
    config = SimpleNamespace(
        agents=SimpleNamespace(
            active_agent="reader",
            profiles={
                "writer": SimpleNamespace(
                    workspace_dir=str(selected), enabled=True,
                ),
                "reader": SimpleNamespace(
                    workspace_dir=str(tenant_root / "workspaces" / "reader"),
                    enabled=True,
                ),
            },
        ),
    )
    monkeypatch.setattr(
        agent_context, "_get_tenant_aware_config", lambda **_kwargs: config,
    )

    resolved = asyncio.run(
        agent_context.resolve_file_manager_workspace_dir(request),
    )

    assert resolved == selected.resolve()
~~~

Add one test with no route Agent or header to verify active-Agent selection. Add a source-scoped default test asserting that _get_tenant_aware_config receives logical tenant default, source ruice, and scope None while the returned path remains below the effective tenant root.

- [ ] **Step 2: Write failing fail-closed tests**

Add parameterized tests for a missing profile (404), disabled profile (403), missing workspace directory (404), and a profile path outside tenant_root / "workspaces" (403). Assert the public error does not disclose the candidate host path.

~~~python
with pytest.raises(HTTPException) as raised:
    asyncio.run(agent_context.resolve_file_manager_workspace_dir(request))

assert raised.value.status_code == expected_status
assert str(outside_workspace) not in str(raised.value.detail)
~~~

- [ ] **Step 3: Run tests to verify failure**

Run:

~~~bash
../../venv/bin/python -m pytest \
  tests/unit/routers/test_agents_tenant_scope.py \
  -k "file_manager_workspace_resolver" -v
~~~

Expected: FAIL because resolve_file_manager_workspace_dir does not exist.

- [ ] **Step 4: Commit the failing tests**

~~~bash
git add tests/unit/routers/test_agents_tenant_scope.py
git commit -m "test(file-manager): define runtime-free workspace resolution"
~~~

### Task 2: Implement the runtime-free resolver

**Files:**
- Modify: src/swe/app/agent_context.py:88-270
- Test: tests/unit/routers/test_agents_tenant_scope.py

- [ ] **Step 1: Add the public resolver beside get_agent_for_request**

Import Path and add the resolver below _get_tenant_aware_config. Reuse _resolve_target_agent_id and _get_tenant_aware_config; do not duplicate Agent selection in Console.

~~~python
async def resolve_file_manager_workspace_dir(request: Request) -> Path:
    """Resolve a verified Agent directory without starting its runtime."""
    from fastapi import HTTPException

    tenant_id = _resolve_tenant_id(request)
    source_id = _resolve_source_id(request)
    scope_id = _resolve_scope_id(request)
    effective_tenant_id = _resolve_effective_tenant_id(
        tenant_id, source_id, scope_id,
    )
    tenant_workspace = getattr(request.state, "workspace", None)
    if not isinstance(tenant_workspace, TenantWorkspaceContext):
        raise HTTPException(
            status_code=503, detail="Tenant workspace is unavailable",
        )
    if effective_tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant context required")

    config = _get_tenant_aware_config(tenant_id, source_id, scope_id)
    requested_agent_id, _ = _resolve_target_agent_id(request)
    agent_id = requested_agent_id or config.agents.active_agent or "default"
    profile = config.agents.profiles.get(agent_id)
    if profile is None:
        raise HTTPException(
            status_code=404, detail=f"Agent '{agent_id}' not found",
        )
    if not getattr(profile, "enabled", True):
        raise HTTPException(
            status_code=403, detail=f"Agent '{agent_id}' is disabled",
        )

    workspace_dir = Path(profile.workspace_dir).expanduser().resolve()
    allowed_root = Path(tenant_workspace.workspace_dir).resolve() / "workspaces"
    try:
        workspace_dir.relative_to(allowed_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=403, detail="Agent workspace is unavailable",
        ) from exc
    if not workspace_dir.is_dir():
        raise HTTPException(
            status_code=404, detail=f"Agent '{agent_id}' not found",
        )
    return workspace_dir
~~~

Do not construct a path from effective_tenant_id. The middleware-supplied TenantWorkspaceContext is the only filesystem trust anchor; effective tenant remains part of identity validation and source/scope test coverage.

- [ ] **Step 2: Export the stable public API**

Add resolve_file_manager_workspace_dir to __all__ in src/swe/app/agent_context.py.

- [ ] **Step 3: Run resolver tests to verify success**

Run:

~~~bash
../../venv/bin/python -m pytest \
  tests/unit/routers/test_agents_tenant_scope.py \
  -k "file_manager_workspace_resolver" -v
~~~

Expected: PASS.

- [ ] **Step 4: Run impact analysis before router adoption**

Run GitNexus impact with upstream direction on get_file_manager_directory, get_file_manager_file_preview, and resolve_file_manager_workspace_dir. Record direct callers and risk in the PR description. If any result is HIGH or CRITICAL, stop and review its direct caller list before editing it.

- [ ] **Step 5: Commit the resolver**

~~~bash
git add src/swe/app/agent_context.py tests/unit/routers/test_agents_tenant_scope.py
git commit -m "feat(file-manager): resolve workspace without runtime startup"
~~~

### Task 3: Add bounded File Manager worker lanes

**Files:**
- Create: src/swe/app/file_manager_execution.py
- Create: tests/unit/app/test_file_manager_execution.py

- [ ] **Step 1: Write failing worker-lane tests**

Create tests that run a synchronous callable through each lane, assert its return value is preserved, and assert a raised FileManagerPathError reaches the caller unchanged. Add a concurrency test with three mutation callables blocked on a threading.Event; instrument their active count and assert at most two run concurrently.

~~~python
@pytest.mark.asyncio
async def test_mutation_lane_limits_parallel_work() -> None:
    started = threading.Event()
    release = threading.Event()
    active = 0
    maximum = 0
    lock = threading.Lock()

    def blocking_call() -> None:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            if active == 2:
                started.set()
        release.wait(timeout=2)
        with lock:
            active -= 1

    tasks = [
        asyncio.create_task(run_file_manager_mutation(blocking_call))
        for _ in range(3)
    ]
    assert started.wait(timeout=2)
    await asyncio.sleep(0)
    assert maximum == 2
    release.set()
    await asyncio.gather(*tasks)
~~~

- [ ] **Step 2: Run tests to verify failure**

Run:

~~~bash
../../venv/bin/python -m pytest tests/unit/app/test_file_manager_execution.py -v
~~~

Expected: FAIL because swe.app.file_manager_execution does not exist.

- [ ] **Step 3: Implement the worker helper**

Create src/swe/app/file_manager_execution.py with typed AnyIO capacity limiters. Mutation capacity is intentionally smaller than ordinary reads.

~~~python
from __future__ import annotations

from functools import partial
from typing import Callable, ParamSpec, TypeVar

import anyio

P = ParamSpec("P")
T = TypeVar("T")
_READ_LIMITER = anyio.CapacityLimiter(8)
_MUTATION_LIMITER = anyio.CapacityLimiter(2)

async def _run(
    limiter: anyio.CapacityLimiter,
    function: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    return await anyio.to_thread.run_sync(
        partial(function, *args, **kwargs), limiter=limiter,
    )

async def run_file_manager_read(
    function: Callable[P, T], *args: P.args, **kwargs: P.kwargs,
) -> T:
    return await _run(_READ_LIMITER, function, *args, **kwargs)

async def run_file_manager_mutation(
    function: Callable[P, T], *args: P.args, **kwargs: P.kwargs,
) -> T:
    return await _run(_MUTATION_LIMITER, function, *args, **kwargs)
~~~

- [ ] **Step 4: Run tests to verify success**

Run:

~~~bash
../../venv/bin/python -m pytest tests/unit/app/test_file_manager_execution.py -v
~~~

Expected: PASS.

- [ ] **Step 5: Commit worker lanes**

~~~bash
git add src/swe/app/file_manager_execution.py tests/unit/app/test_file_manager_execution.py
git commit -m "feat(file-manager): bound filesystem worker concurrency"
~~~

### Task 4: Route all File Manager endpoints through the resolver and workers

**Files:**
- Modify: src/swe/app/routers/console.py:20-45,1024-1301
- Modify: tests/unit/routers/test_console_chat_stream.py:85-105
- Test: tests/unit/routers/test_console_chat_stream.py

- [ ] **Step 1: Convert the HTTP fixture to direct resolution**

Replace _build_file_manager_client's get_agent_for_request monkeypatch with a direct resolver fake. Also patch get_agent_for_request to fail, so every existing File Manager endpoint test proves it cannot start a runtime.

~~~python
async def _fake_resolve_file_manager_workspace_dir(_request):
    return workspace_dir

async def _fail_if_runtime_requested(_request):
    raise AssertionError("File Manager must not resolve an Agent runtime")

monkeypatch.setattr(
    console_router,
    "resolve_file_manager_workspace_dir",
    _fake_resolve_file_manager_workspace_dir,
)
monkeypatch.setattr(
    console_router, "get_agent_for_request", _fail_if_runtime_requested,
)
~~~

Add a parameterized smoke test for list, read, download, save, upload, archive, restore, and purge that counts resolver calls.

- [ ] **Step 2: Run route tests to verify failure**

Run:

~~~bash
../../venv/bin/python -m pytest tests/unit/routers/test_console_chat_stream.py -q
~~~

Expected: FAIL because File Manager routes still call get_agent_for_request.

- [ ] **Step 3: Adopt the resolver in every File Manager route**

Import resolve_file_manager_workspace_dir, run_file_manager_read, and run_file_manager_mutation. In every File Manager endpoint, replace the runtime lookup:

~~~python
workspace = await get_agent_for_request(request)
service = get_file_manager_service(Path(workspace.workspace_dir))
~~~

with:

~~~python
workspace_dir = await resolve_file_manager_workspace_dir(request)
service = get_file_manager_service(workspace_dir)
~~~

Dispatch the service methods through the correct lane:

~~~python
listing = await run_file_manager_read(
    service.list_directory, root, path, cursor=cursor, query=q or None,
)
preview = await run_file_manager_read(service.read_text_preview, root, path)
download = await run_file_manager_read(
    service.open_file_for_download, root, path,
)
saved = await run_file_manager_mutation(
    service.save_text, body.root, body.path, body.content, body.revision,
)
item = await run_file_manager_mutation(
    service.upload_bytes, root, path, filename, content,
)
archived = await run_file_manager_mutation(
    service.archive_file, root, path, actor=_file_manager_actor(request),
)
restored = await run_file_manager_mutation(
    service.restore_recycle_item, archive_item_id, actor=_file_manager_actor(request),
)
purged = await run_file_manager_mutation(
    service.purge_recycle_item, archive_item_id, actor=_file_manager_actor(request),
)
~~~

Do not move UploadFile.read() in this task; chunked upload is a separately planned Phase 2 change.

- [ ] **Step 4: Set Content-Length from the opened snapshot**

Use only FileManagerDownload.size_bytes:

~~~python
headers={
    "Content-Disposition": _file_manager_download_disposition(download.filename),
    "Content-Length": str(download.size_bytes),
}
~~~

Do not reopen or stat the pathname after authorization.

- [ ] **Step 5: Run route tests to verify success**

Run:

~~~bash
../../venv/bin/python -m pytest tests/unit/routers/test_console_chat_stream.py -q
~~~

Expected: PASS.

- [ ] **Step 6: Commit route migration**

~~~bash
git add src/swe/app/routers/console.py tests/unit/routers/test_console_chat_stream.py
git commit -m "feat(file-manager): avoid runtime startup in console routes"
~~~

### Task 5: Remove repeated secret and successful-save I/O

**Files:**
- Modify: src/swe/app/file_manager.py:176-311,559-666
- Modify: tests/unit/app/test_file_manager.py
- Test: tests/unit/app/test_file_manager.py

- [ ] **Step 1: Write failing cache and save-response tests**

Add a test that spies on _read_cursor_secret, creates two services with the same fallback configuration, and asserts the secret file is read once. Clear the cache before and after every test that mutates SWE_FILE_MANAGER_CURSOR_SECRET or SECRET_DIR.

Add a save test that records calls to service.read_text_preview after obtaining the initial revision; a successful save must not call it again.

~~~python
result = service.save_text("working", "document.md", "after", revision)

assert result.content == "after"
assert result.revision == hashlib.sha256(b"after").hexdigest()
assert preview_calls == []
~~~

- [ ] **Step 2: Run tests to verify failure**

Run:

~~~bash
../../venv/bin/python -m pytest tests/unit/app/test_file_manager.py \
  -k "cursor_secret_cache or save_text_does_not_reread" -v
~~~

Expected: FAIL because neither optimization exists.

- [ ] **Step 3: Cache only the process-wide secret lookup**

Rename the current body to _load_or_create_cursor_secret_uncached and wrap it:

~~~python
from functools import cache, wraps

@cache
def _load_or_create_cursor_secret() -> bytes:
    return _load_or_create_cursor_secret_uncached()
~~~

Do not cache FileManagerService instances or workspace paths.

- [ ] **Step 4: Build the known successful text response directly**

After os.replace and os.fsync(parent_fd) succeed, return:

~~~python
return FileManagerTextPreview(
    path=normalised_path,
    size_bytes=len(encoded_content),
    is_text=True,
    content=content,
    editable=True,
    revision=hashlib.sha256(encoded_content).hexdigest(),
)
~~~

Keep both pre-replacement _content_revision_for_entry checks unchanged. All exception cleanup remains unchanged.

- [ ] **Step 5: Run tests to verify success**

Run:

~~~bash
../../venv/bin/python -m pytest tests/unit/app/test_file_manager.py \
  -k "cursor_secret_cache or save_text_does_not_reread" -v
~~~

Expected: PASS.

- [ ] **Step 6: Commit I/O reductions**

~~~bash
git add src/swe/app/file_manager.py tests/unit/app/test_file_manager.py
git commit -m "perf(file-manager): avoid repeated secret and save reads"
~~~

### Task 6: Full regression, impact review, and handoff

**Files:**
- Modify: docs/superpowers/specs/2026-07-30-chat-file-manager-runtime-and-performance-design.md only if implementation intentionally changes the approved contract.
- Test: tests/unit/app/test_file_manager.py
- Test: tests/unit/app/test_file_manager_execution.py
- Test: tests/unit/routers/test_console_chat_stream.py
- Test: tests/unit/routers/test_agents_tenant_scope.py

- [ ] **Step 1: Run the complete Phase 1 suite**

Run:

~~~bash
../../venv/bin/python -m pytest \
  tests/unit/app/test_file_manager.py \
  tests/unit/app/test_file_manager_execution.py \
  tests/unit/routers/test_console_chat_stream.py \
  tests/unit/routers/test_agents_tenant_scope.py -q
~~~

Expected: PASS with no skipped new tests.

- [ ] **Step 2: Run static formatting check**

Run:

~~~bash
../../venv/bin/python -m black --check \
  src/swe/app/agent_context.py \
  src/swe/app/file_manager.py \
  src/swe/app/file_manager_execution.py \
  src/swe/app/routers/console.py \
  tests/unit/app/test_file_manager.py \
  tests/unit/app/test_file_manager_execution.py \
  tests/unit/routers/test_agents_tenant_scope.py \
  tests/unit/routers/test_console_chat_stream.py
~~~

Expected: all files would be left unchanged.

- [ ] **Step 3: Run GitNexus change detection before final commit**

Run GitNexus detect_changes with scope all and base_ref main. Confirm only the resolver, File Manager service, Console File Manager routes, and the new execution helper are affected. If risk is HIGH or CRITICAL, inspect every direct caller before continuing.

- [ ] **Step 4: Verify runtime startup remains absent**

Run:

~~~bash
../../venv/bin/python -m pytest \
  tests/unit/routers/test_console_chat_stream.py \
  -k "file_manager and runtime" -v
~~~

Expected: PASS; the get_agent_for_request test double must not be called.

- [ ] **Step 5: Commit documentation clarification only if needed**

Only if implementation changes an approved contract:

~~~bash
git add docs/superpowers/specs/2026-07-30-chat-file-manager-runtime-and-performance-design.md
git commit -m "docs(file-manager): clarify phase one verification"
~~~

Otherwise, make no empty commit.

## Plan self-review

- **Spec coverage:** Phase 1 resolver, no-runtime guarantee, bounded worker lanes, cursor-secret caching, save reread removal, Content-Length, and acceptance tests map to Tasks 1–6. The Phase 2/3 design items are intentional separate projects, not omissions.
- **Placeholder scan:** Every code-bearing task names exact files, symbols, test cases, commands, and expected outcomes.
- **Type consistency:** resolve_file_manager_workspace_dir returns Path; all Console endpoints pass that Path to get_file_manager_service. run_file_manager_read and run_file_manager_mutation are defined before route adoption.
