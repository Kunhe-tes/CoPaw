## 1. Backend Data Contract

- [x] 1.1 Add optional top-level `model_slot` to `CronJobSpec` using the existing provider model slot shape.
- [x] 1.2 Normalize text cron jobs so saved specs clear any submitted `model_slot`.
- [x] 1.3 Add provider/model validation for agent cron job create and replace paths against the current tenant's configured `models + extra_models`.
- [x] 1.4 Update cron API response models and TypeScript API types so `model_slot` round-trips in create, replace, get, and list responses.

## 2. Scoped Model Resolution

- [x] 2.1 Add a request-scoped model slot override context manager with safe token reset semantics.
- [x] 2.2 Update `create_model_and_formatter()` to prefer the scoped override before reading the tenant active model.
- [x] 2.3 Update active/effective model label helpers used by tracing and hooks to report the scoped effective model when present.
- [x] 2.4 Bind the scoped model override around agent cron execution without mutating `ProviderManager.active_model`.

## 3. Execution Fallback And Observability

- [x] 3.1 Resolve the effective cron execution model before each agent run and detect missing provider/model drift.
- [x] 3.2 Fall back to the current tenant default model when a persisted `model_slot` no longer resolves.
- [x] 3.3 Log fallback reason, original `model_slot`, and effective model slot without surfacing a user-facing model error.
- [x] 3.4 Add Monitor execution `meta` payload support for original model slot, effective model slot, and `fallback_reason` while keeping `input_snapshot` as the actual request.

## 4. Cron Broadcast

- [x] 4.1 Extend `CronBroadcastTenantResult` with `warning: string = ""` in backend and frontend types.
- [x] 4.2 Validate source `model_slot` against each target tenant during broadcast.
- [x] 4.3 Copy `model_slot` only when the target tenant has the same provider/model.
- [x] 4.4 Clear `model_slot` and return `warning="model_slot not copied: provider/model unavailable in target tenant"` when a target tenant lacks the source model.

## 5. Frontend Cron Management UI

- [x] 5.1 Load current tenant configured providers and active model data for cron management forms.
- [x] 5.2 Add an execution model selector to the `Control/CronJobs` drawer for agent tasks with tenant-default as the default option.
- [x] 5.3 Hide or clear execution model selection when the drawer task type is text.
- [x] 5.4 Display execution model in the cron management list, showing tenant default when `model_slot` is absent.
- [x] 5.5 Preserve and submit `model_slot` correctly for create and edit flows.

## 6. Frontend Quick Scheduled Task Popup

- [x] 6.1 Add tenant-default and configured provider/model options to `ScheduledTaskPopup`.
- [x] 6.2 Keep tenant default as the popup default and omit `model_slot` when selected.
- [x] 6.3 Submit top-level `model_slot` from `CaseDetailDrawer` quick scheduled-task creation when the user selects an explicit model.
- [x] 6.4 Update popup and cron utility tests for default and explicit model creation payloads.

## 7. Tests And Verification

- [x] 7.1 Add backend unit tests for valid `model_slot` persistence, invalid create/update rejection, omitted default behavior, and text-job clearing.
- [x] 7.2 Add backend unit tests proving scoped overrides do not mutate tenant active model and do not leak across concurrent/default runs.
- [x] 7.3 Add backend unit tests for execution fallback and Monitor execution `meta` contents.
- [x] 7.4 Add backend unit tests for broadcast copy, clear, and warning behavior across target tenants.
- [x] 7.5 Run focused Python tests with `venv/bin/python -m pytest` for cron, model factory, and provider-related units.
- [x] 7.6 Run focused frontend tests for cron management, `ScheduledTaskPopup`, and cron utilities.
