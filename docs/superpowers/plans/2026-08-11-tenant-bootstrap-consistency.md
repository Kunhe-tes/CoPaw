# Tenant Bootstrap Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make tenant bootstrap a cross-pod, all-or-nothing readiness transition; recover only invalid bootstrap artifacts; and require source templates to be provisioned explicitly before tenant traffic uses them.

**Architecture:** `TenantWorkspacePool` remains the only runtime bootstrap gateway. It serializes each effective storage tenant through a non-blocking `fcntl.flock` file lock and uses strict artifact validation before considering a tenant ready. `TenantInitializer` owns deterministic artifact creation/recovery, while a separate `SourceTemplateProvisioner` creates or repairs `default_<source>` under an internal/admin API or CLI command; normal traffic only checks its readiness.

**Tech Stack:** Python 3.11, asyncio, `fcntl.flock` on the shared RWX volume, FastAPI, Pydantic, pytest/pytest-asyncio, Click.

---

## File map

| File | Responsibility |
| --- | --- |
| `src/swe/app/workspace/bootstrap_lock.py` | Async-compatible `flock` acquisition, timeout/error types, and the stable source-template lock path helper. |
| `src/swe/app/workspace/bootstrap_state.py` | Shared bootstrap-unavailable errors, pure strict readiness checks, durable atomic JSON writes, ready marker, and recovery-backup helpers. |
| `src/swe/app/workspace/source_template_provisioner.py` | Explicit, idempotent source-template provisioning from `default`, using staging and publish/rollback. |
| `src/swe/app/workspace/tenant_initializer.py` | Remove lazy template creation; use strict bootstrap validation and the atomic helpers while creating/recovering bootstrap-owned artifacts. |
| `src/swe/app/workspace/tenant_pool.py` | Cross-process lock, source-template precondition, recover-then-validate sequence, structured events, and typed unavailable errors. |
| `src/swe/app/middleware/tenant_workspace.py` | Translate bootstrap-unavailable failures into retryable HTTP 503 responses with `Retry-After: 2`. |
| `src/swe/app/routers/internal.py` | Token-protected internal source-template ensure endpoint. |
| `src/swe/cli/init_cmd.py`, `src/swe/cli/main.py` | Dedicated `swe init-source-template --source-id <id>` command routed through the provisioner. |
| `src/swe/app/routers/{agent,config,mcp,providers,skills}.py`, `src/swe/app/workspace/file_broadcast.py` | Remove direct `TenantInitializer.ensure_seeded_bootstrap()` calls; await the pool instead. |
| `tests/unit/workspace/test_bootstrap_lock.py` | Cross-process lock, timeout, lock I/O failure, and event-loop responsiveness regression tests. |
| `tests/unit/workspace/test_bootstrap_state.py` | Strict readiness, backup/recovery, `.bak` deletion on success, and failure retention tests. |
| `tests/unit/workspace/test_source_template_provisioner.py` | Create/repair/unchanged/fail-closed source-template tests. |
| `tests/unit/workspace/test_tenant_initializer.py`, `tests/unit/app/test_tenant_pool.py`, `tests/unit/app/test_tenant_workspace.py` | End-to-end bootstrap and retryable middleware tests. |
| `tests/unit/routers/test_internal_source_template.py` | Internal endpoint authorization and response-contract tests. |
| Existing router-specific test files | Adapt mocks/coroutines and assert every target-bootstrap path uses the pool. |

### Task 1: Add the async cross-process bootstrap lock

**Files:**
- Create: `src/swe/app/workspace/bootstrap_lock.py`
- Create: `tests/unit/workspace/test_bootstrap_lock.py`

