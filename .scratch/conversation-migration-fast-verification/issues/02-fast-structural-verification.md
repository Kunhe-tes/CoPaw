# 02: Default to Fast Structural Verification

Status: resolved
Type: task
Parent: 01 Make Fast Verification the Migration Default
Blocked by: None
Triage: ready-for-agent
Priority: P1

**What to build:** After import, the existing migration workflow can establish that committed metadata and NAS bundle structure are ready for source publication without rereading every conversation body. Verification results identify the fast level, and a failed source remains isolated from healthy sources.

**Blocked by:** None (can start immediately).

- [x] `migrate --apply` runs fast structural verification after import and before the unchanged final source freshness check and publication.
- [x] The explicit verification operation uses fast structural verification by default and records the verification level in its report and durable source evidence.
- [x] Fast verification checks migration/target/source bindings, committed publication existence and ownership, expected metadata identities/counts, and database locator association with the expected publication.
- [x] Every required unique bundle path is inspected once per run; bundle identity, byte length, index, required block identities, and locator-to-block containment are checked without reading all body bytes for source equality.
- [x] Database evidence is read in bounded batches under the existing single SQL owner; independent bundle inspections use the shared bounded I/O and memory budgets.
- [x] Import-time commit checks, source freshness checks, source-level failure isolation, named-lock and database identity checks, and global handling of unknown commits/shared I/O failures remain effective.
- [x] A structurally valid bundle with intentionally altered body bytes passes fast verification only when all fast invariants hold; the report does not claim full body equality.
- [x] Missing rows, incorrect scope ownership, invalid locators, missing/truncated bundles, malformed indexes, missing required blocks, and source mutation prevent the affected source from publication.

## Answer

Fast structural verification is now the default for direct migration verification and source-isolated `migrate --apply`. It checks committed publication identity and ownership, validates bundle/index and import-plan bindings, confirms required block locators, and compares expected typed database rows in bounded per-table batches. NAS body blocks are not read. Source verification level is reported and stored in source-state metadata without changing the authority receipt format. Import commit semantics, source recheck, source isolation, and global shared-failure behavior remain in place.

Validation: the complete migration/storage and relevant CLI unit suite passed (1778 passed). Fast-verification tests cover body-read avoidance, missing publication, wrong owner/path, missing required block, truncated bundle, batched 129-publication lookup, and expected SQL row identity. The source workflow MySQL integration fixture was collected but skipped because this environment has no configured migration test database.

## Comments

2026-11-16: Approved ticket breakdown from the fast-verification spec. Parent issue 01 is retained unchanged.
