## Why

Migration still performs per-message ticket transactions, business inserts and retry reads, repeated association locks and bundle index reads. A few hundred users took over 40 minutes in the reported environment; the complete field cause remains unproven. Reduce measured amplification without weakening recovery or source publication.

## What Changes

- Implement the ten approved local tracker tickets for bounded SQL batches, association locks, bundle reads, repeated job work, diagnostics and integrated acceptance.
- Preserve prepare/migrate commands, source failure isolation, single SQL owner, durable identity contracts and existing formats.

## Capabilities

### New Capabilities
- `conversation-migration-performance`: bounded processing with measurable round-trip reduction and unchanged correctness.

### Modified Capabilities
None; existing publication, admission and compatibility requirements remain unchanged.

## Impact

Offline migration orchestration, SQL journal and record installation, immutable bundle readers, progress diagnostics and their existing tests. No schema or public API changes.
