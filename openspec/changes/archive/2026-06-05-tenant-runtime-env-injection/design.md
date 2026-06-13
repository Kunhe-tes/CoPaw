## Context

The project already persists environment variables through `/api/envs` and the
env store. For tenant-scoped requests, `TenantIdentityMiddleware` resolves
`scope_id` from `X-Tenant-Id` and `X-Source-Id`, and `envs.py` stores values at
the scope's `.secret/envs.json`.

The missing piece is runtime consumption. Shell execution builds subprocess
env from `os.environ.copy()`, command hooks build env from `os.environ` plus
handler-level env, and MCP stdio launch config uses only the configured client
env. Persisted tenant env values therefore do not reach the places where auth
tokens are needed.

The main constraint is multi-tenant concurrency. Scope env values must not be
written into process-global `os.environ`, because concurrent requests from
different tenants and sources share the same Python process.

## Goals / Non-Goals

**Goals:**

- Make current-scope env values available to shell commands, command hook
  handlers, and MCP stdio server processes.
- Keep `/api/envs` file-scoped and source-scoped, using `scope_id` for storage
  and lookup.
- Centralize env merge behavior so subprocess callers do not each implement
  their own tenant env loading.
- Protect runtime isolation keys from tenant-provided overrides.
- Preserve explicit call-level env overrides for hooks and MCP client config.
- Avoid exposing secret values through routine read APIs, logs, traces, or
  diagnostic messages.

**Non-Goals:**

- Do not add process-wide mutation of tenant env values into `os.environ`.
- Do not introduce encrypted secret storage in this change.
- Do not redesign provider API key storage.
- Do not let ordinary current-scope env API calls write arbitrary target
  tenants; target writes must use a separate manager/internal endpoint.
- Do not make every Python function transparently read tenant env values via
  `os.getenv`; Python code should use explicit helpers such as
  `get_tenant_env` or the runtime env builder.
- Do not guarantee that user-authored commands cannot print their own env
  values to the user-visible shell output; this change controls automatic
  system handling of secrets, not arbitrary command behavior.

## Decisions

### Decision: Introduce a shared runtime env builder

Create a helper that builds an execution env from:

```text
base process env
  < tenant runtime env from current scope .secret/envs.json
  < call-specific env
```

The helper should live close to env/config utilities so shell, hook runtime,
MCP launch code, and runtime env-reference resolution can share it without
depending on agent-specific modules. It should accept an explicit
runtime scope/tenant argument in addition to reading context variables, so
long-lived setup paths and rebuild paths do not accidentally use a missing or
stale context.

Alternative considered: load tenant env directly inside each execution path.
This was rejected because merge precedence, protected key handling, and scope
lookup would drift across shell, hooks, and MCP.

### Decision: Inject env only into subprocess boundaries

Tenant env values are copied into the env dict passed to subprocess creation.
They are not synced into process-global `os.environ` for API writes or runtime
execution.

Alternative considered: call `save_envs(..., path=None)` or otherwise sync
tenant env to `os.environ`. This was rejected because a single process serves
multiple scopes concurrently and process-global env mutation would leak secrets
across tenants.

### Decision: Preserve scope identity semantics

The env lookup path must use the current effective runtime scope. If explicit
tenant input is accepted by helper APIs, encoded `scope_id` values are allowed,
but logical tenant IDs must not bypass source scoping for scoped requests.

Alternative considered: store auth env by logical `tenant_id` only. This was
rejected because the current runtime model intentionally isolates local state
by `source_id + tenant_id`.

### Decision: Validate env keys at the API boundary

The env API should validate keys on write using a portable environment
variable name format, such as `^[A-Za-z_][A-Za-z0-9_]*$`, and reject empty,
malformed, or reserved names. Values remain strings; non-string values should
be rejected or converted only by an explicitly documented compatibility path.

Alternative considered: rely on the frontend's existing validation. This was
rejected because API callers can bypass the console and malformed keys behave
inconsistently across POSIX shells, Windows, Python subprocesses, and MCP
servers.

### Decision: Protect runtime and path-control env keys

Runtime env injection must skip or reject variables that can alter tenant
isolation, shell startup, interpreter behavior, dynamic loading, or executable
resolution. The protected set should include at least:

- `SWE_WORKING_DIR`
- `SWE_SECRET_DIR`
- `PATH`
- `HOME`
- `SHELL`
- `BASH_ENV`
- `ENV`
- `ZDOTDIR`
- `IFS`
- `CDPATH`
- `PYTHONPATH`
- `PYTHONHOME`
- `LD_LIBRARY_PATH`
- `DYLD_LIBRARY_PATH`

The filter must be applied to the final env contribution from tenant env and
tenant-controlled config env. Call-specific env remains higher priority for
normal auth keys, but it must not bypass protected-key filtering unless the
caller is a trusted system component using an explicit internal escape hatch.
The shell tool already prepends the active Python executable directory for
runtime correctness; tenant config should not be able to replace that path
setup unless a later design adds a constrained, explicit PATH extension
mechanism.

Alternative considered: allow all env keys because users control their own
tenant. This was rejected because tenant env is used inside shared service
processes and can affect isolation and interpreter behavior.