- [ ] **Step 1: Write the failing lock behavior tests.**

  Cover three contractual paths: another process holding `<tenant>/.bootstrap.lock` causes a bounded timeout, an unexpected `flock` error is not treated as contention, and waiting yields to the event loop.

  ```python
  @pytest.mark.asyncio
  async def test_lock_timeout_is_not_a_success(tmp_path: Path) -> None:
      lock_path = tmp_path / "scope-a" / ".bootstrap.lock"
      with _hold_lock_in_child_process(lock_path):
          lock = AsyncFlock(lock_path, timeout_seconds=0.02, poll_seconds=0.005)
          with pytest.raises(BootstrapLockTimeout):
              async with lock:
                  pass


  @pytest.mark.asyncio
  async def test_lock_wait_does_not_block_event_loop(tmp_path: Path) -> None:
      lock_path = tmp_path / "scope-a" / ".bootstrap.lock"
      with _hold_lock_in_child_process(lock_path):
          waiter = asyncio.create_task(
              AsyncFlock(lock_path, timeout_seconds=0.05, poll_seconds=0.005).__aenter__()
          )
          await asyncio.sleep(0)
          assert not waiter.done()
          waiter.cancel()
          with suppress(asyncio.CancelledError):
              await waiter
  ```

- [ ] **Step 2: Run the new tests and verify they fail because the module does not exist.**

  Run: `venv/bin/python -m pytest tests/unit/workspace/test_bootstrap_lock.py -q`

  Expected: collection fails with `ModuleNotFoundError: swe.app.workspace.bootstrap_lock`.

- [ ] **Step 3: Implement the minimal lock contract.**

  Define these public types and behavior; do not add a fallback lock mode:

  Export `BootstrapLockTimeout`, `BootstrapLockFailure`, and `AsyncFlock(lock_path, timeout_seconds=30.0, poll_seconds=0.05)`. `AsyncFlock` is an async context manager returning itself after successful acquisition.

  `__aenter__` must create the parent and open the lock file in `a+`, then repeatedly call `fcntl.flock(fd, LOCK_EX | LOCK_NB)` in `asyncio.to_thread`. Retry only `BlockingIOError`/`EAGAIN`/`EACCES`; use `await asyncio.sleep(poll_seconds)` between retries; raise `BootstrapLockTimeout` at the configured deadline (30 seconds in production); wrap all other open/flock/unlock errors in `BootstrapLockFailure`. Keep the file descriptor open until `__aexit__` unlocks and closes it. The pool will create the tenant directory before instantiating this lock so the tenant lock is exactly `<effective-tenant-root>/.bootstrap.lock`.

- [ ] **Step 4: Run the lock tests.**

  Run: `venv/bin/python -m pytest tests/unit/workspace/test_bootstrap_lock.py -q`

  Expected: PASS on Linux/macOS; mark the child-process `fcntl` assertion as Unix-only.

- [ ] **Step 5: Commit the isolated lock primitive.**

  ```bash
  git add src/swe/app/workspace/bootstrap_lock.py tests/unit/workspace/test_bootstrap_lock.py
  git commit -m "feat(workspace): add async tenant bootstrap file lock"
  ```

### Task 2: Define strict bootstrap readiness and durable bootstrap-owned JSON writes

**Files:**
- Create: `src/swe/app/workspace/bootstrap_state.py`
- Create: `tests/unit/workspace/test_bootstrap_state.py`

- [ ] **Step 1: Write failing strict-readiness and recovery-file tests.**

  Build a known-good tenant fixture with `config.json`, `workspaces/default/agent.json`, `chats.json`, `jobs.json`, `token_usage.json`, both `skill.json` manifests, required directories, and prompt files. Assert that a syntactically broken `config.json`, a disabled default profile, and an `agent.json` whose `workspace_dir` points elsewhere all return `ready=False` with the offending path in `invalid_json_paths`. Also assert a `.bootstrap.ready` marker never makes damaged artifacts ready.

  ```python
  def test_readiness_rejects_tolerant_loader_fallback(good_tenant: Path) -> None:
      config_path = good_tenant / "config.json"
      config_path.write_text("{broken", encoding="utf-8")

      readiness = inspect_bootstrap_readiness(good_tenant)

      assert not readiness.ready
      assert readiness.invalid_json_paths == (config_path,)


  def test_atomic_write_fsyncs_and_leaves_no_tmp_file(tmp_path: Path) -> None:
      path = tmp_path / "config.json"
      write_bootstrap_json(path, {"version": 1})
      assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1}
      assert list(tmp_path.glob(".config.json.*.tmp")) == []
  ```

- [ ] **Step 2: Run the new tests and verify they fail.**

  Run: `venv/bin/python -m pytest tests/unit/workspace/test_bootstrap_state.py -q`

  Expected: collection fails because `bootstrap_state` has not been added.

