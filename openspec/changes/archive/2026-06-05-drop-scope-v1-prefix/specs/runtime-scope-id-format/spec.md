## ADDED Requirements

### Requirement: Runtime scope identifiers SHALL use the canonical unprefixed format
The system SHALL represent every source-scoped runtime identity with the
canonical format `<base64url(tenant_id)>.<base64url(source_id)>`. This
canonical format SHALL be the only format emitted by scope-encoding helpers
and the only format used for new local directories, transient keys, and
standard runtime logging.

#### Scenario: Encoding a source-scoped runtime identity
- **WHEN** the system encodes a `tenant_id` and `source_id` pair into a
  runtime scope identifier
- **THEN** it SHALL return `<base64url(tenant_id)>.<base64url(source_id)>`
- **AND** it SHALL NOT prepend `scope.v1.` or any other version marker

#### Scenario: Creating new scoped local state
- **WHEN** a scoped workspace, provider directory, or transient store entry is
  created for a runtime scope
- **THEN** the created directory name or key SHALL use the canonical unprefixed
  scope format
- **AND** the system SHALL NOT create a new `scope.v1.*` name

### Requirement: Scope parsing SHALL canonicalize legacy prefixed input
The system SHALL continue to accept legacy `scope.v1.<tenant_b64>.<source_b64>`
scope input during the cutover period, but it SHALL canonicalize that input to
the unprefixed format before downstream runtime code uses it.

#### Scenario: Request or task provides a legacy prefixed scope
- **WHEN** a request context, background task, callback payload, or internal
  control path provides `scope.v1.<tenant_b64>.<source_b64>`
- **THEN** the system SHALL decode it successfully
- **AND** downstream runtime helpers SHALL observe the canonical unprefixed
  scope identifier

#### Scenario: Request or task provides a canonical unprefixed scope
- **WHEN** a request context, background task, callback payload, or internal
  control path provides `<tenant_b64>.<source_b64>`
- **THEN** the system SHALL decode it successfully
- **AND** the canonical runtime identifier SHALL remain unchanged

### Requirement: Scoped path resolution SHALL migrate old local directories to canonical names
Whenever scoped local state is resolved, the system SHALL prefer canonical
unprefixed directory names. If a canonical target directory does not exist but
the corresponding legacy `scope.v1.*` directory exists, the system SHALL
migrate that local state to the canonical directory before continuing.

#### Scenario: Canonical directory missing but legacy directory exists
- **WHEN** scoped path resolution targets `<tenant_b64>.<source_b64>`
- **AND** `~/.swe/<tenant_b64>.<source_b64>` does not exist
- **AND** `~/.swe/scope.v1.<tenant_b64>.<source_b64>` exists
- **THEN** the system SHALL migrate the legacy directory to the canonical name
- **AND** subsequent path resolution SHALL use the canonical directory

#### Scenario: Canonical provider directory missing but legacy provider directory exists
- **WHEN** provider storage resolution targets
  `~/.swe.secret/<tenant_b64>.<source_b64>/providers`
- **AND** the canonical provider directory does not exist
- **AND** the legacy directory
  `~/.swe.secret/scope.v1.<tenant_b64>.<source_b64>/providers` exists
- **THEN** the system SHALL migrate the legacy provider storage to the
  canonical directory
- **AND** provider initialization SHALL continue against the canonical path

### Requirement: Scope-aware runtime stores SHALL use canonical scope keys
The system SHALL use the canonical unprefixed scope identifier as the
effective key for any process-wide registry, cache, approval state, progress
token, or session/chat-scoped transient store that isolates by runtime scope.

#### Scenario: Scope-aware transient state is written after cutover
- **WHEN** a scoped runtime writes approvals, suggestions, progress state, or
  other transient records
- **THEN** the persisted in-memory key SHALL use the canonical unprefixed scope
  identifier
- **AND** the system SHALL NOT emit new transient entries keyed by
  `scope.v1.*`

#### Scenario: Legacy-prefixed scope reaches a store boundary
- **WHEN** a legacy-prefixed scope identifier reaches a scope-aware registry or
  store boundary
- **THEN** the boundary SHALL canonicalize it before lookup or write
- **AND** the store SHALL behave as if the canonical unprefixed scope had been
  provided originally
