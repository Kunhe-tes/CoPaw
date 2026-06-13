# cron-execution-model-slot Specification

## Purpose
TBD - created by archiving change cron-execution-model-slot. Update Purpose after archive.
## Requirements
### Requirement: Cron jobs can declare an execution model slot
The cron job API SHALL accept an optional top-level `model_slot` with `provider_id` and `model` for agent cron jobs. If `model_slot` is absent, the cron job SHALL remain bound to the tenant default model at execution time rather than persisting the default model from creation time.

#### Scenario: Create agent cron job with explicit model slot
- **WHEN** a client creates an agent cron job with `model_slot.provider_id` and `model_slot.model` that exist in the current tenant provider configuration
- **THEN** the API SHALL persist the cron job with that top-level `model_slot`
- **AND** subsequent read/list responses SHALL include the same `model_slot`

#### Scenario: Create agent cron job without explicit model slot
- **WHEN** a client creates an agent cron job without `model_slot`
- **THEN** the API SHALL persist the cron job without a `model_slot`
- **AND** the job SHALL use the current tenant default model when each run starts

#### Scenario: Reject invalid explicit model slot
- **WHEN** a client creates or updates an agent cron job with a `model_slot` whose provider does not exist or whose model is not in that provider's `models + extra_models`
- **THEN** the API SHALL reject the request before saving the job

#### Scenario: Clear model slot for text cron job
- **WHEN** a client creates or updates a text cron job with `model_slot`
- **THEN** the API SHALL save the text cron job without `model_slot`
- **AND** the text cron job SHALL NOT perform model resolution during execution

### Requirement: Cron execution uses scoped model resolution
Agent cron execution SHALL resolve the effective model by first using a request-scoped cron model override when present, then falling back to the tenant default model. The scoped override MUST NOT mutate tenant active-model state.

#### Scenario: Explicit model slot drives execution
- **WHEN** an agent cron job with a valid `model_slot` runs
- **THEN** model creation SHALL use that slot for the run
- **AND** the tenant's active model configuration SHALL remain unchanged

#### Scenario: Missing model slot uses runtime tenant default
- **WHEN** an agent cron job without `model_slot` runs after the tenant default model has changed
- **THEN** the run SHALL use the tenant default model that is active at run start

#### Scenario: Trace and hook model labels use effective model
- **WHEN** an agent cron job runs with an explicit model slot or falls back to the tenant default model
- **THEN** trace and hook model labels SHALL report the effective model used by that run

### Requirement: Invalid stored model slots fall back during execution
If a persisted agent cron job has a `model_slot` that no longer resolves at execution time, execution SHALL fall back to the current tenant default model without a user-facing error. The fallback SHALL be visible in operational records.

#### Scenario: Stored provider is removed before execution
- **WHEN** an agent cron job has a persisted `model_slot` whose provider no longer exists when the run starts
- **THEN** the run SHALL use the current tenant default model
- **AND** the user-facing scheduled result SHALL NOT report a model-slot error
- **AND** logs SHALL include the fallback reason and original model slot

#### Scenario: Stored model is removed before execution
- **WHEN** an agent cron job has a persisted `model_slot` whose model is no longer in the provider's `models + extra_models` when the run starts
- **THEN** the run SHALL use the current tenant default model
- **AND** logs SHALL include the fallback reason and original model slot

#### Scenario: Monitor execution records fallback metadata
- **WHEN** a cron run falls back from a stored `model_slot` to the tenant default model
- **THEN** the Monitor execution `meta` JSON SHALL include the original `model_slot`, the effective model slot, and `fallback_reason`
- **AND** no Monitor database column migration SHALL be required for this metadata

### Requirement: Cron broadcast preserves model slots only when target tenant supports them
Cron broadcast SHALL copy a source job's `model_slot` only when the target tenant has the same provider and model. If the target tenant lacks the source model slot, the target job SHALL be saved without `model_slot` and SHALL use the target tenant default model at execution time.

#### Scenario: Broadcast copies model slot to compatible target tenant
- **WHEN** a source cron job with `model_slot` is broadcast to a target tenant that has the same `provider_id` and `model`
- **THEN** the target cron job SHALL be created with the same `model_slot`
- **AND** the broadcast result for that tenant SHALL have `success=true` and empty `warning`

#### Scenario: Broadcast clears model slot for incompatible target tenant
- **WHEN** a source cron job with `model_slot` is broadcast to a target tenant that does not have the same provider/model
- **THEN** the target cron job SHALL be created without `model_slot`
- **AND** the broadcast result for that tenant SHALL have `success=true`
- **AND** the broadcast result `warning` SHALL equal `model_slot not copied: provider/model unavailable in target tenant`

### Requirement: Cron management UI exposes execution model selection
The cron management UI SHALL let users choose either the tenant default model or an explicit configured provider/model for agent cron jobs. The UI SHALL display the saved model selection in job lists and editing forms.

#### Scenario: Create agent cron job using tenant default model in management UI
- **WHEN** a user creates an agent cron job in the cron management drawer and chooses tenant default model
- **THEN** the frontend SHALL submit the cron job without `model_slot`

#### Scenario: Create agent cron job using explicit model in management UI
- **WHEN** a user creates an agent cron job in the cron management drawer and selects a configured provider/model
- **THEN** the frontend SHALL submit `model_slot` with the selected provider and model

#### Scenario: Hide model selection for text cron job
- **WHEN** a user switches the cron management drawer to text task type
- **THEN** the UI SHALL hide or disable model selection
- **AND** the submitted payload SHALL NOT include `model_slot`

#### Scenario: Job list displays execution model
- **WHEN** the cron management list renders a job without `model_slot`
- **THEN** the list SHALL display that the job uses the tenant default model
- **WHEN** the list renders a job with `model_slot`
- **THEN** the list SHALL display the selected provider/model or its friendly name

