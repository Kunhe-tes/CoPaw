## Context

`SourceSystemConfigMiddleware` currently resolves and binds effective Source System Configuration only on HTTP requests, after `TenantIdentityMiddleware` has already resolved `tenant_id`, `source_id`, and `scope_id`. Downstream request code can then read the bound config from `request.state.source_system_config` or the runtime ContextVar helper.

Scheduled work does not pass through that middleware path. `CronManager` currently reconstructs tenant runtime context for three background execution paths:

- scheduled job execution through `CronExecutor`
- heartbeat execution through `run_heartbeat()`
- dream execution through `run_dream()`

Those paths already bind tenant/workload runtime context, but they do not bind Source System Configuration. The result is an execution gap: source-scoped controls work for HTTP requests, yet the same source may be ignored by background scheduled work.

The updated domain language in `CONTEXT.md` resolves this boundary as **Scheduled Run Boundary**. That term covers scheduled background work only, and explicitly excludes `/cron` management API requests.

## Goals / Non-Goals

**Goals:**

- Resolve the latest effective Source System Configuration at each Scheduled Run Boundary.
- Make `CronManager` the shared owner of that boundary for jobs, heartbeat, and dream execution.
- Pass `SourceSystemConfigService` through explicit dependency injection into cron runtime code.
- Prefer explicit scheduled-run `source_id`; fall back to decoding runtime `scope_id` when needed.
- Preserve legacy behavior when a scheduled run has no source or when the runtime has no source config service.
- Treat unavailable or invalid sourced configuration as a scheduled-run failure instead of silently bypassing controls.
- Cover the whole scheduled-run business execution segment, not only the model invocation path.

**Non-Goals:**

- Do not change `/cron` management API request handling; those remain normal HTTP requests and keep middleware-based binding.
- Do not snapshot Source System Configuration into cron job definitions at create/update time.
- Do not invent a default source for legacy source-less scheduled work.
- Do not move scheduled-run boundary ownership into `CronExecutor`, runner internals, or global helpers.
- Do not change Source System Configuration storage, schema, or request-time resolution semantics outside scheduled work.

## Decisions

### 1. `CronManager` owns the Scheduled Run Boundary

The boundary must cover ordinary jobs, heartbeat, and dream execution with one policy. `CronExecutor` only covers normal job execution, so it is too narrow. `CronManager` is already the common runtime boundary that binds tenant context and workload context before scheduled work starts, so it is the right owner for source config binding too.

This also keeps `/cron` management APIs out of scope. API handlers trigger or manage scheduled work, but they are not themselves Scheduled Run Boundaries.

### 2. Resolve Source System Configuration at execution time

Scheduled work must not store a snapshot of Source System Configuration inside the cron definition. Each run resolves the latest effective config when the boundary starts so that changes from the system config page apply on the next run of existing scheduled work.

Source resolution order is:

1. explicit scheduled-run `source_id`
2. decoded `source_id` from runtime `scope_id`
3. no source available: treat the run as legacy source-less work

This matches the ADR and keeps scheduled work aligned with source-scoped runtime identity without forcing a new persistence migration.

### 3. Inject `SourceSystemConfigService` explicitly into scheduled runtime construction

Current cron runtime construction does not receive the source config service. The service is created during app startup and stored on `app.state`, while `CronManager` is created inside `Workspace` service registration.

The change should add explicit dependency plumbing from app/runtime construction into workspace creation and then into `CronManager`, for example:

```text
app startup
  └─ SourceSystemConfigService
      └─ MultiAgentManager / workspace runtime deps
          └─ Workspace
              └─ CronManager(source_system_config_service=...)
```

This keeps scheduled work independent from FastAPI request state and avoids hidden globals.

### 4. Legacy source-less and service-less runs remain unbound

Some scheduled work may still run without explicit source identity, or in runtimes where the source config service is not available. Those cases should keep current behavior:

- no source: continue execution without source config binding and log a warning
- no service: continue execution without source config binding

This keeps rollout compatibility and avoids turning missing historical source data into a hard outage.

### 5. Sourced scheduled work fails on invalid or unavailable config

When both a source and the service exist, the runtime must follow `SourceSystemConfigService.resolve_config()` semantics. Stale cached/default results may still be returned by the service, which is acceptable. But if `resolve_config()` raises unavailable or invalid-configuration errors for that source, scheduled work must fail rather than silently bypassing source-scoped controls.

The important line is: once the runtime has enough information to apply source policy, it must either apply that policy or fail loudly.

### 6. Bind source config around the whole business execution segment

Binding only around `runner.stream_query()` would leave other scheduled side effects outside the source-scoped policy window. The binding must therefore wrap the full business execution segment for each Scheduled Run Boundary:

- job execution including pre/post execution logic that belongs to the run
- heartbeat execution
- dream execution

That keeps future scheduled-run side effects consistent with the same source config context.

## Boundary Sketch

```text
Scheduled Run Boundary
  ├─ resolve scheduled source
  │   ├─ explicit source_id
  │   └─ else decode scope_id
  ├─ resolve effective source config (if service + source exist)
  ├─ bind source config context
  └─ run scheduled business work
      ├─ job execution
      ├─ heartbeat
      └─ dream
```

`/cron` management API requests stay on the normal HTTP request path:

```text
HTTP request
  └─ TenantIdentityMiddleware
      └─ SourceSystemConfigMiddleware
          └─ /cron management API handler
```

## Risks / Trade-offs

- Wiring the new dependency into workspace creation touches `MultiAgentManager`, `Workspace`, and cron-related tests.
- Binding the full boundary can surface Source System Configuration failures in heartbeat and dream execution, not only in agent jobs.
- Legacy source-less scheduled work will continue without source-scoped controls until that work is recreated or otherwise gains source identity.

## Migration Plan

No data migration is required.

- Existing sourced scheduled work will start using execution-time Source System Configuration on its next run after rollout.
- Existing source-less scheduled work will continue with unbound behavior until it is recreated with source identity or started from a scope-aware runtime.

## Open Questions

None.
