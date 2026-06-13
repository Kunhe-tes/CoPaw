## 1. Backend Timing

- [x] 1.1 Add regression tests for normal automatic delay, manual delay bypass, broadcast stacked delay, and invalid delay defaults.
- [x] 1.2 Implement `notification_delay_minutes` normalization and automatic-run due-time calculation in the cron manager.
- [x] 1.3 Ensure broadcast child jobs inherit source job delay metadata.

## 2. CLI Support

- [x] 2.1 Add CLI payload tests for omitted and explicit `--notification-delay-minutes`.
- [x] 2.2 Add `--notification-delay-minutes` to `swe cron create` and inline payload construction.

## 3. Console Forms And Display

- [x] 3.1 Add helper tests for converting notification delay value/unit to stored minutes and back.
- [x] 3.2 Add quick scheduled-task popup tests for saving delay metadata.
- [x] 3.3 Add Cron Jobs list tests for delay display.
- [x] 3.4 Implement quick popup delay controls and payload propagation.
- [x] 3.5 Implement Cron Jobs drawer delay create/edit fields and list display column.

## 4. Verification

- [x] 4.1 Run targeted Python tests for cron manager timing and CLI payload behavior.
- [x] 4.2 Run targeted Vitest tests for cron helpers, scheduled task popup, and Cron Jobs display.
- [x] 4.3 Run OpenSpec validation for `add-cron-notification-delay`.
- [x] 4.4 Review final diff for scope and update tasks as completed.
