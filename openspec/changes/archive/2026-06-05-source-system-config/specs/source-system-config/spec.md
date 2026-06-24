## ADDED Requirements

### Requirement: Source system config SHALL be stored per source
The system SHALL persist system configuration by `source_id` as the only source-level dimension. The system MUST NOT require or evaluate `bbk_id`, tenant, user, or organization overrides when resolving source system configuration.

#### Scenario: Source config exists
- **WHEN** a request or service resolves system configuration for `source_id=portal`
- **THEN** the system SHALL load the configuration record whose source ID is `portal`
- **AND** it SHALL NOT inspect `bbk_id`, tenant ID, user ID, or organization ID for additional overrides

#### Scenario: Source config does not exist
- **WHEN** a request or service resolves system configuration for a valid source that has no stored config record
- **THEN** the system SHALL return the built-in default source system configuration
- **AND** existing backend and Console behavior SHALL remain unchanged

### Requirement: Source config SHALL be a generic JSON object
The system SHALL store source system configuration as a generic JSON object. The system MUST NOT require a built-in list of feature keys or enforce feature behavior in this change.

#### Scenario: Arbitrary object config is submitted
- **WHEN** an authorized manager submits a JSON object for `source_id=portal`
- **THEN** the system SHALL persist that object as the source system configuration
- **AND** it SHALL NOT reject keys solely because they are not in a built-in feature registry

#### Scenario: Non-object config is submitted
- **WHEN** an authorized manager submits a source config that is not a JSON object
- **THEN** the system SHALL reject the request
- **AND** it SHALL NOT modify the stored configuration

### Requirement: Source config SHALL be queryable during requests
The system SHALL bind effective source system configuration to the current request after source identity is resolved.

#### Scenario: Tenant request enters with source identity
- **WHEN** a request enters with `X-Source-Id=portal`
- **THEN** middleware SHALL resolve the effective configuration for `source_id=portal`
- **AND** downstream code SHALL be able to read it from `request.state.source_system_config`
- **AND** downstream code SHALL be able to read it through the runtime context helper

### Requirement: Console SHALL consume effective source config
The Console SHALL be able to load effective source system configuration from the backend for the active `source_id`.

#### Scenario: Console starts with a source
- **WHEN** Console initializes with an active source ID
- **THEN** it SHALL request the effective source system configuration from the backend
- **AND** it SHALL store that response for pages that need source system configuration

#### Scenario: Console source changes
- **WHEN** the active source ID changes during a Console session
- **THEN** Console SHALL refresh the effective source system configuration
- **AND** it SHALL ignore stale responses from the previous source

### Requirement: Source config management SHALL be restricted and auditable
The system SHALL expose management APIs for reading, creating, updating, deleting, and listing source system configuration, and those APIs MUST require manager-level authorization consistent with existing administrative routes.

#### Scenario: Manager updates source config
- **WHEN** an authorized manager updates the configuration for a source
- **THEN** the system SHALL validate that the config is a JSON object
- **AND** it SHALL persist the new config with an incremented version and audit metadata

#### Scenario: Manager deletes source config
- **WHEN** an authorized manager deletes the configuration for a source
- **THEN** the system SHALL remove the stored source config record
- **AND** subsequent effective reads for that source SHALL return the built-in default config

#### Scenario: Non-manager attempts update
- **WHEN** a non-manager attempts to create or update source system configuration
- **THEN** the system SHALL reject the request
- **AND** it SHALL NOT modify the stored configuration

### Requirement: Source config SHALL not mutate tenant runtime config
The system SHALL keep source system configuration separate from tenant runtime `config.json`. Resolving or updating source system configuration MUST NOT write source policy into tenant-local configuration files.

#### Scenario: Source config is updated
- **WHEN** a manager updates source system configuration for `source_id=portal`
- **THEN** the system SHALL update the source system config store
- **AND** it SHALL NOT write the source system config into any tenant `config.json`

#### Scenario: Tenant runtime config is loaded
- **WHEN** runtime code loads tenant-local agent, MCP, tool, provider, or hook configuration
- **THEN** it SHALL continue loading tenant runtime config from the existing tenant or scope path
- **AND** source system config SHALL remain a separate request-level context

### Requirement: Source config cache SHALL preserve correctness during failures
The system SHALL cache source system configuration per source while preserving clear behavior for missing config, invalid config, and storage failures.

#### Scenario: Config record is missing
- **WHEN** the source config store has no record for a valid source
- **THEN** the system SHALL use the built-in default config
- **AND** it SHALL treat that result differently from a storage read failure

#### Scenario: Storage fails after config was cached
- **WHEN** the source config store cannot be read and a last known good config exists for the source
- **THEN** the system SHALL use the last known good config
- **AND** it SHALL record the storage failure for observability

#### Scenario: Storage fails without cached config
- **WHEN** the source config store cannot be read and no last known good config exists for the source
- **THEN** the effective config API SHALL return an error instead of silently returning default config