### Decision: Keep non-protected call-specific env highest priority

Hook `handler.env` and MCP client config `env` remain explicit, local
overrides and should win over tenant runtime env. This preserves existing
configuration semantics and lets a hook or MCP client intentionally override a
shared tenant env key.

Alternative considered: make tenant env highest priority. This was rejected
because it would unexpectedly break existing MCP/hook configs that already
specify env values. Alternative considered: let call-specific env override
protected keys. This was rejected because hook and MCP config are also
tenant-controlled in normal operation and must not become an isolation bypass.

### Decision: Make secret readback safe by default and avoid reveal in v1

Secret-bearing env values should not be returned in full by routine list APIs.
The safer contract is:

- list returns keys and masked values or metadata by default;
- writes provide full values;
- preserving an existing secret does not require the client to read the full
  value first;
- v1 should not add a normal full-value reveal path.

This implies either additive update/delete endpoints or full-replace semantics
that can distinguish "unchanged masked value" from "set this literal value".

Alternative considered: keep full-value `GET /api/envs` forever for editing
convenience. This was rejected because the feature is explicitly for auth
information and routine full-value readback expands the secret exposure surface.
Alternative considered: add a privileged reveal path in v1. This was deferred
because the core use case is write/update plus runtime injection, not secret
exfiltration through the console.

### Decision: Resolve env references without process-global expansion

Any runtime integration that currently expands env references with
`os.path.expandvars` or `os.environ` should use tenant-aware lookup when the
reference is intended to resolve tenant auth values. This includes MCP HTTP
headers and similar tool integration configuration, not just subprocess env.
Tenant-aware references should use an explicit syntax, such as
`${ENV:KEY}`, so literal values and ordinary process-env expansion are not
silently reinterpreted as tenant secret lookups.

Alternative considered: only support subprocess env injection. This was
rejected because not all tool integrations are subprocesses, and HTTP MCP
clients may also need tenant-scoped auth headers.

### Decision: Preserve secret file safety properties

The tenant env store should keep secret-file safety explicit: create parent
secret directories with owner-only permissions where the platform supports it,
write env files with owner-only permissions, and use atomic replace semantics
to avoid partial JSON files during concurrent writes or process interruption.

Alternative considered: rely on the existing JSON write behavior as an
implementation detail. This was rejected because the env store now carries
auth material by design, so persistence safety is part of the feature contract.

### Decision: Implement target-tenant env writes as a separate privileged API

The existing `/api/envs` endpoint writes the current request scope. Because
the desired control-plane flow needs to configure auth values for a specified
tenant, v1 should add a separate manager/internal endpoint that requires both
target tenant and source identity, validates identities, bootstraps the target
scope if needed, and records audit metadata.

Alternative considered: add `tenant_id` to the existing `/api/envs` request
body. This was rejected because ordinary tenant-scoped requests should not
gain the ability to write arbitrary tenant secrets.

## Risks / Trade-offs

- [Secret exposure through list API] -> Add masked list responses and
  update/delete semantics that do not require full-value readback; do not add a
  routine full-value reveal path in v1.
- [Secret exposure through logs/traces] -> Never log env values, mask ignored
  values, and register injected secret values with existing tracing/output
  redaction where available.
- [Breaking existing env names] -> Reject invalid or protected keys at write
  time where possible, and report ignored protected keys by name only where
  legacy stored values exist.
- [MCP lifecycle staleness] -> MCP stdio clients are long-lived; env changes
  apply on client restart/reload, not necessarily to already-running MCP
  subprocesses.
- [Partial or racing writes] -> Use atomic file replacement and preserve
  secret file permissions.
- [Performance overhead] -> Reading a small JSON file per subprocess launch is
  acceptable; if needed, cache by scope with file mtime invalidation.
- [Ambiguous scope in non-HTTP paths] -> Fail closed, use explicitly bound
  tenant context, or pass explicit runtime scope to the helper; do not silently
  fall back to default tenant env.
- [Distributed config with protected env] -> Apply protected-key filtering
  after merging tenant env and tenant-controlled config env so distributed MCP
  or hook configs cannot bypass isolation.

## Migration Plan

1. Add backend env key validation, safe read/update semantics, and a migration
   stance for any legacy protected or malformed env keys.
2. Add the shared tenant runtime env builder and protected-key filtering.
3. Update shell execution to use the helper before applying existing Python
   runtime path guard behavior.
4. Update command hook execution to use the helper with `handler.env` as
   call-specific env.
5. Update MCP stdio launch config to use the helper with MCP client config
   env as call-specific env.
6. Update MCP HTTP/header env reference resolution to use tenant-aware env
   lookup where applicable.
7. Add tests for merge precedence, protected keys, scope isolation, and no
   process-global env mutation.
8. Adjust frontend copy and edit flow to clarify env values apply to the current
   source-scoped tenant.

Rollback is straightforward: execution paths can return to their previous env
construction behavior while leaving stored `.secret/envs.json` files intact.

## Open Questions

No open technical questions remain for v1. Product owners can still choose the
exact route name and UI placement for the manager/internal target-scope write
API during implementation.
