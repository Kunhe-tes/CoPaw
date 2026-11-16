## Approved implementation graph

- [x] 1. Complete ticket 01: performance observation and baseline.
- [x] 2. Complete ticket 02: message batch inserts and committed verification.
- [x] 3. Complete ticket 03: message ticket batch allocation and recovery.
- [x] 4. Complete ticket 04 after 03: extend identity allocation.
- [x] 5. Complete ticket 05 implementation: bounded association locks.
  - [x] Validate real MySQL execution plans, existing/missing row locks, concurrent conflicts and rollback in ticket 10.
  - [x] Validate source isolation, complete results, resume and independent publication through the migration entry point in ticket 10.
- [x] 6. Complete ticket 06: safe bundle multiblock reads.
- [x] 7. Complete ticket 07: registration and selection work.
- [x] 8. Complete ticket 08: retry ticket ownership analysis.
- [x] 9. Complete ticket 09: binding and manifest work.
- [ ] 10. Complete ticket 10 after 01–09: integrated acceptance and operations.
- [ ] 11. Complete independent review, fixes and final requirement audit.

Integration review on 2026-11-16: tickets 04, 05 and 07 merged in that order;
combined focused tests passed (181), followed by all conversation-storage unit
tests (1692). Real MySQL lock acceptance passed after the fixture transaction correction: two cases completed in 13.38 s at `41075904a`/`52d590a6e`, proving existing-row and missing-ID conflicts while locked, then success after rollback. Same-tenant source CLI acceptance at `c5f52b4a1` passed (1 test, 35.47 s): healthy sibling publication/admission, bad source repair on the original manifest, and preservation of online sibling rows/config while its old session input is poisoned.

Ticket 08 independent review found no substantive blocker; after merge, retry/index/legacy/source-isolation focused tests passed (47). Ticket 09 measured persistence work and retained exact serialization/checkpoints under its explicit conservative fallback; its independent review passed 49 focused tests. Central real-MySQL fault acceptance at `52d590a6e` passed 3 cases in 108.24 s (SQL owner, KILL lock with IO drain/resume, lost driver COMMIT response). Final combined performance and independent review remain open under tickets 10/11.