- [ ] **Step 3: Implement pure validation and atomic helpers.**

  Add a frozen result object and helpers with no tolerant config loading and no directory sweep:

  Export `TenantBootstrapUnavailable(retry_after_seconds=2)`, `SourceTemplateUnavailable`, and `BootstrapRecoveryFailure`, plus a frozen `BootstrapReadiness(ready, missing_paths, invalid_json_paths, reason)` value, `inspect_bootstrap_readiness(tenant_dir)`, `write_bootstrap_json(path, payload)`, `write_bootstrap_ready_marker(tenant_dir)`, and `move_to_recovery_backup(path)`.

  `inspect_bootstrap_readiness` must parse raw JSON using `json.loads`, then validate root config with `Config.model_validate` and agent config with `AgentProfileConfig.model_validate`. Require `config.agents.active_agent == "default"`; `profiles["default"].id == "default"` and `profiles["default"].enabled is True`; both root and agent `workspace_dir` equal `tenant_dir / "workspaces" / "default"`; required workspace directories/files from `TenantInitializer._WORKSPACE_REQUIRED_FILES`; JSON object roots for chats/jobs/token usage and both skill manifests; `skills` mappings in both manifests; and each manifest-declared managed skill directory to contain `SKILL.md`. It must never call `load_config`, `load_agent_config`, or `reconcile_*`; it ignores `.bootstrap.ready` for readiness.

  `write_bootstrap_json` must serialize into `.<name>.<random>.tmp` in the destination directory, `flush()` and `os.fsync()` the temp file, `os.replace()` it, then fsync the containing directory. On every ordinary exception, remove only the temp file it created. `move_to_recovery_backup` must rename only an explicitly passed invalid JSON file to `<original-name>.<uuid>.bak`; it must not glob for `.tmp` or `.bak` files.

- [ ] **Step 4: Run the readiness suite.**

  Run: `venv/bin/python -m pytest tests/unit/workspace/test_bootstrap_state.py -q`

  Expected: PASS.

- [ ] **Step 5: Commit the state primitive.**

  ```bash
  git add src/swe/app/workspace/bootstrap_state.py tests/unit/workspace/test_bootstrap_state.py
  git commit -m "feat(workspace): validate and atomically publish bootstrap state"
  ```

### Task 3: Remove lazy source-template creation and add explicit provisioning

**Files:**
- Create: `src/swe/app/workspace/source_template_provisioner.py`
- Modify: `src/swe/app/workspace/tenant_initializer.py:60-190, 520-640`
- Create: `tests/unit/workspace/test_source_template_provisioner.py`
- Modify: `tests/unit/workspace/test_tenant_init_source.py`

- [ ] **Step 1: Write failing provisioner tests.**

  Test missing source template creation, incomplete-template repair, unchanged ready template, invalid/missing `default/` failure, and normal `TenantInitializer` selection with an absent source template.

  ```python
  @pytest.mark.asyncio
  async def test_provisioner_creates_ready_source_template(default_template: Path) -> None:
      result = await SourceTemplateProvisioner(default_template.parent).ensure("ruice")

      assert result.status == "created"
      assert inspect_source_template_readiness(default_template.parent / "default_ruice").ready


  def test_initializer_never_creates_missing_source_template(tmp_path: Path) -> None:
      initializer = TenantInitializer(tmp_path, "tenant-a", source_id="ruice")

      assert initializer.template_name == "default_ruice"
      assert not (tmp_path / "default_ruice").exists()
  ```

- [ ] **Step 2: Run the provisioner tests and verify they fail.**

  Run: `venv/bin/python -m pytest tests/unit/workspace/test_source_template_provisioner.py -q`

  Expected: collection fails because `SourceTemplateProvisioner` does not exist; the legacy initializer test initially fails after its behavior is changed.

