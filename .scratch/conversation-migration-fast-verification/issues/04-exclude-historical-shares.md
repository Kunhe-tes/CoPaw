# 04: Exclude Historical Share Records from Migration

Status: resolved
Type: task
Parent: 01 Make Fast Verification the Migration Default
Blocked by: None
Triage: ready-for-agent
Priority: P1

**What to build:** Conversation migration proceeds without discovering, importing, verifying, or publishing historical share records because that feature was not enabled for the source data being migrated.

**Blocked by:** None (can start immediately).

- [x] Discovery and preparation do not enumerate historical share records into migration evidence.
- [x] Inventory, import, fast verification, and full audit do not issue share-specific migration reads or NAS body reads.
- [x] Historical share records do not become a source or tenant publication prerequisite and do not prevent otherwise valid conversation sources from publishing.
- [x] Migration reports make the excluded historical-share scope explicit without presenting those records as migrated or verified.
- [x] Tests cover the empty input contract, reject unexpected supplied history, and prove the verification path issues no share-table query.
- [x] Runtime Permanent Share Link behavior and its storage contract remain unchanged.

## Answer

New v3 manifests require empty `shares` and `source_shares`. Discover/prepare no longer connect to MySQL to read `swe_chat_shares`; a non-empty compatibility `--shares-file` is rejected. Tenant discovery, source publication comparison, direct pre/post-operation checks, and full semantic verification do not inspect share records. Reports identify `excluded_scopes: ["historical_shares"]`. Schema checks for the runtime share table remain; runtime share code is unchanged.

Validation: 131 focused tests passed across discovery/prepare, manifest validation, tenant/source orchestration, fast/full verification, and migration imports. The repository still has no configured isolated migration MySQL schema for running database-backed end-to-end migration tests.

## Comments

2026-11-16: Approved ticket breakdown from the fast-verification spec. Parent issue 01 is retained unchanged.
