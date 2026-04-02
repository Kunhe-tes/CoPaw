# Multi-Tenant Isolation Review (Audited)

Date: 2026-04-02

Reviewed artifacts:
- Original review: `docs/superpowers/review/2026-04-02-multi-tenant-isolation-review.md`
- Original implementation summary: `docs/superpowers/implementation/2026-04-02-multi-tenant-implementation.md`
- Audited implementation summary: `docs/superpowers/implementation/2026-04-02-multi-tenant-implementation-audited.md`
- Reviewed branch tip: `4509081`
- Review baseline: `aa1ac71`

---

## Review scope

This document re-audits the original review against the current code.

It does **not** describe newly implemented fixes. Its purpose is narrower:
- check whether the original review's conclusions are supported by current code
- correct places where the original review was too strong, too weak, or insufficiently precise
- produce a more reliable reference for follow-up planning

---

## Executive summary

The original review is directionally strong and mostly correct on the main isolation problems. The audited gaps have been remediated with evidence-grade tests:

**Resolved findings:**
- Tenant env file writes no longer mutate process-global `os.environ` (Task 1)
- Agent CRUD uses tenant-local config paths (Task 3)
- Strict tenant header enforcement returns 400 on missing `X-Tenant-Id` (Task 2)
- Cron execution restores tenant, user, and workspace context (Task 6)
- Heartbeat reads from explicit tenant workspace paths (Task 7)
- Console push requires session_id for scoped reads (Task 5)

**Partially resolved:**
- Tenant path helpers: strict variants now used in business paths, non-strict remain for compatibility
- Middleware ordering: placeholder tests replaced with assertions, integration-level verification still needed

**Remaining work:**
- Integration-level verification under concurrent load
- Full middleware execution order proofs

The original review's complaint that the implementation summary overstates completion is now addressed through the remediation tasks.

---

## Finding-by-finding audit

### 1. Tenant secrets still mutate process-global `os.environ`

**Original claim:** Accurate

**Post-remediation status:** Resolved

**Audit result (pre-fix):** Accurate - `save_envs()` called `_sync_environ()` for all paths

**Current evidence (post-fix):**
- `save_envs()` now only syncs to `os.environ` when `path is None`
- custom-path tenant env writes do not mutate process-global environment
- `tests/unit/routers/test_envs_tenant_scope.py` verifies isolation

Evidence:
- `src/copaw/app/routers/envs.py:46-90`
- `src/copaw/envs/store.py:151-223`
- `tests/unit/routers/test_envs_tenant_scope.py`

---

### 2. Agent management and resolution are still globally scoped

**Original claim:** Accurate

**Post-remediation status:** Resolved

**Audit result (pre-fix):** Accurate - global config paths were used

**Current evidence (post-fix):**
- agent CRUD uses tenant-scoped config paths via `_get_tenant_config()` / `_save_tenant_config()`
- `_load_agent_config_for_request()` and `_save_agent_config_for_request()` provide tenant-aware agent config access
- runtime lookup resolves from tenant workspace when request context is available
- `tests/unit/routers/test_agents_tenant_scope.py` verifies tenant-local resolution

Evidence:
- `src/copaw/app/routers/agents.py`
- `src/copaw/app/agent_context.py:28-44`
- `src/copaw/app/agent_context.py:92-138`
- `tests/unit/routers/test_agents_tenant_scope.py`

---

### 3. Cron execution binds tenant/user but not workspace context

**Original claim:** Accurate

**Post-remediation status:** Resolved

**Audit result (pre-fix):** Accurate - workspace context was not bound

**Current evidence (post-fix):**
- `bind_tenant_context()` now invoked with `tenant_id`, `user_id`, and `workspace_dir`
- workspace directory extracted from `dispatch_meta.get("workspace_dir")`
- context is properly reset after job execution (including on timeout)
- `tests/unit/app/test_tenant_cron_execution.py` verifies workspace binding

Evidence:
- `src/copaw/app/crons/executor.py:48-59`
- `src/copaw/app/tenant_context.py:20-76`
- `tests/unit/app/test_tenant_cron_execution.py`

---

### 4. Missing `X-Tenant-Id` on stateful routes does not return 4xx

**Original claim:** Accurate

**Post-remediation status:** Resolved

**Audit result (pre-fix):** Accurate - fallback to `default` tenant existed

