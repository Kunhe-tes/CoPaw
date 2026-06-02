## Context

Cron jobs are persisted as `CronJobSpec` records and executed later through `CronExecutor`, which forwards a permissive `CronJobRequest` into `runner.stream_query()`. Agent model creation currently resolves the tenant active model through `ProviderManager.get_active_model()` inside `create_model_and_formatter()`, so scheduled jobs cannot pin a model independently from the tenant default.

The change must preserve multi-tenant isolation, source/scope-aware provider storage, existing cron task routing, and the current behavior where jobs without a model choice follow the tenant default model at execution time.

## Goals / Non-Goals

**Goals:**
- Allow agent cron jobs to optionally persist a top-level `model_slot`.
- Keep default-model jobs dynamic at execution time when `model_slot` is absent.
- Validate explicit model slots on create/update using the current tenant's configured providers and `models + extra_models`.
- Execute pinned-model jobs without mutating tenant active-model state.
- Keep user-facing execution silent when a previously valid slot becomes unavailable, while recording fallback facts operationally.
- Support model selection in both the cron management UI and quick scheduled-task popup.
- Preserve cross-tenant broadcast success when a target tenant lacks the source model.

**Non-Goals:**
- Do not add per-agent model configuration or restore deprecated agent-scope active model behavior.
- Do not add Monitor database columns for model fallback metadata.
- Do not make text cron jobs invoke models or retain a model slot.
- Do not change cron timing, coordination, task-chat binding, or LLM workload concurrency semantics.

## Decisions

1. Store the selected model as `CronJobSpec.model_slot`.

   Alternatives considered: store in `runtime`, `request`, or `meta`. A top-level field is easier to validate, serialize, display, edit, broadcast, and keep distinct from arbitrary agent request payloads or runtime timeout/concurrency controls.

2. Use execution-time default model resolution when `model_slot` is absent.

   A job without an explicit model slot uses the current tenant default model for each scheduled or manual run. This avoids freezing stale defaults into old jobs and matches existing cron behavior.

3. Reject invalid explicit slots at create/update, but fallback at execution time if persisted slots drift.

   Create/update validation catches bad API calls and frontend bugs early. Execution fallback handles later configuration drift, such as a provider/model being removed after the job was saved, without failing the user-facing scheduled result.

4. Clear model slots for text jobs.

   Text jobs do not call the model runtime, so retaining a model slot would be misleading. The API will normalize text jobs by clearing the submitted model slot rather than rejecting the whole request.

5. Bind model overrides through request-scoped context.

   `CronExecutor` will bind a scoped model slot around the agent run. `create_model_and_formatter()` and model-label helpers will prefer that scoped slot before reading `ProviderManager.get_active_model()`. This avoids mutating `ProviderManager.active_model`, which would be unsafe under concurrent cron and chat executions.

6. Record fallback details in Monitor execution `meta`.

   Monitor execution metadata should include the original `model_slot`, effective model slot, and `fallback_reason` when fallback occurs. `input_snapshot` remains the actual request snapshot. This keeps observability without schema migration.

7. Copy model slots during broadcast only when valid for the target tenant.

   If the target tenant has the same provider/model, copy the slot. Otherwise save the target job without `model_slot`, keep `success=true`, and return a warning so the caller can see that the target will use its tenant default model.

8. Show the effective selection in management UI.

   Cron management list/edit UI will display a selected model or “tenant default model”. The quick scheduled-task popup will offer the same default-vs-explicit choice when creating a task from case details.

## Risks / Trade-offs

- Invalid stored model silently falls back for users → Mitigation: log the fallback and record original/effective model metadata in Monitor execution `meta`.
- ContextVar override could leak across concurrent runs if reset incorrectly → Mitigation: implement a context manager with token reset and unit tests for nested/default behavior.
- Provider models can differ across tenants during broadcast → Mitigation: validate per target tenant and degrade to default model with a warning instead of failing the entire broadcast.
- UI model lists can become stale while the form is open → Mitigation: backend remains authoritative and rejects invalid create/update payloads.
- Model labels can become inconsistent across model factory, tracing, and hooks → Mitigation: centralize scoped-model resolution and have label helpers use the same resolver.

## Migration Plan

Existing cron jobs have no `model_slot` and will continue using execution-time tenant defaults. No data migration is required. Rollback is safe for persisted jobs without `model_slot`; jobs created with `model_slot` during the rollout would need the field ignored or removed if rolling back to code that rejects unknown fields.

## Open Questions

None.
