## Context

Scheduled job notifications are Monitor-backed. SWE records each execution with `notification_status` and `notification_due_at`; Monitor workers claim only successful pending rows whose due time has arrived. Today normal automatic agent jobs become due at `end_time` or `actual_time`, while broadcast child jobs with `broadcast_notification_policy = "original_schedule"` become due at `actual_time + broadcast_offset_minutes`. Manual runs already bypass broadcast notification delay.

The new delay is a job-level preference, not an execution-store concern. The execution row still needs a concrete `notification_due_at` so Monitor claim logic can stay unchanged.

## Goals / Non-Goals

**Goals:**

- Let a scheduled job delay automatic success notifications by a user-configured duration.
- Support the delay from CLI creation, Console Cron Jobs create/edit, and the quick scheduled-task creation popup.
- Store one canonical value in minutes while allowing the UI to collect either minutes or hours.
- Preserve current broadcast behavior by adding the new delay on top of `broadcast_offset_minutes`.
- Keep old jobs compatible by treating missing or invalid delay metadata as `0`.

**Non-Goals:**

- No Monitor table migration or new execution column.
- No target-tenant-specific notification delay during broadcast.
- No delay for manual one-off runs.
- No change to which jobs enter the notification queue; only successful agent jobs are notified.

## Decisions

### Store the delay in `CronJobSpec.meta.notification_delay_minutes`

The field lives beside existing cron extension metadata such as `broadcast_offset_minutes` and `broadcast_notification_policy`. This avoids a schema migration and lets JSON-file creation keep working without API-model changes. The alternative was adding a top-level `CronJobSpec` field, but that would spread validation and type changes across more API surfaces for a setting that is still an execution behavior extension.

### Normalize at the execution boundary

`CronManager._sync_execution_to_monitor()` will read the job metadata, clamp or default invalid values to `0`, and compute the concrete due time before calling `MonitorSyncClient.record_execution()`. This keeps `MonitorSyncClient` and Monitor claim predicates focused on concrete execution records rather than job configuration.

### Use minutes as the API/CLI storage unit

The CLI flag and stored metadata use minutes. UI forms expose a numeric value plus a minute/hour unit and convert to minutes on submit. Edit forms reverse the conversion for readability, preferring hours when the stored value is divisible by 60.

### Broadcast child jobs inherit the source job delay

The existing broadcast job builder copies source metadata before replacing volatile task and broadcast fields. The new notification delay remains in metadata and therefore travels to child jobs. Automatic child executions compute `broadcast_offset_minutes + notification_delay_minutes`; manual child runs still bypass both delays.

## Risks / Trade-offs

- **Risk: Invalid historical metadata values** -> normalize non-numeric, negative, or missing values to `0` when calculating due time.
- **Risk: Extremely large delays leave rows pending too long** -> cap normalized delay at seven days.
- **Risk: UI unit conversion causes surprising values** -> store only minutes and derive the display unit deterministically on edit.
- **Risk: CLI update behavior ambiguity** -> this change only requires `swe cron create`; update can still be done through JSON or UI edit unless explicitly extended later.

## Migration Plan

No data migration is required. Existing jobs have no `notification_delay_minutes` metadata and therefore behave as delay `0`. Rollback is safe because jobs with this metadata remain valid extra metadata; older code will ignore it.

## Open Questions

None. The user confirmed delay stacking, manual-run bypass, broadcast inheritance, default `0`, and minute/hour UI input.
