# 05: Accept Fast Verification Performance and Failure Semantics

Status: open
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

- [ ] Run fast and full verification against the same frozen fixture and isolated MySQL schema with matching worker, I/O, and memory budgets.
- [x] Instrument comparable workflow wall time, stage time, SQL statement/query work, bundle opens/index parses, and bundle bytes read; benchmark output keeps wall time separate from cumulative stage/I/O durations.
- [ ] Verify that one source-level fast-verification failure does not prevent healthy sibling sources from importing and publishing, and that retry preserves already published sources.
- [ ] Verify that database identity or named-lock loss, unknown commit outcome, cancellation with undrained I/O, and shared I/O failure still stop the whole migration safely.
- [x] Update operator guidance to explain the fast verification guarantee, its inability to prove body equality, and how to invoke the optional full audit.
- [x] Report local-directory, isolated-MySQL, and real-NAS evidence separately; do not claim a production or fixed percentage speedup without matching measurements.

## Current Evidence

The representative workflow test now measures prepare, import, fast verify, full verify, migrate, and retry under one isolated-MySQL fixture with the same resource flags. It reports stage wall time and operation counters including actual bundle bytes read. A source-level fast-verification failure-and-retry case and a same-input fast-versus-full body-mismatch case are also encoded in the integration tests. They were collected locally but skipped because `conversation target database not configured; not acceptance evidence`. No isolated-MySQL timings or real-NAS byte/I/O results are available, so this ticket remains open. The fast unit test confirms that verification reads bundle structure and the import plan while reading fewer bytes than the complete bundle body.

## Comments

2026-11-16: Approved ticket breakdown from the fast-verification spec. Parent issue 01 is retained unchanged.