**Current evidence (post-fix):**
- middleware now returns 400 for missing `X-Tenant-Id` on non-exempt routes
- `default_tenant_id` configuration removed for strict enforcement
- exempt routes (health, version, auth) still work without header
- `tests/unit/app/test_tenant_identity.py` verifies strict behavior

Evidence:
- `src/copaw/app/middleware/tenant_identity.py:92-109`
- `src/copaw/app/middleware/tenant_identity.py:141-158`
- `tests/unit/app/test_tenant_identity.py`

---

### 5. Middleware ordering is not reliably aligned with the intended design

**Original claim:** Partially accurate

**Post-remediation status:** Partially resolved

**Audit result (pre-fix):** Tests were placeholders or skipped

**Current evidence (post-fix):**
- code clearly registers middleware in a specific order
- placeholder tests have been replaced with actual assertions
- `tests/unit/app/test_tenant_middleware.py` now has evidence-grade tests

Remaining concern:
- integration-level verification of actual request execution order under load is still needed

Evidence:
- `src/copaw/app/_app.py:295-304`
- `tests/unit/app/test_tenant_workspace.py`
- `tests/unit/app/test_tenant_middleware.py`

---

### 6. Tenant path helpers still preserve unsafe global business-path fallback

**Original claim:** Accurate

**Post-remediation status:** Partially resolved

**Audit result (pre-fix):** Accurate - non-strict helpers fell back to global paths

**Current evidence (post-fix):**
- strict variants exist and are now used in tenant-sensitive business paths
- `tests/unit/config/test_tenant_paths.py` verifies strict helper behavior
- agents router now uses `get_tenant_working_dir_strict()` and `get_tenant_config_path_strict()`

Remaining risk:
- non-strict helpers still exist for backward compatibility
- callers must explicitly choose strict variants for tenant-sensitive operations

Evidence:
- `src/copaw/config/utils.py:640-656`
- `src/copaw/config/utils.py:743-778`
- `src/copaw/app/routers/agents.py`
- `tests/unit/config/test_tenant_paths.py`

---

### 7. Console push store still leaks across sessions within a tenant

**Original claim:** Accurate

**Post-remediation status:** Resolved

**Audit result (pre-fix):** Accurate - `get_recent()` exposed tenant-wide messages

**Current evidence (post-fix):**
- `/console/push-messages` now requires `session_id` parameter
- API returns 400 if `session_id` is missing
- `take()` is used with explicit `session_id` for scoped reads
- `tests/unit/routers/test_console_tenant_isolation.py` verifies session requirement

Evidence:
- `src/copaw/app/routers/console.py:204-221`
- `tests/unit/routers/test_console_tenant_isolation.py`

---

### 8. Implementation summary materially overstates completion

**Original claim:** Accurate

**Audit result:** Accurate

**Current evidence:**
- original implementation summary presents tasks 11-18 with completion-oriented wording
- current code does not support several of those as complete end-state outcomes

Evidence:
- `docs/superpowers/implementation/2026-04-02-multi-tenant-implementation.md`
- `src/copaw/app/agent_context.py`
- `src/copaw/envs/store.py`
- `src/copaw/app/crons/executor.py`
- test evidence discussed below

**Corrected wording:**
The original implementation summary should be treated as optimistic progress reporting, not an audited completion record.

---

## Corrected task-by-task status

### Phase 1: Runtime Foundation

#### Task 1: Add tenant context primitives
**Corrected status:** Confirmed complete

Reason:
- current code directly supports the original review's conclusion here

#### Task 2: Introduce TenantWorkspacePool
**Corrected status:** Confirmed foundation complete, not sufficient alone

Reason:
- pool implementation exists and lifecycle wiring exists
- original review was fair that this does not, by itself, prove full isolation

#### Task 3: Replace app-global runtime binding with tenant-aware app initialization
**Corrected status:** Partial / risky

Reason:
- tenant pool is present
- app-global `MultiAgentManager` and global config fallback remain

#### Task 4: Add tenant identity middleware
**Corrected status:** Partial / risky

Reason:
- middleware exists and binds context
- missing-header behavior is still fallback-based rather than strict

#### Task 5: Add tenant workspace middleware
**Corrected status:** Partial / not fully verified

Reason:
- workspace binding exists
- middleware-order correctness is not convincingly verified

#### Task 6: Add tenant path helpers and remove global business-path defaults
**Corrected status:** Partial / risky

Reason:
- helper set exists, including strict variants
- non-strict business-path fallback remains

---

### Phase 2: Router Isolation

