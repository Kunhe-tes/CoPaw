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
- [ ] Report comparable workflow wall time, stage time, SQL statement/query work, unique bundle opens/index parses, and NAS bytes read; distinguish cumulative concurrent time from wall time.
- [ ] Verify that one source-level fast-verification failure does not prevent healthy sibling sources from importing and publishing, and that retry preserves already published sources.
- [ ] Verify that database identity or named-lock loss, unknown commit outcome, cancellation with undrained I/O, and shared I/O failure still stop the whole migration safely.
- [ ] Update operator guidance to explain the fast verification guarantee, its inability to prove body equality, and how to invoke the optional full audit.
- [ ] Report local-directory, isolated-MySQL, and real-NAS evidence separately; do not claim a production or fixed percentage speedup without matching measurements.

## Comments

2026-11-16: Approved ticket breakdown from the fast-verification spec. Parent issue 01 is retained unchanged.
