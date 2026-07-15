# Batch Dispatch Rollout And Rollback Design

## Summary

This change lets operators opt cron broadcast jobs into the new batch
dispatch path and safely roll them back to the existing external scheduler
path.

The design keeps the service boundary unchanged:

- Scheduler owns batch orchestration.
- SWE remains the execution target.
- The external scheduler still owns the wall-clock trigger.

Batch mode changes where the external scheduler callback lands for the parent
job. It does not move execution out of SWE.

## Goals

- Add a durable parent job switch for batch dispatch.
- Add a broadcast-dialog switch for whether a new distribution should use
  batch dispatch after distribution completes.
- Make batch enable and rollback operations asynchronous so large parent-child
  groups do not block the request thread.
- Support existing jobs by turning an existing broadcast parent and its
  children into a batch-managed group.
- Support rollback by restoring the parent and children to the previous SWE
  callback based external scheduling behavior.
- Reuse existing external scheduler job IDs whenever possible.
- Start Scheduler dispatching with a configured default worker capacity and
  adjust that capacity from execution feedback.
- Preserve current notification behavior for non-batch jobs, while making
  batch-managed broadcast notifications use the parent scheduled fire time as
  their delay baseline.
- Keep ordinary cron jobs and ordinary broadcast jobs unchanged unless an
  operator explicitly opts in.

## Non-Goals

- Do not migrate all cron jobs automatically.
- Do not let Scheduler execute jobs directly.
- Do not remove the SWE `/api/internal/cron/callback` execution contract.
- Do not change notification semantics for jobs that are not explicitly
  batch-managed.
- Do not make Scheduler scan for due parent jobs as the primary trigger path.

## Existing Context

SWE already has two durable metadata fields that can define the batch-managed
broadcast group:

- `meta.broadcast_dispatch_intents_enabled`
- `meta.broadcast_source_job_id`

A broadcast parent is batch-managed when:

- `broadcast_dispatch_intents_enabled` is true.
- `broadcast_source_job_id` is absent.

A broadcast child is batch-managed when:

- `broadcast_source_job_id` points to the parent job.
- `broadcast_dispatch_intents_enabled` is true.

The existing broadcast creation path already writes `broadcast_source_job_id`
on children. The new behavior only needs to decide when to also write or remove
`broadcast_dispatch_intents_enabled`.

## UI Design

### Parent job editor

The cron job editor exposes a switch for non-child jobs:

```text
Use batch dispatch
```

When enabled, the saved parent job becomes batch-managed.

When disabled on an already batch-managed parent, the system rolls the parent
and its children back to normal external scheduler callbacks.

Child jobs do not show this switch because their batch state is derived from
the parent relationship.

### Broadcast dialog

The broadcast dialog exposes a switch:

```text
Use batch dispatch after distribution
```

The default value follows the parent job's current batch state:

- Existing batch parent: default on.
- Ordinary parent: default off.

When enabled, the broadcast operation creates or refreshes children and then
places the parent and resulting children in batch mode.

When disabled for a currently batch-managed parent, the dialog should ask for
confirmation because this rolls the group back to normal external scheduling.

## API Design

Extend `CronBroadcastRequest` with:

```json
{
  "enable_batch_dispatch": true
}
```

The frontend passes this field from the broadcast dialog.

The regular job create/update API continues to persist the parent-level
`meta.broadcast_dispatch_intents_enabled` switch through the existing cron job
model.

Batch enable and rollback must return an asynchronous task response instead of
waiting for every parent and child external scheduler update to finish. The
response should include enough identity for polling:

```json
{
  "task_id": "batch-dispatch-transition-...",
  "status": "running",
  "operation": "enable_batch_dispatch"
}
```

The same task mechanism should cover both enable and rollback operations. The
task result must summarize parent update status, processed child count, failed
child count, and per-tenant failures.

## Batch Enable Flow

When a parent job is saved with batch dispatch enabled, or a broadcast request
sets `enable_batch_dispatch=true`, SWE schedules an asynchronous batch
transition task. That task performs the following steps:

1. Persist `meta.broadcast_dispatch_intents_enabled=true` on the parent.
2. Update or register the parent external scheduler job using the same
   `external_job_id` when present.
3. Change only the parent external scheduler callback URL from SWE callback to
   Scheduler callback.
4. Keep the parent `jobParam` shape compatible with the existing SWE callback
   contract.
5. For every existing or newly distributed child, persist
   `meta.broadcast_dispatch_intents_enabled=true` while preserving
   `meta.broadcast_source_job_id`.
6. If a child already has `external_job_id`, pause that external scheduler job.
7. If a child does not have `external_job_id`, do not register a new external
   scheduler job while it is batch-managed.