- [ ] **Step 3: Implement explicit source-template provisioning.**

  `TenantInitializer._resolve_template_name()` becomes a pure name resolver: no `exists()`, no `copytree`, no fallback to `default`, and no `_template_created_from_default` state. Delete `_create_source_template_from_default`, `_fix_template_config_paths`, and lazy provider-template creation methods/calls. When a source template is absent, seeding returns an unavailable error from the pool rather than copying from `default`.

  Define the provisioner interface:

  Export `SourceTemplateProvisionResult(source_id, template_name, status)`, where `status` is exactly `created`, `repaired`, or `ready`, and async `SourceTemplateProvisioner(base_working_dir).ensure(source_id)`.

  Validate `source_id` with `is_valid_identity_value`. Export `inspect_source_template_readiness(base_working_dir, source_id)`, which requires strict readiness of both `default_<source>` and its `SECRET_DIR/default_<source>/providers` directory. Acquire a stable lock outside the replaceable template directory, at `<base>/.source-template-locks/<source-id>.lock`, through `AsyncFlock`. First require strict readiness of `<base>/default`; if it is not ready, log `source_template_provisioning_failed` and raise `SourceTemplateUnavailable` without creating `default_<source>`. Run the blocking copy, path rewrite, staged validation, directory publication, and backup cleanup in `asyncio.to_thread` while holding the lock. Build a complete sibling staging directory from `default`, rewrite only workspace paths from `default/workspaces` to `default_<source>/workspaces`, validate staging, and publish with same-filesystem `Path.replace`. For an incomplete target, rename it to an explicit recovery `.bak`, publish staging, and delete the backup only after strict readiness passes; restore the backup if publish/readiness fails. A ready target is returned unchanged. Copy the corresponding `SECRET_DIR/default/providers` into the staged source-template secret directory as part of the same provisioning operation, and fail rather than silently creating it during a normal tenant request. Emit `source_template_provisioning_started`, `source_template_provisioning_ready`, `source_template_provisioning_repaired`, and `source_template_provisioning_failed` with source id, outcome, and duration only.

- [ ] **Step 4: Run the provisioner tests.**

  Run: `venv/bin/python -m pytest tests/unit/workspace/test_source_template_provisioner.py tests/unit/workspace/test_tenant_initializer.py tests/unit/workspace/test_tenant_init_source.py -q`

  Expected: PASS.

- [ ] **Step 5: Commit source-template isolation.**

  ```bash
  git add src/swe/app/workspace/source_template_provisioner.py src/swe/app/workspace/tenant_initializer.py tests/unit/workspace/test_source_template_provisioner.py tests/unit/workspace/test_tenant_initializer.py tests/unit/workspace/test_tenant_init_source.py
  git commit -m "feat(workspace): require explicit source template provisioning"
  ```

### Task 4: Make `TenantInitializer` recover only invalid bootstrap-owned artifacts

**Files:**
- Modify: `src/swe/app/workspace/tenant_initializer.py:213-314, 440-750, 1150-1257`
- Modify: `tests/unit/workspace/test_tenant_initializer.py`

- [ ] **Step 1: Add failing recovery tests.**

  Test corrupt root config, corrupt agent config, and a malformed manifest. Test that a semantically ready config is neither backed up nor overwritten. Test the cleanup contract in both directions.

  ```python
  def test_recovery_removes_backup_after_ready_state(good_template: Path) -> None:
      tenant_dir = _seed_corrupt_tenant(good_template.parent, "tenant-a")
      (tenant_dir / "config.json").write_text("{broken", encoding="utf-8")

      result = TenantInitializer(good_template.parent, "tenant-a").recover_seeded_bootstrap()

      assert result.recovered_paths == (tenant_dir / "config.json",)
      assert inspect_bootstrap_readiness(tenant_dir).ready
      assert list(tenant_dir.glob("config.json.*.bak")) == []


  def test_recovery_keeps_backup_when_final_validation_fails(
      good_template: Path,
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      tenant_dir = _seed_corrupt_tenant(good_template.parent, "tenant-a")
      config_path = tenant_dir / "config.json"
      config_path.write_text("{broken", encoding="utf-8")
      monkeypatch.setattr(
          TenantInitializer,
          "ensure_seeded_bootstrap",
          lambda self, **kwargs: {"minimal": True},
      )

      with pytest.raises(BootstrapRecoveryFailure):
          TenantInitializer(good_template.parent, "tenant-a").recover_seeded_bootstrap()

      assert list(tenant_dir.glob("config.json.*.bak"))
  ```

- [ ] **Step 2: Run the recovery tests and verify they fail.**

  Run: `venv/bin/python -m pytest tests/unit/workspace/test_tenant_initializer.py -q`

  Expected: the new `recover_seeded_bootstrap()` tests fail because the method is absent.

