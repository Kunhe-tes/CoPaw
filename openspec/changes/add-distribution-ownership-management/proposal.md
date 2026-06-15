## Why

Managers need to audit and manage distributed assets after they are sent to users. Today cron broadcast can create child scheduled jobs, but the Cron Jobs page cannot reverse-check which users have child jobs, nor batch delete or rerun those child jobs. The application market also needs a manager action to check which users currently own a skill by skill name, including version status, without relying on distribution logs.

## What Changes

- Add source scheduled-job child lookup from the Cron Jobs menu.
- Add batch delete and batch rerun actions for selected broadcast child scheduled jobs.
- Change cron rebroadcast semantics so existing child jobs are updated instead of skipped, while preserving target identity, child job ID, task binding, and enabled/paused state.
- Add an application-market manager action per skill to look up owners by stable skill name.
- The skill owner lookup matches current user-side skills by name, not historical distribution records, and includes user-side and market version information.

## Capabilities

### New Capabilities

- `cron-distribution-management`: Managers can reverse-check, delete, and rerun distributed scheduled-job children.
- `market-skill-owner-lookup`: Managers can reverse-check which source users currently own a market skill by name.

### Modified Capabilities

- Cron broadcast to a target tenant with an existing child job now refreshes task-definition fields instead of returning a duplicate-skip warning.

## Impact

- Backend cron broadcast and management API in `src/swe/app/crons/api.py`.
- Console cron API types and calls under `console/src/api`.
- Console Cron Jobs page and action column under `console/src/pages/Control/CronJobs`.
- Console application market skill manager actions under `console/src/pages/Market`.
- Targeted Python and Vitest coverage for child lookup, batch actions, rebroadcast overwrite, and skill owner lookup.
