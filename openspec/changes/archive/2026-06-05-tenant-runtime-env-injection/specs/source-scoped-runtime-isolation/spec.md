## MODIFIED Requirements

### Requirement: Tenant-scoped helpers SHALL resolve local state by scope
The system SHALL make any helper that resolves tenant-scoped local paths,
configuration, or runtime environment values use runtime scope identity rather
than logical tenant identity.

#### Scenario: Router resolves settings or envs path
- **WHEN** a router resolves tenant-scoped settings, envs, providers, config,
  workspace, memory, media, or heartbeat paths
- **THEN** the helper SHALL use the request `scope_id`
- **AND** explicit logical `tenant_id` input SHALL NOT bypass source scoping

#### Scenario: Runtime resolves provider storage
- **WHEN** provider storage is initialized or loaded for a scoped execution
- **THEN** provider storage SHALL be isolated by `scope_id`
- **AND** source scoping SHALL apply uniformly to every tenant, not only to the
  logical `default` tenant

#### Scenario: Runtime resolves persisted tenant env values
- **WHEN** shell execution, command hook execution, MCP stdio launch, or another
  subprocess runtime reads tenant-scoped env values
- **THEN** the lookup SHALL use the current runtime `scope_id`
- **AND** the lookup SHALL NOT use logical `tenant_id` as the local-state
  isolation key for scoped requests
