---
status: accepted
supersedes: 0051
---

# Discover Workspaces Before Import

`prepare` resolves and records service, tenant, source, Agent, and workspace
identities and locations, checks ownership boundaries and the target schema,
and does not semantically inventory conversation input files. `migrate`
skips SQL-published sources, scans each remaining source into bounded temporary
workspace records, and gives those records to the existing importer. It then
verifies the target and publishes each valid source independently.

The workflow does not record or compare `chats.json` modification times and
does not calculate source input or manifest binding digests. Operators keep
unpublished conversation inputs, identity configuration, and manifest mappings
unchanged from prepare until source publication. SQL tickets and bundle state
continue to support recovery from interrupted writes.

The jobs table stores a small `manifest-v1` source-binding marker. The complete
mapping is kept in the manifest and a copy is installed beside each service's
runtime reference. Runtime uses the existing scope manifest path to locate the
copy; SQL remains the authority for source publication state. Deployments
continue to guarantee one migration process per application schema.
