## 1. Backend Store And API

- [x] 1.1 Add tests for database-backed and memory-fallback broadcast task storage.
- [x] 1.2 Implement `CronBroadcastTaskStore` with task creation, running-claim reuse, per-target updates, completion, failure, and lookup.
- [x] 1.3 Initialize the broadcast task store at app startup.
- [x] 1.4 Add tests for async broadcast submission returning a task summary without waiting for all target processing.
- [x] 1.5 Add tests for broadcast task lookup with running, completed, and failed target results.
- [x] 1.6 Implement async broadcast route behavior, task lookup route, and current running task route.
- [x] 1.7 Add tests that repeated broadcast to an existing child refreshes the child and does not create duplicates.

## 2. Console Broadcast Flow

- [x] 2.1 Update Console cron API types and client methods for broadcast task start and current running task lookup.
- [x] 2.2 Add tests for Console broadcast helper behavior and modal progress text.
- [x] 2.3 Update the Cron Jobs broadcast modal to show started/running/completed/failed progress and current running status on open.
- [x] 2.4 Preserve existing offset controls, target selection, warnings, and final result messaging.

## 3. Verification And Review

- [x] 3.1 Run targeted Python tests for cron broadcast task store and cron API.
- [x] 3.2 Run targeted Vitest coverage for the Cron Jobs broadcast UI/API changes.
- [x] 3.3 Run OpenSpec validation/status checks for `add-async-cron-broadcast`.
- [x] 3.4 Run GitNexus `detect_changes` and final diff review.