- [ ] **Step 3: Implement exact recovery sequencing.**

  Replace `has_seeded_bootstrap()` with a thin `return inspect_bootstrap_readiness(self.tenant_dir).ready` compatibility wrapper. Add `recover_seeded_bootstrap()` that:

  1. calls strict readiness;
  2. backs up only the explicit `invalid_json_paths` with `move_to_recovery_backup`;
  3. leaves valid tenant-owned settings and files untouched;
  4. runs `ensure_seeded_bootstrap()` to recreate only missing/removed bootstrap artifacts;
  5. runs strict readiness again;
  6. writes `.bootstrap.ready` only after strict readiness passes;
  7. unlinks only backups created by this call after success, otherwise preserves them and raises `BootstrapRecoveryFailure`.

  Replace direct `write_text()` JSON writes in `seed_tenant_config_from_default()` and the source-agent branch of `ensure_default_workspace_scaffold()` with `write_bootstrap_json()`. Do not modify `agents/tools/file_io.py`, do not glob or TTL-delete its `.tmp` files, and do not add a general temporary-file cleaner. Keep its present immediate cleanup behavior unchanged.

- [ ] **Step 4: Run focused initializer tests.**

  Run: `venv/bin/python -m pytest tests/unit/workspace/test_tenant_initializer.py tests/unit/agents/test_file_io_cancellation.py -q`

  Expected: PASS; file I/O cancellation behavior remains unchanged.

- [ ] **Step 5: Commit the recovery behavior.**

  ```bash
  git add src/swe/app/workspace/tenant_initializer.py tests/unit/workspace/test_tenant_initializer.py
  git commit -m "fix(workspace): recover invalid tenant bootstrap artifacts"
  ```

### Task 5: Apply the shared lock and strict readiness in `TenantWorkspacePool`

**Files:**
- Modify: `src/swe/app/workspace/tenant_pool.py:77-84, 180-487`
- Modify: `tests/unit/app/test_tenant_pool.py`

- [ ] **Step 1: Write failing pool-level concurrency and recovery tests.**

  Use two pool instances against one base directory to model two pods. Assert one bootstrap execution, strict readiness before cache fast-path success, recovery invocation for an invalid config, and typed failures for timeout/source-template unavailable.

  ```python
  @pytest.mark.asyncio
  async def test_two_pool_instances_publish_one_ready_bootstrap(tmp_path: Path, monkeypatch) -> None:
      _create_ready_default_template(tmp_path)
      calls = 0
      original = TenantInitializer.ensure_seeded_bootstrap

      def counted(self, **kwargs):
          nonlocal calls
          calls += 1
          return original(self, **kwargs)

      monkeypatch.setattr(TenantInitializer, "ensure_seeded_bootstrap", counted)
      await asyncio.gather(
          TenantWorkspacePool(tmp_path).ensure_bootstrap("tenant-a"),
          TenantWorkspacePool(tmp_path).ensure_bootstrap("tenant-a"),
      )

      assert calls == 1
      assert inspect_bootstrap_readiness(tmp_path / "tenant-a").ready
  ```

- [ ] **Step 2: Run the pool tests and verify they fail.**

  Run: `venv/bin/python -m pytest tests/unit/app/test_tenant_pool.py -q`

  Expected: new two-pool and typed-unavailable assertions fail before the pool owns the file lock and source-template check.

- [ ] **Step 3: Implement the pool state machine.**

  Import the shared typed failures from `bootstrap_state.py`; do not redefine them in the pool.

  Retain the in-process `asyncio.Lock` only as a local contention optimization, but make cross-process `AsyncFlock(tenant_dir / ".bootstrap.lock")` authoritative. The fast path must call strict readiness even when the pool has a cached entry. On the slow path: validate the required source template before any tenant seeding; create the effective tenant root; acquire the file lock; recheck strict readiness; run recovery only when readiness reports invalid/missing bootstrap artifacts; revalidate; write the diagnostic `.bootstrap.ready` marker; record mapping/register only after the final ready result. Convert lock timeout, lock I/O failure, unavailable source template, recovery failure, and final-not-ready outcomes to `TenantBootstrapUnavailable` with no in-process/no-lock fallback.

  Emit exactly these structured event names with identifiers/timing only (never config contents or secrets): `tenant_bootstrap_lock_wait`, `tenant_bootstrap_lock_timeout`, `tenant_bootstrap_lock_error`, `tenant_bootstrap_not_ready`, `tenant_bootstrap_recovery_started`, `tenant_bootstrap_recovery_succeeded`, `tenant_bootstrap_recovery_failed`. Remove the now-dead `_template_created_from_default` mapping branch.

