# Conversation Migration Fast Verification

Status: resolved
Type: task
Triage: ready-for-agent
Date: 2026-11-16

## Problem Statement

The current `migrate --apply` workflow performs full post-import semantic verification before it can publish a migrated source. That verification rereads stored conversation bodies and compares them with the frozen input, then exercises runtime read paths. In the measured representative MySQL workflow, verification took about 87 seconds while import took about 33 seconds. The migration needs a faster default release check while retaining explicit evidence that persisted metadata and NAS bundle structure are usable.

Historical share records are outside this migration's enabled data set. They must not cause discovery, import, verification, or publication work for this migration.

## Solution

Keep the established `prepare -> migrate --apply` operator workflow. After import, `migrate --apply` performs bounded, concurrent fast verification of committed database metadata, ownership, publication locators, and NAS bundle structure. It does not read every stored body or compare every body with the frozen source. Source freshness checks and source-isolated publication gates remain mandatory.

Full body-level semantic verification remains available as an explicit audit operation. Its result is distinct from fast verification and is not a prerequisite for routine source publication. Reports and durable verification evidence identify which level passed.

## User Stories

1. As a migration operator, I want `migrate --apply` to run fast verification by default, so that a source can be published without a full second read of every conversation body.
2. As a migration operator, I want the existing `prepare -> migrate --apply` workflow to remain intact, so that reducing verification cost does not add another required migration stage.
3. As a migration operator, I want fast verification to check the migration, target schema, NAS roots, frozen source boundary, and workspace mapping bindings, so that evidence from another job or target cannot authorize publication.
4. As a migration operator, I want fast verification to confirm that every expected committed publication exists, so that missing database publication records fail the affected source before release.
5. As a migration operator, I want fast verification to confirm that publication ownership matches the expected service, tenant, source, and Agent scope, so that cross-source or cross-tenant records cannot pass validation.
6. As a migration operator, I want fast verification to compare expected record counts and structural metadata with the import plan, so that missing or duplicated metadata is detected without reading each body.
7. As a migration operator, I want every required NAS bundle to be opened and its header, length, index, operation identity, and required block set checked, so that missing, truncated, malformed, or misidentified bundle files are detected.
8. As a migration operator, I want database body locators checked against the expected publication and indexed block extents, so that invalid offsets, lengths, and cross-publication references do not pass.
9. As a migration operator, I want fast verification to reuse import-commit evidence when it proves the same invariant, so that the workflow does not repeat equivalent database and bundle checks unnecessarily.
10. As a migration operator, I want fast verification to batch database reads within bounded query and memory limits, so that many sessions and chats do not cause avoidable serial round trips.
11. As a migration operator, I want independent bundle checks to use the existing bounded I/O workers and shared resource budgets, so that faster verification does not create unbounded disk or memory pressure.
12. As a migration operator, I want each unique bundle path inspected at most once per fast-verification run, so that duplicate publications or references do not trigger repeated index reads.
13. As a migration operator, I want full body-level semantic verification to remain explicitly runnable for audits, so that operators can still compare persisted message and archive content with frozen input when needed.
14. As a migration operator, I want the report and durable source state to record whether fast or full verification passed, so that fast structural validation is not represented as a full semantic audit.
15. As a migration operator, I want verification failures to remain isolated to the affected source, so that unrelated healthy sources can complete import and independent publication.
16. As a migration operator, I want the final frozen-source freshness check to remain in force, so that a source changed during migration cannot be published merely because its stored structure looks valid.
17. As a migration operator, I want historical share records excluded from discovery, inventory, import, verification, and publication work, so that a feature that was not enabled does not add unrelated reads or block conversation migration.
18. As a migration operator, I want reports to state that fast verification does not prove body bytes equal the source, so that I can understand the integrity guarantee before enabling runtime traffic.
19. As a migration operator, I want database identity loss, named-lock loss, unknown commit outcomes, and shared I/O failures to remain globally fatal, so that fast verification never weakens shared migration safety.
20. As a migration operator, I want performance evidence to report stage time, query work, unique bundle opens, and bytes read, so that the speedup is demonstrated rather than inferred from fewer checks in code.

## Implementation Decisions