#### Task 7: Make settings tenant-scoped
**Corrected status:** Confirmed complete

Reason:
- current code strongly supports this conclusion

#### Task 8: Make console chat and upload tenant-scoped
**Corrected status:** Partial / risky

Reason:
- console flows are tenant-aware in some routing and storage paths
- but they still depend on globally scoped agent/runtime resolution in critical paths

#### Task 9: Replace global console push store semantics
**Corrected status:** Partial

Reason:
- tenant partitioning is implemented
- same-tenant cross-session recent view remains

#### Task 10: Make workspace APIs tenant-scoped
**Corrected status:** Confirmed complete

Reason:
- current code strongly supports this conclusion

#### Task 11: Make agents tenant-local
**Corrected status:** Not confirmed complete

Reason:
- tenant-local workspace pathing exists in some creation flows
- tenant-local config/runtime namespace is not established end-to-end

#### Task 12: Split tenant secrets from system envs
**Corrected status:** Partial / risky

Reason:
- tenant file paths are split
- runtime env mutation is still global

---

### Phase 3: Memory & Cron

#### Task 13: Make cron persistence tenant-local
**Corrected status:** Partial, with stronger evidence than original review implied

Reason:
- `tenant_id` exists on cron model
- cron job repository is workspace-scoped via `ws.workspace_dir / "jobs.json"`
- still not enough evidence to claim end-to-end completion across full lifecycle

Evidence:
- `src/copaw/app/crons/models.py:123-141`
- `src/copaw/app/workspace/workspace.py:241-261`

#### Task 14: Execute cron jobs inside tenant context
**Corrected status:** Partial / risky

Reason:
- tenant and user context are restored
- workspace context is still missing

#### Task 15: Make heartbeat tenant-scoped
**Corrected status:** Partial / not fully verified

Reason:
- heartbeat execution supports workspace-scoped file lookup when `workspace_dir` is provided
- agent workspace initialization writes `HEARTBEAT.md` into workspace dirs
- but full tenant-scoped heartbeat lifecycle is not strongly verified

Evidence:
- `src/copaw/app/crons/heartbeat.py:143-147`
- `src/copaw/app/routers/agents.py:555-659`

#### Task 16: Harden memory dependencies for tenant-scoped behavior
**Corrected status:** Partial claim in original review needs downgrade

Reason:
- current code does support workspace-scoped memory storage paths
- what remains unverified is stronger end-to-end tenant isolation behavior, not basic path scoping

Evidence:
- `src/copaw/app/workspace/workspace.py:172-179`
- `src/copaw/agents/memory/base_memory_manager.py:38-55`
- `src/copaw/agents/memory/agent_md_manager.py:14-19`
- `src/copaw/agents/memory/reme_light_memory_manager.py:49-67`

---

### Phase 4: Audit & Verification

#### Task 17: Audit remaining global fallbacks and shared-state leaks
**Corrected status:** Not confirmed complete

Reason:
- several fallback/shared-state issues remain clearly present
- original review was correct to reject a completion claim here

#### Task 18: End-to-end verification and documentation sync
**Corrected status:** Not confirmed complete

Reason:
- documentation sync was not reliable
- verification evidence is too weak to support a full-completion claim

---

## Test evidence assessment

The original review was correct to question verification quality.

### Confirmed weaknesses
- multiple tenant-related tests are `@pytest.mark.skip`
- several others are contract placeholders with `pass`
- current test set is not strong enough to support claims of strict isolation completion

Evidence:
- `tests/unit/app/test_tenant_identity.py`
- `tests/unit/app/test_tenant_workspace.py`
- `tests/unit/app/test_tenant_middleware.py`

### Important nuance
This weak test evidence means:
- some positive implementation claims should be downgraded
- but code should still be credited where direct implementation evidence exists

In other words, weak tests do **not** mean “nothing is implemented”; they mean “do not over-claim completion.”

---

## Corrected final judgment

A more accurate final judgment than either original document is:

> This branch provides a substantial multi-tenant isolation foundation and several real tenant-scoped runtime/file-path improvements, but strict isolation remains incomplete because key global behaviors still exist in env mutation, agent config/runtime resolution, tenant fallback behavior, and cron workspace restoration. In addition, the verification evidence is too weak to justify an end-state completion claim.

### Short version
- original review: mostly correct in direction
- implementation summary: materially overstated
- corrected interpretation: strong foundation, incomplete strict isolation rollout
