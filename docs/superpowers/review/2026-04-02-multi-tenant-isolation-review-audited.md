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

The original review is directionally strong and mostly correct on the main isolation problems. In particular, its blocker findings about env global mutation, app-global agent/runtime behavior, missing strict tenant-header enforcement, and missing workspace restoration in cron execution are supported by the current code.

However, several parts of the original review should be corrected:
- some conclusions should be downgraded from “missing” to “partial / not fully verified”
- memory isolation was judged too harshly; current code does support workspace-scoped memory storage paths
- heartbeat isolation was also judged too harshly; the codebase contains workspace-scoped heartbeat support, though not enough to claim full completion
- middleware-order concerns are valid, but the stronger claim is that execution order is **not well verified**, not that the code necessarily registers middleware incorrectly

The original review's complaint that the implementation summary overstates completion is still valid.

---

## Finding-by-finding audit

### 1. Tenant secrets still mutate process-global `os.environ`

**Original claim:** Accurate

**Audit result:** Accurate

**Current evidence:**
- env router writes tenant-specific file paths
- `save_envs()` still calls `_sync_environ(old, envs)`
- `delete_env_var()` and `set_env_var()` both flow through `save_envs()`

Evidence:
- `src/copaw/app/routers/envs.py:46-90`
- `src/copaw/envs/store.py:182-223`

**Corrected wording:**
Tenant env file paths are tenant-scoped, but tenant env CRUD still mutates process-global `os.environ`, so runtime env isolation is not yet achieved.

---

### 2. Agent management and resolution are still globally scoped

**Original claim:** Accurate

**Audit result:** Accurate

**Current evidence:**
- `_get_tenant_aware_config()` still explicitly returns global config
- active-agent lookup still depends on that global path
- runtime workspace lookup still uses app-global `MultiAgentManager`
- tenant-local workspace creation alone does not make config/runtime namespaces tenant-local

Evidence:
- `src/copaw/app/agent_context.py:28-44`
- `src/copaw/app/agent_context.py:92-138`
- `src/copaw/app/_app.py:201-219`

**Corrected wording:**
Agent workspace directories can be tenant-specific in some flows, but agent config resolution and runtime namespace remain globally scoped in critical paths.

---

### 3. Cron execution binds tenant/user but not workspace context

**Original claim:** Accurate

**Audit result:** Accurate

**Current evidence:**
- `bind_tenant_context(...)` is invoked with `tenant_id` and `user_id`
- no workspace directory is passed into that binding

Evidence:
- `src/copaw/app/crons/executor.py:48-53`

**Corrected wording:**
Cron execution restores tenant and user context, but not workspace context, so some workspace-dependent resolution may still fall back outside tenant-scoped paths.

---

### 4. Missing `X-Tenant-Id` on stateful routes does not return 4xx

**Original claim:** Accurate

**Audit result:** Accurate

**Current evidence:**
- middleware is instantiated with `require_tenant=True`
- default configuration still sets `default_tenant_id="default"`
- missing tenant header therefore falls back to `default` instead of rejecting

Evidence:
- `src/copaw/app/middleware/tenant_identity.py:92-109`
- `src/copaw/app/middleware/tenant_identity.py:141-158`

**Corrected wording:**
Current middleware behavior is backward-compatible default-tenant fallback, not strict tenant-header enforcement.

---

### 5. Middleware ordering is not reliably aligned with the intended design

**Original claim:** Partially accurate

**Audit result:** Needs wording correction

**Current evidence:**
- code clearly registers middleware in a specific order
- but current tests do not convincingly verify actual runtime execution order
- several related tests are placeholders or skipped

Evidence:
- `src/copaw/app/_app.py:295-304`
- `tests/unit/app/test_tenant_workspace.py:16-42`
- `tests/unit/app/test_tenant_middleware.py:98-123`

**Corrected wording:**
The intended middleware order is visible in registration code, but the branch does not provide strong verification that actual request execution order is correct and regression-safe.

---

### 6. Tenant path helpers still preserve unsafe global business-path fallback

**Original claim:** Accurate

**Audit result:** Accurate

**Current evidence:**
- `get_tenant_working_dir()` falls back to global `WORKING_DIR` when tenant context is absent
- strict variants exist, but non-strict helpers still permit global fallback

Evidence:
- `src/copaw/config/utils.py:640-656`
- `src/copaw/config/utils.py:743-778`

**Corrected wording:**
The codebase contains strict tenant path helpers, but many non-strict tenant helpers still silently fall back to global paths when context is missing.

---

### 7. Console push store still leaks across sessions within a tenant

**Original claim:** Accurate

**Audit result:** Accurate

**Current evidence:**
- store is partitioned by tenant
- `get_recent()` returns all recent messages for that tenant
- `/console/push-messages` without `session_id` exposes that tenant-wide recent view

Evidence:
- `src/copaw/app/console_push_store.py:157-176`
- `src/copaw/app/routers/console.py:204-222`

**Corrected wording:**
Cross-tenant separation exists, but same-tenant cross-session recent-message visibility remains in the normal API path.

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