- Use the existing top-level tenant migration workflow as the primary seam. Exercise `migrate --apply` end to end and preserve source-level failure isolation and independent publication.
- Fast verification is the default after import for `migrate --apply` and publication-producing migration operations. It runs before final source freshness checking and publication.
- The existing explicit verification command defaults to fast verification. An explicit full-audit option invokes the current complete body-level semantic checks. Full audit is not required to publish a source.
- Fast verification checks frozen job bindings, expected committed publication rows, source ownership, required SQL metadata counts and identities, bundle file identity/length, index integrity, required block identities, and locator-to-block containment.
- Fast verification does not read all message, archive, checkpoint, recovery, or artifact body bytes for source-equality comparison. It does not claim to detect validly structured but incorrect body bytes. No body checksums or new integrity format are introduced by this change.
- Import-time publication preparation, durable bundle confirmation, import-plan comparison, per-operation SQL verification, transaction semantics, and recovery evidence remain unchanged. Fast verification may reuse their immutable evidence only when the existing job identity and commit protocol prove that evidence is still applicable.
- Group SQL evidence by source/workspace and use bounded batches. Keep the single SQL owner, named lock, source scoping, cancellation behavior, and unknown-commit handling. Do not add concurrent database sessions.
- Deduplicate bundle inspection by validated relative path for the duration of one fast-verification run. Run independent filesystem inspections through the existing shared I/O scheduler and memory/resource budgets.
- Record a verification level such as `fast` or `full` in source verification evidence and operator reports. A source becomes publication-eligible only after fast verification and the unchanged final source check succeed. Full audit results are recorded separately and cannot be inferred from the fast result.
- Historical legacy share records are excluded from this migration input and all subsequent migration stages. This decision does not change runtime Permanent Share Link behavior or storage contracts outside this migration scope.
- Preserve the two primary operator actions and existing migration identity. Do not add a required stage, bypass source ownership checks, weaken source freshness, change bundle format, or change publication ordering.
- Continue to mark a failed source as failed and allow unrelated sources to proceed. Shared infrastructure failures continue to stop the whole run.

## Testing Decisions

- Prefer behavior tests through the existing migration CLI/orchestration seam. Tests should assert published source state, failure isolation, verification-level reporting, and runtime-visible metadata rather than private helper call order.
- Reuse tenant workflow MySQL integration fixtures for `prepare -> migrate --apply`, source-level failure/retry, and independent publication. Run the workflow against an isolated MySQL schema.
- Reuse bundle filesystem tests for missing files, truncated files, malformed indexes, identity mismatch, extent overflow, symlinks, special files, and replacement races.
- Reuse commit and retry tests for durable publication confirmation, import-plan evidence, unknown commit handling, and re-entry after interruption.
- Add fast-verification behavior cases for missing expected rows, wrong source ownership, incorrect locator, missing required block, invalid bundle length, and validly structured bodies that are deliberately not read in fast mode.
- Add scope tests proving historical share records do not enter migration inventories or cause share queries, bundle reads, or source publication dependencies.
- Add source isolation cases proving one fast-verification failure does not prevent healthy sibling sources from publishing, while lock loss and shared I/O failure still stop the run globally.
- Compare fast and full verification on the same frozen fixture and isolated database. Assert full audit detects body-content mismatch that fast verification intentionally does not claim to detect.
- Measure wall time, query/statement work, unique bundle opens, index parses, and actual NAS bytes read at the workflow seam. Report local-directory and real-NAS results separately; a local fixture is not evidence of production NAS performance.
- Prior art includes the existing tenant workflow MySQL integration tests, offline commit/verify stage tests, source freshness boundary tests, bundle safety tests, and migration resource-budget tests.

## Out of Scope

- Changing the `prepare -> migrate --apply` operator workflow or introducing another required migration stage.
- Verifying or migrating historical share records that are outside the enabled feature set.
- Proving that every persisted body byte exactly matches the frozen source during the default fast path.
- Adding content checksums, changing bundle format, or claiming detection of arbitrary same-length silent NAS corruption.
- Weakening writer shutdown, immutable source capture, final source freshness checks, database lock/identity validation, commit recovery, per-source failure isolation, or publication ordering.
- Adding multiple database owners or database connections for concurrent verification.
- Changing runtime Permanent Share Link behavior, conversation storage APIs, or production schema.
- Claiming production NAS, large-scale, or fixed percentage performance results without corresponding measurements.

## Further Notes

- The measured performance acceptance found full verification to be the largest remaining stage in its representative fixture. That fixture used three sources and three workspaces with a remote isolated MySQL instance and local input directories; it is not a real NAS or large-scale benchmark.
- The current bundle format does not provide a payload checksum. Fast verification can validate file and index structure and database locator consistency, but not body equality or arbitrary silent payload corruption.
- Existing conversation storage decisions keep content on NAS, metadata in MySQL, durable NAS publication before MySQL commit, and source-independent publication. This spec narrows migration verification cost without changing those decisions.
- Primary testing seam: existing `migrate --apply` workflow; explicit full audit is tested through the existing `verify` CLI operation. No new migration entry point is required.
