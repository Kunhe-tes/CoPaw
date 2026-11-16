---
status: accepted
---

# Conversation Migration Uses Fast Structural Verification

On 2026-11-16 the user selected fast structural verification as the default
pre-publication gate for the existing `prepare -> migrate --apply` workflow.
The gate validates migration and target bindings, committed publication
metadata and ownership, required database record identities/counts, bundle
identity/length/index/block structure, locator containment, and the unchanged
frozen-source freshness boundary. It uses bounded batches and the existing
single SQL owner and shared I/O budgets. Source-level failures remain isolated;
loss of database identity or lock, unknown commit outcome, and shared I/O
failure remain globally fatal.

For verification, this decision supersedes the requirement in ADR 0045 to run
full post-import body-level semantic comparison before routine source
publication.
Import-time commit validation, durable NAS-before-MySQL publication,
writer shutdown, immutable source capture, final source freshness checking,
source-isolated publication, backups, and rollback guarantees remain in force.

Fast verification does not read every persisted body or prove exact equality
between body bytes and the frozen source. The current bundle format has no
content checksum, so structurally valid but incorrect or silently corrupted
body bytes may not be detected by the fast gate. Adding a checksum or changing
the bundle format is not part of this decision. Full semantic comparison
remains available as an explicit audit and its result is reported separately;
it is not a routine publication prerequisite.

The migration will not discover, import, verify, or publish historical share
records because the legacy share feature was not enabled for the data being
migrated. This is an explicit exception to the share-preservation statements in
ADRs 0045 and 0049. The migration does not delete or rewrite such records, and
this decision does not change runtime Permanent Share Link behavior. If
historical share data is found in an environment that is expected to have none,
it remains outside this migration's result and requires a separate operator
decision before that environment can claim share-history continuity.

The selected verification seam is the existing migration CLI workflow. No
additional required migration phase, concurrent database owner, production
schema change, or public conversation API change is introduced.