The API returns as soon as the transition task is accepted. Operators can poll
the task until the parent and child external scheduler updates finish.

After the transition succeeds, wall-clock execution is:

```text
External scheduler -> Scheduler parent callback -> SWE parent and child callbacks
```

Scheduler calls SWE parent and child jobs through `/api/internal/cron/callback`
with `callback_source=dispatch_service` and dispatch intent metadata.

## Batch Callback Execution Flow

When Scheduler receives the parent callback from the external scheduler, it
creates one dispatch batch for that scheduled fire. The batch contains execution
intents for both the parent job and every batch-managed child job.

The parent job is not a priority item and is not a prerequisite for child jobs.
It participates in the same ordering algorithm as children. The ordering input
must include the parent job as one candidate alongside the children, then write
the computed order to every execution intent.

Scheduler must not execute the parent job locally. Parent and child execution
intents both call SWE through the same internal cron callback path.

The current implementation's parent intent concept should therefore be treated
as a batch expansion trigger only. The real parent job execution must be a
separate execution intent in the expanded batch.

## Dispatch Batch Persistence

Scheduler should add a dispatch batch master record so every external scheduler
trigger has one durable row before intent expansion starts. The existing
`swe_cron_dispatch_intents`, `swe_cron_dispatch_events`, and
`swe_cron_executions` tables remain the detail tables.

### `swe_cron_dispatch_batches`

One row represents one parent callback / one scheduled batch run.

Recommended columns:

- `batch_id` primary key.
- `parent_job_id`.
- `parent_external_job_id`.
- `tenant_id`.
- `source_id`.
- `agent_id`.
- `scheduled_fire_at`.
- `callback_received_at`.
- `status`, such as `received`, `expanding`, `dispatching`, `running`,
  `completed`, `failed`, or `partial_failed`.
- `total_intents`.
- `pending_count`.
- `claimed_count`.
- `dispatched_count`.
- `completed_count`.
- `failed_count`.
- `first_dispatched_at`.
- `last_dispatched_at`.
- `completed_at`.
- `error_message`.
- `callback_metadata` JSON with sanitized request identifiers, never raw tokens
  or full encoded `jobParam`.
- `created_at`.
- `updated_at`.

Scheduler must create or upsert this row as the first durable step when the
Scheduler callback is received. The uniqueness rule is `batch_id`; `batch_id`
should remain deterministic for `(parent_job_id, scheduled_fire_at)` so duplicate
external scheduler callbacks reuse the same batch row instead of creating a new
batch.

Intent creation, callback dispatch, execution feedback, retry scheduling, stale
failure, and final completion should update the batch aggregate status and
counts. The detailed timeline still belongs in `swe_cron_dispatch_events`.

## Notification Timing

The existing non-batch broadcast path keeps its current notification behavior:
children that use `broadcast_notification_policy=original_schedule` compute the
notification due time from the original scheduled execution time plus
`broadcast_offset_minutes` plus `notification_delay_minutes`.

The batch-managed path has no per-child broadcast schedule offset. Scheduler
must include the parent scheduled fire time in the dispatch metadata for every
execution intent in the batch, including the parent execution intent. SWE should
then compute a successful automatic execution's `notification_due_at` as:

```text
parent_scheduled_fire_at + notification_delay_minutes
```

For batch-managed executions, SWE must ignore `broadcast_offset_minutes` when
calculating `notification_due_at`. If an execution finishes after its computed
notification due time, Monitor will still claim it after the execution record is
written because the due time is already in the past.

## Worker Capacity Flow

Scheduler starts dispatching each source/provider/model scope with a
database-configured baseline worker capacity. In this design, a worker is a
Scheduler dispatch capacity slot, not a SWE execution process. Each available
worker slot may claim and dispatch one ready execution intent at a time.

Dispatch capacity is a sliding concurrency window. If `effective_workers` is 5,
Scheduler may have at most five in-progress execution intents at once. A sixth
intent is not dispatched until one in-progress intent reaches a terminal state
or is marked failed by stale-timeout recovery. When a slot opens, Scheduler may
dispatch the next sorted ready intent immediately. It does not wait for all five
in-flight intents to finish, and it does not dispatch another group of five
unless five slots are actually available.

Worker capacity settings are database-managed, not environment-variable
managed. Scheduler resolves the active policy by `source_id`, `provider_id`, and
`model_id` before it adjusts capacity. The intent payload must carry enough
model identity for this lookup, using the cron job's effective
`model_slot.model` as `model_id` and the cron job's effective
`model_slot.provider_id` as `provider_id`. If `provider_id` is missing,
Scheduler must normalize it to `default` before looking up or recording worker
capacity.

Use two configuration tables:

### `swe_cron_dispatch_model_worker_policy`

