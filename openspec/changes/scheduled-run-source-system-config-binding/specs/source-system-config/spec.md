## ADDED Requirements

### Requirement: Scheduled Run Boundaries SHALL bind effective source system configuration at execution time
The system SHALL resolve and bind the latest effective Source System Configuration whenever work enters a Scheduled Run Boundary. A Scheduled Run Boundary includes scheduled job execution, heartbeat execution, and dream execution, and excludes `/cron` management API requests.

#### Scenario: Scheduled job binds latest config from explicit source
- **WHEN** a scheduled job starts with explicit `source_id=portal`
- **THEN** the runtime SHALL resolve the effective Source System Configuration for `portal` at run start
- **AND** it SHALL bind that config for the whole scheduled-run business execution segment
- **AND** downstream runtime code SHALL be able to read it through the runtime context helper

#### Scenario: Scheduled work falls back to runtime scope identity
- **WHEN** heartbeat, dream, or job execution starts without explicit `source_id` but with a runtime `scope_id` that decodes to `source_id=portal`
- **THEN** the Scheduled Run Boundary SHALL recover `source_id=portal` from that runtime scope
- **AND** it SHALL resolve and bind the effective Source System Configuration for `portal`

#### Scenario: Cron management API is not a Scheduled Run Boundary
- **WHEN** a `/cron` management API request is handled through the normal HTTP request path
- **THEN** it SHALL remain a request-scoped middleware flow
- **AND** the system SHALL NOT treat that API handler itself as a Scheduled Run Boundary

### Requirement: Scheduled Run source config binding SHALL preserve explicit failure and legacy passthrough semantics
The system SHALL keep legacy source-less scheduled work running without Source System Configuration binding, but it SHALL NOT silently bypass sourced configuration failures once both source identity and the source config service are available.

#### Scenario: Legacy scheduled work has no source
- **WHEN** scheduled work starts without explicit `source_id` and without a decodable runtime `scope_id`
- **THEN** the runtime SHALL continue the scheduled work without binding Source System Configuration
- **AND** it SHALL preserve prior unbound behavior for that legacy run

#### Scenario: Runtime has no source config service
- **WHEN** scheduled work has a source identity but the runtime has no `SourceSystemConfigService`
- **THEN** the runtime SHALL continue the scheduled work without binding Source System Configuration

#### Scenario: Sourced scheduled work encounters unavailable config
- **WHEN** scheduled work has a source identity and `SourceSystemConfigService.resolve_config()` reports configuration unavailable for that source
- **THEN** the Scheduled Run Boundary SHALL fail the run instead of silently continuing without source-scoped controls

#### Scenario: Sourced scheduled work encounters invalid config
- **WHEN** scheduled work has a source identity and `SourceSystemConfigService.resolve_config()` reports invalid configuration data for that source
- **THEN** the Scheduled Run Boundary SHALL fail the run instead of silently continuing without source-scoped controls
