## Approved implementation graph

- [x] 1. Complete ticket 01: performance observation and baseline.
- [x] 2. Complete ticket 02: message batch inserts and committed verification.
- [x] 3. Complete ticket 03: message ticket batch allocation and recovery.
- [x] 4. Complete ticket 04 after 03: extend identity allocation.
- [x] 5. Complete ticket 05 implementation: bounded association locks.
  - [ ] Validate real MySQL execution plans, existing/missing row locks, concurrent conflicts and rollback in ticket 10.
  - [ ] Validate source isolation, complete results, resume and independent publication through the migration entry point in ticket 10.
- [x] 6. Complete ticket 06: safe bundle multiblock reads.
- [x] 7. Complete ticket 07: registration and selection work.
- [x] 8. Complete ticket 08: retry ticket ownership analysis.
- [ ] 9. Complete ticket 09: binding and manifest work.
- [ ] 10. Complete ticket 10 after 01–09: integrated acceptance and operations.
- [ ] 11. Complete independent review, fixes and final requirement audit.

Integration review on 2026-11-16: tickets 04, 05 and 07 merged in that order;
combined focused tests passed (181), followed by all conversation-storage unit
tests (1692). Real MySQL lock acceptance remains open: the new ticket-05
integration test calls `transaction()` on `DatabaseSession` at lines 85 and 100,
but the transaction context belongs to `DatabaseConnection`; a fresh implementer
must correct the test and obtain real lock evidence before acceptance. Mixed-source
and fault acceptance remains part of ticket 10.

Ticket 08 independent review on 2026-11-16 found no substantive blocker: the
disk ownership proof is limited to the original task's read-only retention phase,
uses the aggregate index budget, preserves legacy and orphan checks, and is
discarded before the final transactional SQL authority recheck. After merge,
retry/index/legacy/source-isolation focused tests passed (47). The MySQL fixture
transaction correction was independently reviewed and merged; real lock acceptance
remains pending the centralized database rerun.
