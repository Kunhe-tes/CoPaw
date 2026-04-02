# Multi-Tenant Isolation Review

Date: 2026-04-02

Reviewed artifacts:
- Plan: `docs/superpowers/plans/2026-04-01-multi-tenant-isolation.md`
- Implementation summary: `docs/superpowers/implementation/2026-04-02-multi-tenant-implementation.md`
- Reviewed branch tip: `4509081`
- Review baseline: `aa1ac71`

---

## Overall assessment

This branch makes solid progress on tenant context primitives, tenant workspace pooling, tenant-scoped settings, and tenant-scoped workspace file APIs. However, it does **not** yet satisfy the plan's strict multi-tenant isolation bar.

The main issue is not lack of effort, but that several critical isolation boundaries remain global or still contain unsafe fallback behavior. In addition, the implementation summary overstates completion for later plan tasks.

### High-level conclusion

- **Strongly complete:** Tasks 1, 7, 10
- **Partially complete / risky:** Tasks 2, 3, 4, 5, 6, 8, 9, 12, 13, 14
- **Missing or materially overstated:** Tasks 11, 15, 16, 17, 18

---

## Priority findings

### Blockers

#### 1. Tenant secrets still mutate process-global `os.environ`

**Files:**
- `src/copaw/app/routers/envs.py:72`
- `src/copaw/envs/store.py:182`
- `src/copaw/envs/store.py:200`

**Evidence:**
- The env API writes tenant data to a tenant-specific file path.
- `save_envs()` still calls `_sync_environ(old, envs)`.
- `delete_env_var()` calls `save_envs()`, so deletes also synchronize into global process environment.

**Why this matters:**
Tenant-scoped secrets are still affecting the global process environment, so tenant A can influence runtime-visible environment seen by tenant B.

**Required outcome:**
Tenant env CRUD must use tenant file storage as the source of truth and must not update global `os.environ`.

---

#### 2. Agent management and resolution are still globally scoped

**Files:**
- `src/copaw/app/agent_context.py:40-44`
- `src/copaw/app/agent_context.py:129-138`
- `src/copaw/app/_app.py:201-219`
- `src/copaw/app/routers/agents.py`

**Evidence:**
- `_get_tenant_aware_config()` explicitly says it falls back to global config.
- Runtime lookup still uses app-global `MultiAgentManager`.
- Tenant-local agent directory creation does not make agent metadata/config/runtime tenant-local by itself.

**Why this matters:**
Task 11 requires agents to be tenant-local. Today, tenant-local workspace paths exist in some flows, but agent config and runtime namespace remain global.

**Required outcome:**
Agent CRUD, active-agent selection, config resolution, and runtime lookup must all be tenant-local.

---

#### 3. Cron execution binds tenant/user but not workspace context

**Files:**
- `src/copaw/app/crons/executor.py:48-53`

**Evidence:**
- `bind_tenant_context(...)` is called with `tenant_id` and `user_id` only.
- No workspace directory is bound for cron execution.

**Why this matters:**
The plan explicitly requires non-HTTP paths to restore tenant/workspace context so file and path resolution remain tenant-bound. Without workspace context, cron code can still hit global fallbacks.

**Required outcome:**
Cron execution must bind tenant, user, and workspace context together.

---

#### 4. Missing `X-Tenant-Id` on stateful routes does not return 4xx

**Files:**
- `src/copaw/app/middleware/tenant_identity.py:95-97`
- `src/copaw/app/middleware/tenant_identity.py:143-158`

**Evidence:**
- Middleware is configured with `require_tenant=True` but `default_tenant_id="default"`.
- Missing header falls back to `default` instead of rejecting the request.

**Why this matters:**
This contradicts the plan and the verification checklist, which both require missing tenant identity on stateful routes to fail with 4xx.

**Required outcome:**
Non-exempt routes must reject requests that do not provide `X-Tenant-Id`.

---

#### 5. Middleware ordering is not reliably aligned with the intended design

**Files:**
- `src/copaw/app/_app.py`
- `docs/superpowers/implementation/2026-04-02-multi-tenant-implementation.md:101-108`

