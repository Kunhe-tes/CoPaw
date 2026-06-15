## 1. Cron Backend

- [x] 1.1 Add regression tests for child lookup empty/list responses.
- [x] 1.2 Add regression tests for batch child delete and batch child rerun skip behavior.
- [x] 1.3 Add regression tests for rebroadcast overwriting task definition while preserving target identity and enabled state.
- [x] 1.4 Implement cron child lookup, batch delete, batch rerun, and existing-child refresh APIs.

## 2. Cron Console

- [x] 2.1 Add Cron API types and client methods for child lookup and batch operations.
- [x] 2.2 Add a Cron Jobs menu action that opens a distributed-child management modal for every job.
- [x] 2.3 Implement empty state, selectable child table, batch delete, and batch rerun result display.
- [x] 2.4 Add focused Vitest coverage for API helpers or UI actions where existing test infrastructure supports it.

## 3. Market Skill Owner Lookup

- [x] 3.1 Add name-based owner lookup helpers that combine source tenants with user skill lists.
- [x] 3.2 Add a skill management action in the application market card/detail flows.
- [x] 3.3 Implement the owner lookup modal with user identity, market version, installed version, and update status.
- [x] 3.4 Add focused Vitest coverage for the matching helper.

## 4. Documentation And Verification

- [x] 4.1 Update wiki or module docs for cron distribution management and market skill name lookup.
- [x] 4.2 Run targeted Python tests.
- [x] 4.3 Run targeted frontend tests.
- [x] 4.4 Run OpenSpec validation for `add-distribution-ownership-management`.
- [x] 4.5 Run final diff checks and update tasks as completed.
