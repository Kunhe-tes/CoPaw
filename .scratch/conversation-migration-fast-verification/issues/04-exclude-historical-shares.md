# 04: Exclude Historical Share Records from Migration

Status: open
Type: task
Parent: 01 Make Fast Verification the Migration Default
Blocked by: None
Triage: ready-for-agent
Priority: P1

**What to build:** Conversation migration proceeds without discovering, importing, verifying, or publishing historical share records because that feature was not enabled for the source data being migrated.

**Blocked by:** None (can start immediately).

- [ ] Discovery and preparation do not enumerate historical share records into migration evidence.
- [ ] Inventory, import, fast verification, and full audit do not issue share-specific migration reads or NAS body reads.
- [ ] Historical share records do not become a source or tenant publication prerequisite and do not prevent otherwise valid conversation sources from publishing.
- [ ] Migration reports make the excluded historical-share scope explicit without presenting those records as migrated or verified.
- [ ] Tests cover both the expected empty legacy-share population and unexpected historical rows, proving those rows do not enter the migration workflow.
- [ ] Runtime Permanent Share Link behavior and its storage contract remain unchanged.

## Comments

2026-11-16: Approved ticket breakdown from the fast-verification spec. Parent issue 01 is retained unchanged.