This table maps a source/provider/model tuple to the strategy schedule for that
model. Its primary key is `(source_id, provider_id, model_id)`.

Recommended columns:

- `source_id`
- `provider_id`
- `model_id`
- `timezone`
- `default_strategy_id`
- `strategy_schedule` JSON, for time-window rules such as:

```json
[
  {"start": "00:00", "end": "08:00", "strategy_id": "off_peak"},
  {"start": "08:00", "end": "23:59", "strategy_id": "business_hours"}
]
```

- `enabled`
- `created_at`
- `updated_at`

Keeping the primary key as only `(source_id, provider_id, model_id)` means
time-based routing lives inside `strategy_schedule`. If operators later need
independently editable rows per time window, the key must expand to include the
window boundary.

### `swe_cron_dispatch_worker_strategy`

This table defines reusable worker-adjustment strategies.

Recommended columns:

- `strategy_id`
- `name`
- `min_workers`
- `baseline_workers`
- `max_workers`
- `adjust_interval_seconds`
- `feedback_window_seconds`
- `stale_execution_seconds`
- `error_rate_rules` JSON
- `enabled`
- `created_at`
- `updated_at`

`error_rate_rules` contains ordered rules. Each rule has an inclusive lower
bound, exclusive upper bound, an operation, and a value:

```json
[
  {"min": 0.00, "max": 0.05, "op": "add", "value": 1},
  {"min": 0.05, "max": 0.20, "op": "hold", "value": 0},
  {"min": 0.20, "max": 1.01, "op": "multiply", "value": 0.5}
]
```

Supported operations are `add`, `subtract`, `multiply`, `divide`, `set`, and
`hold`. The computed value is rounded to an integer and clamped to
`min_workers <= effective_workers <= max_workers`. `baseline_workers` is used
when no previous capacity snapshot exists for the source/provider/model scope.

Scheduler dispatching and worker resizing are separate loops:

- Dispatching should continue moving ready intents whenever capacity is
  available.
- Resizing should run only on the configured interval and use recent execution
  feedback.

Feedback inputs include successful completions, failed completions, pending
count, and in-flight count for the same source/provider/model scope. Missing
execution feedback after the strategy's stale timeout is counted as a failed
completion. The first policy does not classify internal failure reasons. It
only uses failure rate:

```text
error_rate = failed_terminal_count / max(1, successful_count + failed_terminal_count)
```

If there are no terminal completions in the feedback window, the strategy holds
the current capacity. Otherwise Scheduler finds the first matching
`error_rate_rules` row and applies its operation.

Every capacity decision should be recorded with its reason so operators can
explain why Scheduler scaled up, scaled down, or held steady.

The adjustment interval is also policy-scoped. Scheduler must evaluate whether
the interval elapsed per `source_id + provider_id + model_id + strategy_id`,
using the latest capacity snapshot or a persisted policy state. It must not
rely on a single process-local `_last_capacity_adjusted_at` timestamp for all
models.

The existing `swe_cron_dispatch_worker_capacity` table remains the audit table
for decisions. It should be extended to record `model_id`, `provider_id`,
`strategy_id`, `previous_workers`, `next_workers`, `error_rate`, and the matched
rule details. These fields are decision history, not configuration.

## Observability

Scheduler should write structured logs at every lifecycle boundary needed to
debug a batch without reading database rows by hand. Logs must include stable
identifiers such as `batch_id`, `intent_id`, `job_id`, `tenant_id`, `source_id`,
`worker_id`, `dispatch_attempt`, and `parent_scheduled_fire_at` when available.
They must not include raw tokens or full encoded `jobParam` payloads.

Required log points:

- Scheduler parent callback received from the external scheduler and persisted
  to `swe_cron_dispatch_batches`.
- Parent job and child job information fetched, including child count and any
  skip reason.
- Initial worker capacity resolved for a source/provider/model scope, including
  baseline, min, max, effective capacity, strategy id, adjustment interval, and
  stale timeout.
- Every SWE callback request attempt, including target job, intent role,
  attempt number, response status, latency, and failure details.
- Every worker-capacity adjustment, including previous capacity, next capacity,
  feedback counts, selected `strategy_id`, matched error-rate rule, operation,
  computed value before clamp, final value after clamp, and decision reason.
- Every execution feedback callback from SWE and every task-end transition,
  including terminal status, retry scheduling, stale-timeout failure, and
  whether dispatch refill was triggered.

## Rollback Flow

When the parent switch is disabled, or a broadcast request explicitly disables
batch dispatch for a currently batch-managed parent, SWE schedules an
asynchronous rollback task. That task performs the rollback as one logical
operation:

1. Remove `meta.broadcast_dispatch_intents_enabled` from the parent.
2. Update or register the parent external scheduler job using the same
   `external_job_id` when present.
