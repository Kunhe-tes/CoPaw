## Why

Scheduled agent tasks currently always execute with the tenant's active model at runtime. Users need to pin a specific model for selected scheduled tasks while preserving default-model behavior for tasks that do not explicitly choose a model.

## What Changes

- Add an optional top-level `model_slot` to `CronJobSpec` for agent scheduled jobs.
- Keep omitted `model_slot` dynamic: each run uses the current tenant default model at execution time.
- Validate explicit `model_slot` on create/update against the current tenant's configured provider models.
- Ignore and clear `model_slot` for text scheduled jobs because they do not invoke an LLM.
- During execution, bind a request-scoped model override so the selected model affects model creation, tracing, and hook model labels without mutating tenant active-model state.
- If a previously valid stored `model_slot` becomes unavailable at execution time, silently fall back to the tenant default model for the user-facing result while recording the fallback details in logs and Monitor execution metadata.
- Extend cron broadcast so model slots are copied only when the target tenant has the same provider/model; otherwise the target job uses the target tenant default model and the broadcast result includes a non-failing warning.
- Add model selection and display to both cron management and quick scheduled-task creation UI.

## Capabilities

### New Capabilities
- `cron-execution-model-slot`: Cron job API, execution, broadcast, observability, and management UI behavior for optional scheduled-task model selection.

### Modified Capabilities
- `scheduled-task-popup`: Quick scheduled-task creation from case details can select an execution model and send it in the created cron job.

## Impact

- Backend: `src/swe/app/crons/*`, `src/swe/agents/model_factory.py`, provider model validation helpers, Monitor sync payloads, and related tests.
- Frontend: cron job API types/modules, `Control/CronJobs` management UI, `ScheduledTaskPopup`, and case detail scheduled-task creation.
- Observability: Monitor execution `meta` records original/effective model slots and fallback reason without adding database columns.
- Contracts: Cron job responses include `model_slot`; broadcast results include `warning`.
