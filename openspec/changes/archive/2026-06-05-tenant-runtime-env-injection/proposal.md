## Why

Tenant-scoped environment variables can already be saved through `/api/envs`,
but tool execution paths do not consistently load them. As a result, auth
values configured by the frontend are persisted but are not available to shell
commands, command hooks, or MCP stdio servers at execution time.

This matters now because source-scoped runtime isolation treats
`source_id + tenant_id` as the local-state boundary, so auth env injection must
follow the same `scope_id` contract without falling back to process-global
environment mutation.

## What Changes

- Introduce a tenant runtime env capability that loads the current runtime
  scope's `.secret/envs.json` and merges it into subprocess environments.
- Reuse the existing `/api/envs` storage endpoint for current-scope env writes
  and document that it saves auth values for the active `scope_id`.
- Add a shared runtime env builder used by shell command execution, command
  hook execution, and MCP stdio launch configuration.
- Add safe read/update semantics for secret-bearing env values so APIs do not
  require full-value readback in order to preserve existing secrets.
- Preserve multi-tenant safety by never syncing scope env values into
  process-global `os.environ` during tenant API writes or tool execution.
- Validate env keys and protect runtime isolation variables from tenant or
  config-level env override so configured auth values cannot change workspace,
  secret, interpreter, shell startup, or runtime path boundaries.
- Keep call-specific env overrides, such as hook `handler.env` and MCP client
  config `env`, higher priority than tenant runtime env values.
- Resolve tenant env references for tool integration configuration without
  relying on process-global `os.environ`.
- Add an explicit manager/internal target-scope env write API for cases where
  the frontend or control plane must configure auth values for a specified
  tenant and source.

## Capabilities

### New Capabilities

- `tenant-runtime-env-injection`: Defines how tenant-scoped persisted env values
  are loaded and injected into runtime subprocess environments.

### Modified Capabilities

- `source-scoped-runtime-isolation`: Clarifies that env storage and runtime env
  lookup use `scope_id` rather than logical `tenant_id`.

## Impact

- Backend env store and config utilities:
  - `src/swe/envs/store.py`
  - `src/swe/config/utils.py`
- Tenant env API:
  - `src/swe/app/routers/envs.py`
- Runtime config/env reference resolution:
  - MCP HTTP header/env expansion paths
  - Hook HTTP secret reference paths
- Runtime execution paths:
  - `src/swe/agents/tools/shell.py`
  - `src/swe/agents/hook_runtime/executor.py`
  - `src/swe/app/mcp/stdio_launcher.py`
  - MCP client construction/rebuild paths that pass stdio env values
- Tests:
  - Tenant env router/store tests
  - Shell tenant boundary tests
  - Hook runtime command handler tests
  - MCP stdio launch tests
- Frontend:
  - Existing environment variables page continues to call `/api/envs`; optional
    UI copy may clarify that values apply to the current source-scoped tenant.