3. Change the parent external scheduler callback URL back to
   `/api/internal/cron/callback`.
4. For every child whose `broadcast_source_job_id` points to the parent, remove
   `meta.broadcast_dispatch_intents_enabled`.
5. If a child has `external_job_id`, update it with the SWE callback and resume
   it when the child is enabled.
6. If a child is enabled and has no `external_job_id`, register it with the
   external scheduler and persist the returned ID.
7. If a child is disabled and has no `external_job_id`, keep it unregistered
   until it is enabled or otherwise saved through the normal cron path.

The API returns as soon as the rollback task is accepted. Operators can poll the
task until parent and child restoration finishes.

After rollback succeeds, wall-clock execution is:

```text
External scheduler -> SWE parent callback
External scheduler -> SWE child callback
```

Rollback must preserve `broadcast_source_job_id` so distribution management
features can still identify which children belong to the parent.

## Consistency Rules

- Parent and child batch state must not be allowed to diverge for the same
  broadcast group.
- The parent callback and child external scheduler state must be updated as a
  coordinated operation.
- If some children fail to update during enable or rollback, the response or
  task snapshot must expose partial failure details.
- While an enable or rollback transition task is running for a parent, another
  transition for the same parent must reuse or reject the existing task instead
  of running concurrently.
- Re-running enable or rollback must be idempotent.
- Existing ordinary cron jobs remain ordinary unless the parent batch switch or
  broadcast-dialog batch switch is explicitly enabled.

## Error Handling

External scheduler failures should not be silently swallowed. The caller should
receive a task result with clear partial-failure details when parent update
succeeds but one or more child updates fail.

For asynchronous broadcast tasks, the task result should include tenant-level
success, warning, and failure summaries so operators can retry the affected
targets.

Rollback should prefer restoring more jobs over failing fast on the first child.
Failures are reported after all reachable children have been attempted.

## Testing Plan

- Parent editor payload keeps `broadcast_dispatch_intents_enabled` only for
  non-child jobs.
- Broadcast dialog sends `enable_batch_dispatch` with the selected value.
- Enabling batch dispatch returns an asynchronous transition task response.
- Rolling back batch dispatch returns an asynchronous transition task response.
- Concurrent enable or rollback requests for the same parent reuse or reject
  the running transition task.
- Broadcast request with `enable_batch_dispatch=true` marks parent and children
  as batch-managed.
- Existing child with `external_job_id` is paused when batch mode is enabled.
- New child created under batch mode is not registered with the external
  scheduler.
- Disabling the parent switch removes parent and child batch flags.
- Rollback updates the parent callback back to SWE callback.
- Rollback resumes existing child external scheduler jobs.
- Rollback registers enabled children that lack `external_job_id`.
- Scheduler creates an execution intent for the parent job when it receives the
  parent callback.
- Parent execution intent and child execution intents use the same dispatch
  ordering algorithm; parent is not forced to order 0.
- Scheduler parent callback creates or reuses one `swe_cron_dispatch_batches`
  row before fetching job information or creating intents.
- Duplicate parent callbacks for the same parent scheduled fire reuse the same
  batch row and do not create duplicate batch runs.
- Batch aggregate status and counts update when intents are queued, dispatched,
  completed, failed, retried, or marked stale.
- Batch-managed executions compute notification due time from the parent
  scheduled fire time plus `notification_delay_minutes`.
- Batch-managed notification timing ignores `broadcast_offset_minutes`.
- Non-batch broadcast notification timing still uses the existing original
  schedule plus broadcast offset behavior.
- Scheduler starts from configured default worker capacity.
- With `effective_workers=5`, Scheduler dispatches at most five in-progress
  intents.
- When one in-progress intent completes or fails, Scheduler dispatches only the
  next sorted ready intent to refill the freed slot.
- Worker policy lookup uses `source_id + provider_id + model_id` and picks the
  configured strategy for the current time window. Missing provider id is
  normalized to `default`.
- Worker capacity uses the strategy's configured min, baseline, max, feedback
  window, stale timeout, and adjustment interval from the database.
- Error-rate rules can adjust worker capacity with `add`, `subtract`,
  `multiply`, `divide`, `set`, and `hold`.
- Failed terminal executions affect worker capacity through the configured
  error-rate rules regardless of internal failure reason.
- Adjustment interval checks are scoped by source/provider/model/strategy rather
  than a single process-local timestamp.
- Worker capacity decisions are persisted with decision reasons.
- Scheduler logs parent callback receipt, job-info fetch, worker initialization,
  SWE callback attempts, worker adjustments, and task-end transitions.
- Ordinary broadcast without `enable_batch_dispatch` preserves current
  behavior.
