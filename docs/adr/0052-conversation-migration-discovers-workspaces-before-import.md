---
status: accepted
supersedes: 0051
---

# Discover Workspaces Before Import

`prepare` resolves and records service, tenant, source, Agent, and workspace
identities and locations, checks the target schema, and does not semantically
inventory conversation input files. Deployments guarantee source workspace and
configuration paths do not overlap. `migrate`
skips SQL-published sources, scans each remaining source into bounded temporary
workspace records, and gives those records to the existing importer. It then
verifies the target and publishes each valid source independently.

The workflow does not record or compare `chats.json` modification times and
does not calculate source input or manifest binding digests. Operators keep
unpublished conversation inputs, identity configuration, and manifest mappings
unchanged from prepare until source publication. SQL tickets and bundle state
continue to support recovery from interrupted writes.

The jobs table stores a small `manifest-v1` source-binding marker. The complete
mapping remains in the operator's manifest for migration and recovery. Runtime
selects the service's unique tenant migration job from SQL and reads only the
requested source's publication proof. It does not load the operator manifest or
scan workspace boundaries; deployments guarantee source workspace and
configuration paths do not overlap, and one migration process per application
schema runs at a time.
