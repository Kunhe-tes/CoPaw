## Why

Cron scheduled-job broadcast currently waits for all target tenants to finish inside one HTTP request. When a manager broadcasts to many users, external scheduler registration and tenant bootstrap can exceed API timeouts even though the work can safely continue in the background.

## What Changes

- Change scheduled-job broadcast from a synchronous all-results response to an asynchronous task response.
- Persist broadcast task progress and per-target results so managers can refresh the page and still inspect the outcome.
- Keep broadcast child creation idempotent: rebroadcasting to a tenant with an existing child job refreshes that child instead of creating a duplicate.
- Add APIs for querying the current running broadcast task and, when needed, a task status by id.
- Update the Console Cron Jobs broadcast modal to show the current running task when the modal opens instead of continuously polling.

## Capabilities

### New Capabilities
- `async-cron-broadcast`: Scheduled-job broadcast requests start quickly, continue in the background, and expose durable per-target progress.

### Modified Capabilities
- None.

## Impact

- Backend cron broadcast API in `src/swe/app/crons/api.py`.
- New or extended cron broadcast task storage under `src/swe/app/crons/`.
- App startup store initialization in `src/swe/app/_app.py`.
- Console Cron Jobs API types and calls under `console/src/api`.
- Console Cron Jobs broadcast modal in `console/src/pages/Control/CronJobs/index.tsx`.
- Targeted Python and Vitest coverage for async start, current running task lookup, source-job-level mutual exclusion, and idempotent existing-child refresh.
