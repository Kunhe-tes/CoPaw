# Tenant Bootstrap Consistency Design

**Status:** Approved

## Goal

Ensure that an effective tenant storage scope is either fully bootstrap-ready or unavailable and retriable. Concurrent Pods must never expose a partially initialized root configuration or default workspace.

## Scope

This design changes tenant bootstrap, recovery, and Source Template provisioning. It covers root `config.json`, `workspaces/default/agent.json`, required workspace assets, provider seeding, and skill manifests.

It does not add a general `.tmp` reaper. `file_io` retains its existing immediate cleanup behavior and abrupt-process leftovers remain an accepted manual-recovery concern.

## Terms

The canonical terms are maintained in `CONTEXT.md`: Tenant Bootstrap, Tenant Bootstrap Recovery, Tenant Bootstrap Lock, Tenant Bootstrap Readiness, Tenant Staging Artifact, Source Template, and Source Template Provisioning.

## Decisions

### Effective-scope bootstrap lock

Every bootstrap and recovery takes an exclusive `fcntl.flock` lock at:

```text
<effective-tenant-root>/.bootstrap.lock
```

The lock key is the effective storage tenant ID, not the logical tenant ID. The shared RWX volume has been operationally verified to provide mutually exclusive cross-Pod `flock` behavior.

Acquisition uses non-blocking attempts off the event loop, waits at most 30 seconds, and logs wait duration. A timeout or any lock I/O failure returns `503` with `Retry-After: 2`; bootstrap must not fall back to process-local locking or uncoordinated writes.

The lock covers the complete state transition:

```text
strict readiness check -> repair or initialize -> strict readiness check
-> write diagnostic ready marker -> release lock
```

### Readiness is derived from real artifacts

`.bootstrap.ready` is an atomic diagnostic/version marker only. It never makes a tenant ready by itself. The readiness validator must strictly parse and validate all of the following without invoking the tolerant `load_config()` fallback path:

- `<tenant>/config.json` is a JSON object and has a valid enabled `default` profile.
- The default profile's `workspace_dir` resolves to `<tenant>/workspaces/default`.
- `<tenant>/workspaces/default/agent.json` is valid and declares the `default` agent and the same workspace path.
- Required workspace directories and prompt files exist.
- Required skill-pool and workspace-skill manifests are parseable and satisfy the existing bootstrap contract.

Any failed predicate produces a machine-readable reason code for logs and causes recovery inside the lock.

### Atomic bootstrap writes and recovery

Bootstrap-owned JSON writes use one reusable atomic-write helper:

```text
create unique staging file in target directory
-> write JSON -> flush -> fsync(file)
-> os.replace(staging, target) -> fsync(parent directory)
```

The helper replaces direct `write_text()` and `open(..., "w")` persistence for bootstrap-owned `config.json`, `agent.json`, manifests, and the ready marker.

For an invalid existing bootstrap-owned JSON file, recovery creates a uniquely named recovery `.bak` before replacing the file. Recovery only creates missing state or replaces state that failed strict readiness; it never overwrites a ready user configuration.

On successful final readiness validation, recovery removes its `.bak` files immediately. On failure it retains them, emits a recovery-failed log, and returns 503. No workspace runtime starts from a failed recovery.

### Source Templates are pre-provisioned assets

`default_<source_id>` is a Source Template, not a lazy side effect of a tenant request. Remove runtime creation of `default_<source_id>` from `TenantInitializer._resolve_template_name()`.

Source Template Provisioning is available only through an authenticated internal/admin endpoint and a CLI command. It is an idempotent safe `ensure` operation:

- A missing template is created from a strictly ready global `default` template.
- An incomplete template is repaired under a per-source template file lock.
- A ready template is returned unchanged; no `force` overwrite exists.
- A missing or invalid global `default` template fails closed and leaves no partial Source Template.

Tenant requests only read a strictly ready Source Template. When it is missing or invalid, they return `503 source template unavailable` instead of copying from `default/` or using an empty fallback.

The internal endpoint follows the existing `/api/internal` authentication boundary and is paired with a CLI entry point for deployment provisioning. Provisioning logs source ID and outcome, but no configuration content or secrets.

### Initialization-entry-point convergence

All routes that can initialize a target tenant must call the lock-owning `TenantWorkspacePool` API. Routers and broadcast helpers must not call `TenantInitializer.ensure_seeded_bootstrap()` directly, because doing so bypasses cross-Pod coordination.

### Temporary files

`file_io` continues to remove its own `.<target>.<random>.tmp` files on normal completion, ordinary exception, and task cancellation. Abrupt process termination can still leave them behind; the system deliberately does not introduce a TTL scanner or delete arbitrary user `.tmp` files.

Bootstrap recovery only manages staging and `.bak` files it created itself. Successful recovery deletes its backups immediately; failed recovery retains them.

### Observability

The implementation emits structured logs, without configuration payloads, for:

- `tenant_bootstrap_lock_wait`, `tenant_bootstrap_lock_timeout`, and `tenant_bootstrap_lock_error`;
- `tenant_bootstrap_not_ready` with readiness reason codes;
- `tenant_bootstrap_recovery_started`, `tenant_bootstrap_recovery_succeeded`, and `tenant_bootstrap_recovery_failed`;
- `source_template_provisioning_started`, `source_template_provisioning_ready`, `source_template_provisioning_repaired`, and `source_template_provisioning_failed`.

Every record includes the effective storage scope or source ID, elapsed time, and safe artifact-category identifiers.

## Main flows

### Tenant request

```text
request -> resolve effective storage tenant
        -> acquire tenant bootstrap lock
        -> strict readiness check
        -> ready: release and continue
        -> not ready: validate Source Template, recover, validate again
        -> success: write ready marker, delete recovery backups, release
        -> failure: retain backups, release, return retryable 503
```

### Source Template provisioning

```text
internal/admin or CLI ensure(source_id)
  -> acquire source-template lock
  -> strict Source Template readiness check
  -> ready: return unchanged
  -> validate global default template
  -> invalid global default: fail closed
  -> create or repair template atomically
  -> strict validation -> return success
```

## Test strategy

- Use two independent Python processes on a shared temporary filesystem to prove only one bootstrap mutates a single effective tenant scope.
- Prove a lock holder beyond 30 seconds produces retryable 503 for a second caller.
- Verify partial or invalid `config.json` and `agent.json` recover to strict readiness.
- Verify recovery deletes its `.bak` files immediately after success and retains them after final validation failure.
- Verify a ready marker paired with damaged real artifacts triggers recovery.
- Verify tenant requests never create Source Templates.
- Verify Source Template provisioning creates a missing template, is idempotent for a ready template, repairs an incomplete template, and fails closed when global `default` is invalid.
- Verify logical tenant/source combinations lock independently only when their effective storage scopes differ.
- Verify direct bootstrap call sites are removed or routed through the pool.

## Rollout

1. Inventory all active source IDs and use the internal/CLI ensure operation to provision and validate their Source Templates.
2. Deploy the strict readiness and lock implementation after the pre-provisioning check is clean.
3. Alert on bootstrap lock timeout/error, recovery failure, and source-template provisioning failure logs.
4. Keep the new readiness validator backward compatible with existing valid tenant layouts; missing diagnostic markers must not by themselves trigger destructive repair.

## Non-goals

- Replacing shared filesystem locking with Redis or database locking.
- Automatically removing `file_io` artifacts left by SIGKILL/OOM/restart.
- Force-resetting ready Source Templates or tenant configurations.
- Treating a filesystem existence check as bootstrap correctness.