**Evidence:**
- The implementation summary documents a specific middleware order.
- The code does not provide sufficient proof that FastAPI/Starlette actual execution order matches the intended order.
- Review identified this as a correctness risk.

**Why this matters:**
Tenant identity must exist before tenant workspace resolution, and tenant workspace must exist before downstream agent resolution. If the order is wrong, request context may be inconsistent or silently wrong.

**Required outcome:**
The middleware registration order must be verified and corrected, with tests proving the intended request flow.

---

### Important issues

#### 6. Tenant path helpers still preserve unsafe global business-path fallback

**Files:**
- `src/copaw/config/utils.py`

**Why this matters:**
The plan explicitly aimed to remove global business-path defaults. If tenant-specific helpers still fall back to `WORKING_DIR`, accidental cross-tenant or global writes remain possible.

**Required outcome:**
Tenant-scoped business helpers should raise on missing tenant/workspace context instead of silently falling back.

---

#### 7. Console push store still leaks across sessions within a tenant

**Files:**
- `src/copaw/app/console_push_store.py:157-176`
- `src/copaw/app/routers/console.py`

**Evidence:**
- Message storage is partitioned by tenant.
- `get_recent()` still returns recent messages across all sessions for that tenant.

**Why this matters:**
The plan called for removing or sharply constraining the “recent messages across all sessions” behavior. Current behavior still allows intra-tenant cross-session leakage.

**Required outcome:**
The normal API path should require tenant + session scope, or the cross-session recent view should be limited to internal diagnostics only.

---

#### 8. Implementation summary materially overstates completion

**Files:**
- `docs/superpowers/implementation/2026-04-02-multi-tenant-implementation.md`

**Why this matters:**
The summary currently reads like end-state completion, but several later tasks remain partial or missing. This makes the document unreliable for handoff or status tracking.

**Required outcome:**
Update the summary to distinguish complete / partial / missing work and remove unsupported completion claims.

---

## Task-by-task review

### Phase 1: Runtime Foundation

#### Task 1: Add tenant context primitives
**Status:** Complete

Implemented:
- tenant/user contextvars
- strict getters
- tenant binding helper / context manager

Assessment:
- This task appears complete and aligned with the plan.

---

#### Task 2: Introduce TenantWorkspacePool
**Status:** Partial

Implemented:
- tenant workspace cache
- per-tenant locking
- `stop_all`

Remaining concern:
- This is only a foundation. The wider runtime still has global assumptions, so the pool alone does not establish real tenant isolation.

---

#### Task 3: Replace app-global runtime binding with tenant-aware app initialization
**Status:** Partial / Risky

Implemented:
- `app.state.tenant_workspace_pool`
- startup/shutdown pool lifecycle

Remaining concerns:
- app-global `MultiAgentManager`
- global config fallback in `agent_context.py`
- runtime is not fully tenant-first

---

#### Task 4: Add tenant identity middleware
**Status:** Partial / Risky

Implemented:
- middleware exists
- tenant/user extraction
- basic tenant validation
- route exemptions

Remaining concerns:
- missing tenant header does not fail strictly
- current fallback to `default` weakens isolation guarantees

---

#### Task 5: Add tenant workspace middleware
**Status:** Partial / Risky

Implemented:
- tenant workspace is loaded
- `request.state.workspace` is set
- workspace context is bound for request handling

Remaining concerns:
- middleware ordering is not convincingly validated

---

#### Task 6: Add tenant path helpers and remove global business-path defaults
**Status:** Partial / Risky

Implemented:
- tenant path helpers exist

Remaining concerns:
- global business-path fallback still remains in tenant-sensitive flows

---

### Phase 2: Router Isolation

#### Task 7: Make settings tenant-scoped
**Status:** Complete

Implemented:
- tenant-specific settings storage
- settings path resolution no longer hard-coded globally

Assessment:
- This task looks complete and is one of the stronger parts of the branch.

---

#### Task 8: Make console chat and upload tenant-scoped
**Status:** Partial / Risky

Implemented:
- some console flows now carry tenant awareness
- upload targets have moved toward tenant workspace usage