- [ ] **Step 4: Run the pool suite.**

  Run: `venv/bin/python -m pytest tests/unit/app/test_tenant_pool.py tests/unit/app/test_lazy_loading.py -q`

  Expected: PASS.

- [ ] **Step 5: Commit the pool transition.**

  ```bash
  git add src/swe/app/workspace/tenant_pool.py tests/unit/app/test_tenant_pool.py
  git commit -m "fix(workspace): serialize tenant bootstrap across pods"
  ```

### Task 6: Return retryable 503 at the HTTP workspace boundary

**Files:**
- Modify: `src/swe/app/middleware/tenant_workspace.py:90-245`
- Modify: `tests/unit/app/test_tenant_workspace.py`

- [ ] **Step 1: Write a failing middleware contract test.**

  ```python
  @pytest.mark.asyncio
  async def test_bootstrap_unavailable_returns_retryable_503(mock_request) -> None:
      pool = Mock()
      pool.ensure_bootstrap = AsyncMock(side_effect=TenantBootstrapUnavailable("locked"))
      mock_request.app.state.tenant_workspace_pool = pool

      with pytest.raises(TenantBootstrapUnavailable):
          await TenantWorkspaceMiddleware(app)._get_workspace(mock_request, "tenant-a")
  ```

  Exercise `dispatch()` with a request fixture and assert the final response is `503`, JSON detail is `Tenant bootstrap unavailable`, and header `Retry-After` equals `"2"`.

- [ ] **Step 2: Run the middleware test and verify it fails.**

  Run: `venv/bin/python -m pytest tests/unit/app/test_tenant_workspace.py -q`

  Expected: failure because the current broad catch converts all bootstrap failures to a generic missing workspace response.

- [ ] **Step 3: Preserve the typed failure through `_get_workspace` and translate it once in `dispatch`.**

  Catch `TenantBootstrapUnavailable` before the broad exception in `_get_workspace`, log the event reason without secrets, and re-raise it. In `dispatch`, catch it before the generic handler and raise:

  ```python
  raise HTTPException(
      status_code=503,
      detail="Tenant bootstrap unavailable",
      headers={"Retry-After": "2"},
  ) from exc
  ```

  Leave unrelated missing-workspace/error behavior unchanged.

- [ ] **Step 4: Run the middleware tests.**

  Run: `venv/bin/python -m pytest tests/unit/app/test_tenant_workspace.py tests/unit/app/test_lazy_loading.py -q`

  Expected: PASS.

- [ ] **Step 5: Commit the HTTP contract.**

  ```bash
  git add src/swe/app/middleware/tenant_workspace.py tests/unit/app/test_tenant_workspace.py
  git commit -m "fix(app): expose retryable tenant bootstrap failures"
  ```

### Task 7: Expose provisioning through an authenticated internal API and dedicated CLI command

**Files:**
- Modify: `src/swe/app/routers/internal.py:1-40, 519-604, 1190-1260`
- Modify: `src/swe/cli/init_cmd.py:91-130`
- Modify: `src/swe/cli/main.py:70-130`
- Create: `tests/unit/routers/test_internal_source_template.py`
- Modify: `tests/unit/cli/test_init_cmd_multi_tenant.py`

- [ ] **Step 1: Write failing API and CLI tests.**

  ```python
  def test_internal_ensure_source_template_requires_internal_token(client) -> None:
      response = client.post("/internal/source-templates/ensure", json={"source_id": "ruice"})
      assert response.status_code == 401


  def test_internal_ensure_source_template_reports_created(client, default_template) -> None:
      response = client.post(
          "/internal/source-templates/ensure",
          json={"source_id": "ruice"},
          headers={"X-Internal-Token": "Bearer test-token"},
      )
      assert response.json()["status"] == "created"
  ```

  Invoke `swe init-source-template --source-id ruice` with `CliRunner`; assert it calls the same provisioner and reports `created`/`repaired`/`ready`.

