# 05: Accept Fast Verification Performance and Failure Semantics

Status: resolved
Type: task
Parent: 01 Make Fast Verification the Migration Default
Blocked by: 02 Default to Fast Structural Verification, 03 Keep Full Semantic Verification as an Explicit Audit, 04 Exclude Historical Share Records from Migration
Triage: ready-for-agent
Priority: P1

**What to build:** The fast verification workflow is demonstrated end to end to reduce measured work while preserving source publication, retry, and global failure guarantees; operators can distinguish measured local/MySQL results from unmeasured NAS performance.

**Blocked by:**
- 02 Default to Fast Structural Verification
- 03 Keep Full Semantic Verification as an Explicit Audit
- 04 Exclude Historical Share Records from Migration

- [x] Run fast and full verification against the same frozen fixture and isolated MySQL schema with matching worker, I/O, and memory budgets.
- [x] Instrument comparable workflow wall time, stage time, SQL statement/query work, bundle opens/index parses, and bundle bytes read; benchmark output keeps wall time separate from cumulative stage/I/O durations.
- [x] Verify that one source-level fast-verification failure does not prevent healthy sibling sources from importing and publishing, and that retry preserves already published sources.
- [x] Verify that database identity or named-lock loss, unknown commit outcome, cancellation with undrained I/O, and shared I/O failure still stop the whole migration safely.
- [x] Update operator guidance to explain the fast verification guarantee, its inability to prove body equality, and how to invoke the optional full audit.
- [x] Report local-directory, isolated-MySQL, and real-NAS evidence separately; do not claim a production or fixed percentage speedup without matching measurements.

## Current Evidence

The representative workflow was run with three sources, three workspaces, 128 messages, three workers, two I/O workers, and a 128 MiB memory budget against isolated remote MySQL and local directories. On the same frozen fixture, fast verification took 0.632 s of stage wall time (4.304 s command wall time), attempted 81 SQL statements, opened 7 bundles, and read 85,012 bundle bytes. Full audit took 86.585 s of stage wall time (90.589 s command wall time), attempted 1,827 statements, opened 8 bundles, and read 162,477 bundle bytes. These bundle byte counters count reads from migration bundles; they exclude source enumeration/reads and are not total NAS traffic. They describe this fixture only, not production NAS performance.

The complete performance workflow suite passed 4 tests in 282.50 s: healthy prepare/import/verify/migrate/re-entry, running-Turn failure followed by repair, source-level fast failure with healthy sibling publication and retry, and body mismatch distinction between fast and full verification. The changed source alone failed full audit. Related global failure barrier tests passed 84 unit tests, covering lock/identity loss, unknown commit outcomes, cancellation draining, and shared I/O failures. Temporary MySQL schemas were verified empty and dropped. No real-NAS fixture was available, so no NAS throughput or total-NAS-byte claim is made.

## Comments

2026-11-16: Approved ticket breakdown from the fast-verification spec. Parent issue 01 is retained unchanged.
