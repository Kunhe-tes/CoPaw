## ADDED Requirements

### Requirement: BBK writes SHALL store primary branch IDs
The system SHALL normalize BBK IDs to primary branch IDs before writing new
records to `swe_tracing_traces`, `swe_tracing_spans`, `swe_cron_jobs`, and
`swe_tenant_init_source`.

#### Scenario: Primary BBK ID is written unchanged
- **WHEN** a write path receives a known primary branch BBK ID
- **THEN** the persisted `bbk_id` SHALL equal the received primary branch BBK ID

#### Scenario: Secondary BBK ID is written as primary
- **WHEN** a write path receives a known secondary branch BBK ID
- **THEN** the persisted `bbk_id` SHALL equal the secondary branch's primary parent BBK ID
- **AND** the secondary branch BBK ID SHALL NOT be persisted in the target table

#### Scenario: Unknown BBK ID is preserved with warning
- **WHEN** a write path receives a BBK ID that is neither a known primary nor a known secondary branch
- **THEN** the persisted `bbk_id` SHALL keep the received value
- **AND** the system SHALL log a warning for follow-up data quality investigation

### Requirement: BBK display helpers SHALL resolve primary branch names
The SWE and Monitor Python BBK helpers SHALL expose primary branch name lookup
for stored primary branch IDs and SHALL provide a normalization helper for
callers that receive external secondary branch IDs.

#### Scenario: Primary name lookup
- **WHEN** a caller requests the branch name for a known primary BBK ID
- **THEN** the helper SHALL return the primary branch name

#### Scenario: Secondary ID compatibility
- **WHEN** a caller requests the branch name for a known secondary BBK ID
- **THEN** the helper MAY normalize it to the primary branch ID before resolving the name

### Requirement: Existing data and Console mapping are out of scope
This change SHALL NOT migrate historical database rows and SHALL NOT update the
Console TypeScript BBK mapping.

#### Scenario: Existing rows remain unchanged
- **WHEN** this change is deployed
- **THEN** existing rows in the target tables SHALL remain unchanged unless they are rewritten by a normal application write path
