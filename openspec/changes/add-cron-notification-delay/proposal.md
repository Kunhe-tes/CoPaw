## Why

Scheduled job completion notifications currently fire as soon as an automatic run is complete, except broadcast jobs which delay notification back to the original schedule time. Users need a per-job way to delay those completion notifications, for example to notify two hours after the scheduled work completes.

## What Changes

- Add an optional scheduled-job notification delay stored as `meta.notification_delay_minutes`.
- Apply the delay only to automatic scheduled runs; manual one-off runs remain immediately claimable for notification.
- Preserve broadcast notification alignment by adding the new delay on top of the existing broadcast offset.
- Let `swe cron create` set the delay with an optional CLI flag that defaults to `0` when omitted.
- Let the Console scheduled-task creation and Cron Jobs create/edit screens configure the delay with user-entered values in minutes or hours.
- Show the configured delay in the Cron Jobs list.

## Capabilities

### New Capabilities

- `cron-notification-delay`: Scheduled jobs can define a completion-notification delay that is applied to automatic notification timing and inherited by broadcast child jobs.

### Modified Capabilities

None.

## Impact

- Backend cron execution timing in `src/swe/app/crons/manager.py`.
- Broadcast job metadata copy behavior in `src/swe/app/crons/api.py`.
- CLI payload construction in `src/swe/cli/cron_cmd.py`.
- Console cron forms and list display under `console/src/components/ScheduledTaskPopup` and `console/src/pages/Control/CronJobs`.
- Targeted Python and Vitest coverage for timing, CLI payloads, form persistence, and display.
