## ADDED Requirements

### Requirement: Bounded batch processing preserves migration authority
The system SHALL use bounded SQL and immutable-body operations while preserving source publication, single SQL ownership, existing identity and recovery contracts.

#### Scenario: Healthy source beside failed source
- **WHEN** one source has invalid input and another independent source is valid
- **THEN** the invalid source is recorded and skipped while the healthy source completes import, full verification, final source checks and publication

#### Scenario: Restart after partial commit
- **WHEN** the same migration resumes after an interrupted batch
- **THEN** real durable ticket identities are reconciled and already published source data is not reread or overwritten

### Requirement: Performance improvement is measured without weakened checks
The system SHALL report comparable SQL, transaction and IO work and validate all existing data and safety checks.

#### Scenario: Message count exceeds one batch
- **WHEN** messages exceed a bounded SQL block
- **THEN** inserts and ticket allocation use bounded blocks rather than per-message transactions while semantic results remain equivalent

#### Scenario: Multiple blocks in one bundle
- **WHEN** a bounded read requests multiple extents from one immutable bundle
- **THEN** it reuses one safe open and index parse while validating every extent and rejecting unsafe or changed input