- [ ] **Step 2: Run API/CLI tests and verify they fail.**

  Run: `venv/bin/python -m pytest tests/unit/routers/test_internal_source_template.py tests/unit/cli/test_init_cmd_multi_tenant.py -q`

  Expected: route/command not found.

- [ ] **Step 3: Add the minimal authorized interfaces.**

  Add `POST /internal/source-templates/ensure`, request body `{ "source_id": "ruice" }`, and response fields `source_id`, `template_name`, and `status`; the status is `created`, `repaired`, or `ready`. Require `_verify_internal_token`; validate the source id; map `SourceTemplateUnavailable` to `503` with `Retry-After: 2`; do not expose filesystem paths, backups, or template content.

  Add a distinct Click command named `init-source-template` in `init_cmd.py` and register it in `LazyGroup.lazy_subcommands`. It accepts only `--source-id`; calls `asyncio.run(SourceTemplateProvisioner(WORKING_DIR).ensure(source_id))`; prints the result; exits nonzero on provisioner failure. Do not make `swe init --source-id` a hidden provisioning path.

- [ ] **Step 4: Run focused interface tests.**

  Run: `venv/bin/python -m pytest tests/unit/routers/test_internal_source_template.py tests/unit/cli/test_init_cmd_multi_tenant.py -q`

  Expected: PASS.

- [ ] **Step 5: Commit the provisioning interfaces.**

  ```bash
  git add src/swe/app/routers/internal.py src/swe/cli/init_cmd.py src/swe/cli/main.py tests/unit/routers/test_internal_source_template.py tests/unit/cli/test_init_cmd_multi_tenant.py
  git commit -m "feat(workspace): add explicit source template provisioning"
  ```

### Task 8: Converge every runtime bootstrap caller on the pool

**Files:**
- Modify: `src/swe/app/routers/agent.py:805-845`
- Modify: `src/swe/app/routers/config.py:649-690, 760-850`
- Modify: `src/swe/app/routers/mcp.py:293-330`
- Modify: `src/swe/app/routers/providers.py:534-660, 780-900, 1590-1750`
- Modify: `src/swe/app/routers/skills.py:420-510`
- Modify: `src/swe/app/workspace/file_broadcast.py:57-180`
- Modify: `tests/unit/routers/test_agents_tenant_scope.py`
- Modify: `tests/unit/routers/test_config_tenant_scope.py`
- Modify: `tests/unit/routers/test_mcp_tenant_scope.py`
- Modify: `tests/unit/routers/test_providers_distribution.py`
- Modify: `tests/unit/routers/test_skills_tenant_scope.py`
- Create: `tests/unit/workspace/test_file_broadcast.py`

- [ ] **Step 1: Add failing assertions that target operations await `request.app.state.tenant_workspace_pool.ensure_bootstrap`.**

  For each route/service, use an `AsyncMock` pool and assert the target tenant id plus source id are passed. Preserve each response's existing `bootstrapped` field by checking readiness before the pool call through a pure helper, not by directly initializing.

  ```python
  async def test_mcp_distribution_bootstraps_target_via_pool(request) -> None:
      request.app.state.tenant_workspace_pool.ensure_bootstrap = AsyncMock()

      await _distribute_mcp_clients_to_tenant(
          request,
          target_tenant_id="tenant-b",
          source_clients={"demo": client_config},
      )

      request.app.state.tenant_workspace_pool.ensure_bootstrap.assert_awaited_once_with(
          "tenant-b", source_id="ruice"
      )
  ```

- [ ] **Step 2: Run only the affected router tests and verify they fail.**

  Run: `venv/bin/python -m pytest tests/unit/routers/test_mcp_tenant_scope.py tests/unit/routers/test_providers_distribution.py tests/unit/routers/test_skills_tenant_scope.py -q`

  Expected: new pool-await assertions fail while direct initializer calls remain.

