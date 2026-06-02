## Why

`SourceSystemConfigMiddleware` currently binds effective Source System Configuration only for incoming HTTP requests. Scheduled work runs outside that request path, so agent jobs, heartbeat, and dream execution can miss source-scoped controls even when the run already has source-aware runtime identity.

The domain language now disambiguates this boundary as **Scheduled Run Boundary**: background scheduled work owned by the runtime, not `/cron` management API requests. We need one change that extends source-system-config runtime binding to that boundary without snapshotting configuration at job creation time.

## What Changes

- Extend Source System Configuration binding from HTTP middleware to the Scheduled Run Boundary.
- Make `CronManager` the single owner of scheduled-run source config binding for normal jobs, heartbeat, and dream execution.
- Resolve the scheduled-run source from explicit `source_id` first, then fall back to decoding runtime `scope_id`.
- Inject `SourceSystemConfigService` explicitly into scheduled runtime construction instead of reading `app.state` or module globals from cron execution paths.
- Preserve legacy behavior when a scheduled run has no source or when the runtime has no source config service: continue without binding.
- Fail scheduled work when a source and service both exist but `resolve_config()` reports unavailable or invalid configuration, rather than silently bypassing source-scoped controls.
- Bind source config across the whole scheduled-run business execution segment, not only around `runner.stream_query()`.

## Capabilities

### Modified Capabilities

- `source-system-config`: add execution-time binding semantics for the Scheduled Run Boundary.

## Impact

- Backend runtime wiring: `src/swe/app/_app.py`, workspace/runtime construction, and `src/swe/app/crons/*`.
- Runtime semantics: scheduled jobs, heartbeat, and dream execution will observe the latest effective Source System Configuration at run start.
- Observability and failure behavior: legacy source-less runs remain unbound, but invalid/unavailable config for sourced scheduled work becomes an execution error instead of a silent bypass.
- Tests: cron execution and source-system-config unit coverage need new boundary-binding scenarios.
