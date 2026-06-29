## Context

Scheduled-job broadcast currently creates or refreshes child Scheduled Jobs for every selected target tenant inside `POST /cron/jobs/{job_id}/broadcast`. The route already limits concurrent target processing through `CRON_BROADCAST_CONCURRENCY`, but the HTTP request still waits for every target and each target can synchronously call the external scheduler.

The repository already has `CronBroadcastChildrenStore` for reverse-check snapshots. That store answers "which child jobs exist now" and is keyed by source job identity. Broadcast execution progress is a different concept: it needs a task id, per-target status, retry-safe results, and enough persistence for a page refresh or backend restart to retain the latest state.

## Goals / Non-Goals

**Goals:**

- Return from broadcast submission quickly with a durable task id and initial progress.
- Continue target-tenant broadcast work in a bounded background task.
- Persist per-target progress and final `CronBroadcastTenantResult` payloads.
- Reuse existing child jobs for the same source job and target tenant instead of creating duplicates.
- Let the Console display the currently running broadcast task when the broadcast modal opens, without continuous polling.

**Non-Goals:**

- No change to Scheduled Run execution, external scheduler callback execution, heartbeat, dream, or Monitor execution recording.
- No migration from per-tenant child Scheduled Jobs to one source-level fanout job.
- No automatic retry scheduler for failed broadcast targets in this change.
- No removal of existing broadcast child management APIs.

## Decisions

### Add a dedicated broadcast task store

Create `CronBroadcastTaskStore` for broadcast task progress instead of overloading `CronBroadcastChildrenStore`.

Alternatives considered:

- Reuse `CronBroadcastChildrenStore`: simpler file count, but it conflates "current child inventory" with "one broadcast operation's execution state" and lacks per-target lifecycle.
- Keep only in-memory task state: solves request timeout but loses progress on restart and cannot support reliable refresh.

The store will mirror existing storage conventions: use MySQL when the app has a connected DB and fall back to process memory otherwise.

### Keep the public broadcast route, change its response shape

`POST /cron/jobs/{job_id}/broadcast` will start a broadcast task and return the task summary. The Console will be updated in the same change, so the route does not need to preserve the old synchronous `results` response.

Alternatives considered:

- Add `/broadcast/async` and keep the old route: lower external compatibility risk, but it leaves the timeout-prone path in place and requires two Console paths.
- Add a query flag for async: unnecessary because the current synchronous behavior is the problem to remove.

### Reuse existing child refresh semantics for idempotence

The background target worker will continue to call `_broadcast_to_tenant()`. That helper already finds an existing child with `meta.broadcast_source_job_id` and refreshes it. The new task layer records per-target progress around that existing behavior rather than creating a second idempotence mechanism.

### Query current task status from Console

The Console will treat broadcast submit as "started" and show the task summary returned by `POST /cron/jobs/{job_id}/broadcast`. When a manager opens the broadcast modal later, the Console will call `GET /cron/jobs/{job_id}/broadcast/tasks/current` once to show whether the source Scheduled Job already has a running broadcast. It will not continuously poll.

### Enforce one running broadcast per source Scheduled Job

The task store will claim running work by source Scheduled Job identity: agent id, source id, current tenant id, and job id. While that claim is active, any new broadcast submission for the same source Scheduled Job returns the existing running task summary, regardless of the newly selected target tenant set.

## Risks / Trade-offs

- API response shape changes -> Update Console API types and targeted tests in the same change.
- Background task lost after process crash -> Persisted state remains visible; the first version does not auto-resume incomplete tasks after restart.
- DB unavailable -> Memory fallback still prevents HTTP timeout but progress is process-local.
- Many per-target row updates can add write load -> Keep progress writes compact and bounded to selected tenants.
- External scheduler latency still exists -> Work is moved out of the request path and stays bounded by `CRON_BROADCAST_CONCURRENCY`.
