# Batch Dispatch Scheduler Implementation Plan

## Scope

Implement callback-driven batch dispatch so the external scheduler calls the Scheduler service for a batch parent, then Scheduler dispatches the parent and its children through SWE's existing internal cron callback. Scheduler must not discover parent runs by scanning `swe_cron_jobs`.

## Design Commitments

- External scheduler remains the physical timer for batch parents.
- Scheduler owns batch orchestration, intent ordering, worker slots, retry/refill, and worker capacity decisions.
- SWE remains the executor and records final execution feedback.
- Parent and children are all execution intents in the same batch queue; parent is not prioritized.
- Worker capacity is configured in database tables by `(source_id, provider_id, model_id)`, with missing provider normalized to `default`.
- Feedback-based resizing only cares about success vs failed terminal outcomes for now.
- Batch notifications use `parent_scheduled_fire_at + notification_delay_minutes`; broadcast offset is ignored for dispatch-managed runs.

## Implementation Tasks

1. Add scheduler parent callback API.
   - Add `POST /api/scheduler/cron/callback`.
   - Accept direct JSON and external scheduler-style callback fields.
   - Fetch the parent job and active batch children from `swe_cron_jobs`.
   - Create or reuse a deterministic batch row for `(parent_job_id, scheduled_fire_at)`.
   - Enqueue execution intents for parent plus children.
   - Trigger immediate dispatch refill.

2. Add durable tables and schema updates.
   - Add `swe_cron_dispatch_batches`.
   - Add `swe_cron_dispatch_model_worker_policy`.
   - Add `swe_cron_dispatch_worker_strategy`.
   - Extend dispatch intents with `provider_id`, `model_id`, and `scheduled_fire_at`.
   - Extend worker capacity audit with provider/model/strategy, previous/next workers, error rate, and matched rule details.

3. Replace scanner dispatch semantics.
   - Stop app startup loop from scanning parent jobs.
   - Keep a lightweight loop only for stale recovery / worker adjustment if needed.
   - Dispatch both `parent` and `child` intent roles to SWE callback.

4. Implement DB-configured worker policy.
   - Resolve strategy by `(source_id, provider_id, model_id)` and time windows.
   - Use baseline/min/max from strategy for initial capacity.
   - Use per-scope in-flight counts to decide available slots.
   - Adjust at `adjust_interval_seconds` using recent terminal error rate.
   - Record every adjustment decision and reason.

5. Preserve rollout and rollback behavior.
   - Opening parent batch dispatch switches only parent callback URL to Scheduler and leaves parent `external_job_id` stable.
   - Batch children pause existing external scheduler jobs and no longer register new external jobs.
   - Closing parent batch dispatch restores parent callback to SWE and resumes or registers child external jobs.
   - New broadcast dispatch supports an `enable_batch_dispatch` switch.

6. Add logs at required points.
   - Scheduler callback received.
   - Parent/child job fetch.
   - Initial worker capacity creation.
   - Each SWE callback attempt.
   - Each worker adjustment with reason.
   - Execution feedback / task end handling.

7. Update tests.
   - Parent callback enqueues parent plus children and dispatches by sorted order.
   - Duplicate callback reuses batch/intents.
   - Worker strategy resolution and adjustment.
   - SWE notification due time for dispatch-managed runs.
   - Frontend helper behavior for parent switch / broadcast switch.

8. Generate development documentation.
   - Document data tables, API contracts, end-to-end flow, callback metadata, worker strategy, rollback, and operational notes.