- [ ] **Step 3: Replace the bypasses without changing domain behavior.**

  Add a small async router helper where needed:

  ```python
  async def _ensure_target_bootstrap(
      request: Request,
      tenant_id: str,
      source_id: str | None,
  ) -> tuple[str, bool]:
      pool = getattr(request.app.state, "tenant_workspace_pool", None)
      if pool is None:
          raise HTTPException(status_code=503, detail="Tenant pool not available")
      initializer = TenantInitializer(_request_tenant_working_dir(request).parent, tenant_id, source_id=source_id)
      was_ready = initializer.has_seeded_bootstrap()
      await pool.ensure_bootstrap(tenant_id, source_id=source_id)
      return initializer.effective_tenant_id, was_ready
  ```

  Convert synchronous distribution helpers that must await this function to `async def`, then update their loops/callers to `await` them. Refactor `FileBroadcastService.broadcast()` to accept an injected pool from `routers/workspace.py` and call its async `ensure_bootstrap`; move only the post-readiness blocking copy to `asyncio.to_thread` with explicit tenant id, file names, and overwrite arguments. No route may call `TenantInitializer.ensure_seeded_bootstrap()` directly after this task.

- [ ] **Step 4: Run all changed router and file-broadcast tests.**

  Run: `venv/bin/python -m pytest tests/unit/routers/test_agents_tenant_scope.py tests/unit/routers/test_config_tenant_scope.py tests/unit/routers/test_mcp_tenant_scope.py tests/unit/routers/test_providers_distribution.py tests/unit/routers/test_skills_tenant_scope.py tests/unit/workspace/test_file_broadcast.py -q`

  Expected: PASS.

- [ ] **Step 5: Verify no runtime bypass remains, then commit.**

  Run: `rg -n 'ensure_seeded_bootstrap\(' src/swe/app src/swe/cli`

  Expected: only `tenant_pool.py`, `tenant_initializer.py`, and CLI’s explicit local bootstrap flow remain; no router or file broadcast call is present.

  ```bash
  git add src/swe/app/routers src/swe/app/workspace/file_broadcast.py tests/unit/routers
  git commit -m "refactor(app): route target bootstrap through tenant pool"
  ```

### Task 9: Update scoped documentation and perform final verification

**Files:**
- Modify: `analysis/config-and-tenant-isolation.md`
- Modify: `docs/superpowers/specs/2026-08-11-tenant-bootstrap-consistency-design.md` only if implementation evidence changes the approved decision
- Modify: `CONTEXT.md` only for terms that differ from the already-recorded definitions

- [ ] **Step 1: Document only the real operational behavior.**

  Add the effective-tenant lock path, 30-second timeout/2-second retry contract, strict readiness/recovery contract, explicit source-template provision entry points, and explicit non-goal: file I/O temporary files remain immediately cleaned but may survive ungraceful process termination. Do not document a generic TTL cleaner.

- [ ] **Step 2: Run focused and final regression tests.**

  Run:

  ```bash
  venv/bin/python -m pytest \
    tests/unit/workspace/test_bootstrap_lock.py \
    tests/unit/workspace/test_bootstrap_state.py \
    tests/unit/workspace/test_source_template_provisioner.py \
    tests/unit/workspace/test_tenant_initializer.py \
    tests/unit/app/test_tenant_pool.py \
    tests/unit/app/test_tenant_workspace.py \
    tests/unit/routers/test_internal_source_template.py \
    tests/unit/agents/test_file_io_cancellation.py -q
  ```

  Expected: PASS.

- [ ] **Step 3: Run static checks and inspect the final change surface.**

  Run:

  ```bash
  venv/bin/python -m black --check \
    src/swe/app/workspace/bootstrap_lock.py \
    src/swe/app/workspace/bootstrap_state.py \
    src/swe/app/workspace/source_template_provisioner.py \
    src/swe/app/workspace/tenant_initializer.py \
    src/swe/app/workspace/tenant_pool.py
  git diff --check
  ```

  Expected: both commands exit 0.

- [ ] **Step 4: Run GitNexus change detection before the final commit.**

  Run `detect_changes({"repo":"CoPaw","scope":"all"})`, review every affected process, and investigate any HIGH/CRITICAL result before committing. Confirm that no unrelated dirty-worktree files are staged.

- [ ] **Step 5: Commit documentation and final integration.**

  ```bash
  git add analysis/config-and-tenant-isolation.md CONTEXT.md docs/superpowers/specs/2026-08-11-tenant-bootstrap-consistency-design.md
  git commit -m "docs(workspace): document durable tenant bootstrap contract"
  ```