Remaining concerns:
- console runtime still relies on globally-scoped agent resolution in important paths
- no convincing cross-tenant reconnect/stop/upload protection tests were found

---

#### Task 9: Replace global console push store semantics
**Status:** Partial

Implemented:
- tenant-level store partitioning

Remaining concerns:
- same-tenant cross-session leakage still exists via recent message retrieval

---

#### Task 10: Make workspace APIs tenant-scoped
**Status:** Complete

Implemented:
- workspace download/upload use tenant workspace from request state

Assessment:
- This task appears complete.

---

#### Task 11: Make agents tenant-local
**Status:** Missing / Risky

Implemented:
- agent workspace creation under tenant directories in some flows

Missing:
- tenant-local agent config resolution
- tenant-local active-agent selection
- tenant-local runtime namespace

Assessment:
- This task should not be considered complete.

---

#### Task 12: Split tenant secrets from system envs
**Status:** Partial / Risky

Implemented:
- tenant-scoped env file path
- router passes tenant path into env store functions

Remaining concerns:
- process-global env mutation still occurs

Assessment:
- This task is not complete because the core isolation boundary is still broken.

---

### Phase 3: Memory & Cron

#### Task 13: Make cron persistence tenant-local
**Status:** Partial

Implemented:
- `tenant_id` added to cron job model

Remaining concerns:
- no convincing evidence of full tenant-local cron repo/manager lifecycle wiring
- missing repo round-trip verification

---

#### Task 14: Execute cron jobs inside tenant context
**Status:** Partial / Risky

Implemented:
- cron execution wrapped in tenant context helper

Remaining concerns:
- workspace context is not restored

---

#### Task 15: Make heartbeat tenant-scoped
**Status:** Missing

Assessment:
- The current changes do not provide sufficient evidence that heartbeat isolation was implemented.

---

#### Task 16: Harden memory dependencies for tenant-scoped behavior
**Status:** Missing

Assessment:
- The implementation summary claims completion, but corresponding memory manager hardening changes are not present in the reviewed code.

---

### Phase 4: Audit & Verification

#### Task 17: Audit remaining global fallbacks and shared-state leaks
**Status:** Missing / Incorrectly claimed

Assessment:
- Multiple global fallbacks and shared-state leaks still remain, so this audit cannot be considered complete.

---

#### Task 18: End-to-end verification and documentation sync
**Status:** Missing / Incorrectly claimed

Assessment:
- There is not enough evidence for full verification of request isolation, runtime isolation, memory isolation, heartbeat isolation, or single-tenant regression.
- The implementation summary currently claims more completion than the code supports.

---

## Test and verification gaps

The review found significant evidence gaps in test coverage.

### Missing or weakly supported areas
- cross-tenant agent CRUD/list/update isolation
- cross-tenant env isolation
- console reconnect/stop/upload isolation
- cron persistence and execution isolation
- heartbeat isolation
- memory isolation
- middleware execution ordering
- strict 4xx behavior for missing tenant headers on stateful routes

### Specific concern
Several newly added tests appear to be placeholders, scaffolding, or skipped cases rather than strong verification of isolation claims. This makes the “all tasks complete” and “verification completed” statements unreliable.

---

## Recommended remediation order

1. Stop syncing tenant env writes into global `os.environ`
2. Make agent config and runtime resolution genuinely tenant-local
3. Bind workspace context during cron execution
4. Enforce strict 4xx for missing `X-Tenant-Id` on stateful routes
5. Verify and correct middleware ordering
6. Remove remaining global fallback behavior for tenant business paths
7. Restrict console push reads to tenant + session scope
8. Implement heartbeat tenant isolation
9. Harden memory-related tenant boundaries
10. Re-run verification and rewrite implementation summary to reflect actual status

---

## Final judgment

This branch is a **strong foundation**, not a completed strict tenant isolation rollout.

It should be described as:
- foundational runtime isolation added
- several router surfaces tenant-scoped
- strict isolation still incomplete due to remaining global state and fallback behavior

Until the blocker items are addressed, this work should **not** be considered complete against the approved plan.
