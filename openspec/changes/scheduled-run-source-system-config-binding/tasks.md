## 1. Runtime Dependency Plumbing

- [x] 1.1 Add explicit scheduled-runtime dependency plumbing so workspace creation can pass `SourceSystemConfigService` into `CronManager`.
- [x] 1.2 Update all `Workspace` / `MultiAgentManager` construction paths and relevant tests to support the injected source config service without reading `app.state` inside cron execution code.

## 2. Scheduled Run Boundary Binding

- [x] 2.1 Add a `CronManager` helper that resolves the scheduled-run source using explicit `source_id` first and runtime `scope_id` decoding second.
- [x] 2.2 Bind effective Source System Configuration around scheduled job execution, heartbeat execution, and dream execution.
- [x] 2.3 Keep legacy source-less or service-less scheduled runs unbound, preserving prior behavior and warning where appropriate.
- [x] 2.4 Propagate `resolve_config()` unavailable/invalid errors as scheduled-run failures when both source identity and service are present.

## 3. Tests And Verification

- [x] 3.1 Add unit tests for scheduled jobs proving sourced runs bind the latest effective Source System Configuration across the full execution segment.
- [x] 3.2 Add unit tests for heartbeat and dream execution covering explicit source, scope-derived source, and legacy source-less behavior.
- [x] 3.3 Add unit tests for service-missing passthrough and `resolve_config()` failure behavior.
- [x] 3.4 Run focused Python tests for cron and source-system-config runtime behavior.
- [x] 3.5 Run `openspec status --change scheduled-run-source-system-config-binding` and confirm the change is well-formed.
