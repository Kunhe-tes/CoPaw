# Source-Scoped Runtime Isolation

## Purpose
Define source-scoped runtime isolation so tenant-scoped state, runtime helpers,
and background execution paths consistently isolate local state by resolved
`scope_id` rather than logical tenant identity alone.
## Requirements
### Requirement: Scoped runtime identity SHALL combine source and logical tenant
The system SHALL derive a runtime `scope_id` from `source_id` and logical
`tenant_id` for every tenant-scoped execution path. The runtime `scope_id`
SHALL be the only identifier used for local-state isolation.

#### Scenario: HTTP request resolves runtime scope
- **WHEN** a non-exempt HTTP request includes `X-Tenant-Id` and `X-Source-Id`
- **THEN** the system SHALL resolve a runtime `scope_id` from those two values
- **AND** the request context SHALL retain logical `tenant_id`, `source_id`,
  and resolved `scope_id`

#### Scenario: Runtime code uses scope instead of logical tenant
- **WHEN** workspace, runner, provider, config, or filesystem helpers operate
  on tenant-scoped local state
- **THEN** they SHALL use the resolved `scope_id`
- **AND** they SHALL NOT use logical `tenant_id` as the local-state isolation
  key

### Requirement: Scope identifiers SHALL be centrally validated and collision-safe
The system SHALL validate raw `tenant_id` and `source_id` before scope
resolution and SHALL encode `scope_id` using one reversible, collision-safe
format that is safe for directory names, cache keys, and logs.

#### Scenario: Scoped request includes malformed source identity
- **WHEN** a tenant-scoped entry provides `X-Source-Id` or equivalent source
  transport containing malformed, unsafe, or unsupported characters
- **THEN** the system SHALL reject the entry before any scope-aware state is
  read or written

#### Scenario: Scope format coexists with legacy tenant names
- **WHEN** the runtime resolves `scope_id` for `(source_id, tenant_id)`
- **THEN** the encoded value SHALL not collide with an existing logical tenant
  name or legacy `default_{source}` directory pattern
- **AND** downstream code SHALL be able to decode it back to the original
  `source_id` and logical `tenant_id`

### Requirement: Non-exempt scoped ingress SHALL require explicit source identity
The system SHALL reject any non-exempt tenant-scoped request or runtime entry
that does not provide explicit source identity.

#### Scenario: HTTP request omits source header
- **WHEN** a non-exempt tenant-scoped HTTP request omits `X-Source-Id`
- **THEN** the system SHALL reject the request
- **AND** it SHALL NOT fall back to `"default"` or any implicit source value

#### Scenario: Scoped non-HTTP entry omits source identity
- **WHEN** a CLI call, internal API, cron path, or channel callback attempts to
  access tenant-scoped local state without explicit source identity
- **THEN** the system SHALL treat that entry as invalid
- **AND** it SHALL NOT continue with tenant-only runtime scoping

### Requirement: Runtime propagation SHALL preserve scope across execution paths
The system SHALL propagate `scope_id` through runtime objects and background
flows that access tenant-scoped state.

#### Scenario: Workspace runtime is loaded for a scoped request
- **WHEN** a request resolves a runtime `scope_id`
- **THEN** the workspace cache key, workspace runtime identity, and runner
  identity SHALL all use that `scope_id`

#### Scenario: Background continuation writes scoped state
- **WHEN** a background task, auto-follow-up, cron execution, or callback-driven
  request writes suggestions, validation state, provider data, or other
  tenant-scoped artifacts
- **THEN** it SHALL use the same `scope_id` that originated the execution

#### Scenario: Background binder needs the original source identity
- **WHEN** a background task, callback handler, or cron path reconstructs a
  scoped runtime context
- **THEN** it SHALL preserve logical `tenant_id`, raw `source_id`, and resolved
  `scope_id`
- **AND** downstream code SHALL NOT be forced to infer `source_id` back from a
  tenant-only fallback or from opaque local state

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

### Requirement: Temporary session and chat stores SHALL isolate by scope-aware keys
Temporary stores for scoped runtime data SHALL use keys that include runtime
scope identity.

#### Scenario: Two scopes share the same session identifier
- **WHEN** two different `scope_id` values use the same logical `session_id`
- **THEN** suggestions, push messages, validation state, and similar temporary
  data SHALL remain isolated between the two scopes

#### Scenario: Two scopes share the same chat identifier
- **WHEN** two different `scope_id` values reference the same logical `chat_id`
- **THEN** any chat-scoped temporary content SHALL remain isolated between the
  two scopes

### Requirement: Approval state MUST isolate by scope
The system MUST isolate process-wide transient state used by approvals,
progress reporting, callbacks, and other control flows with scope-aware
lookup keys or namespaces.

#### Scenario: Two scopes share the same session during approval flow
- **WHEN** two different `scope_id` values use the same logical `session_id`
  and both create pending approvals or post-turn control state
- **THEN** each scope SHALL only be able to observe and consume its own pending
  records

#### Scenario: Two scopes report progress concurrently
- **WHEN** scoped executions emit MCP progress events or similar transient
  control identifiers at the same time
- **THEN** the emitted identifiers and their lookup namespaces SHALL remain
  unique per `scope_id`

### Requirement: Callback and control protocols SHALL carry source identity explicitly
The system SHALL require callback, control, and automation protocols that touch
tenant-scoped state to transport source identity explicitly rather than
inferring it from local tenant state. These protocols MUST provide enough
source context for downstream runtime code to recover the originating
`scope_id`.

#### Scenario: Channel callback enters the runtime
- **WHEN** a channel callback constructs a runtime request for a tenant-scoped
  execution
- **THEN** the callback path SHALL attach explicit `source_id`
- **AND** downstream runtime code SHALL be able to recover the originating
  `scope_id`

#### Scenario: CLI or internal reload requests a scoped runtime
- **WHEN** a CLI or internal control call targets a tenant-scoped runtime
- **THEN** the call SHALL transmit both logical `tenant_id` and `source_id`
- **AND** runtime reload or lookup SHALL resolve the target by `scope_id`

#### Scenario: Auth-exempt callback still needs source identity
- **WHEN** an HTTP callback route is exempt from tenant-auth requirements but
  still enters tenant-scoped runtime execution
- **THEN** the route SHALL still require an explicit source transport contract
- **AND** it SHALL NOT fall back to `"default"` or inherit source identity from
  unrelated local state

### Requirement: Runtime caches MUST not reuse tenant-only entries after scope cutover
The system MUST prevent long-lived process caches and singletons that
previously keyed by logical tenant from serving stale tenant-only entries for
scope-aware traffic after cutover.

#### Scenario: Process restarts into scope-aware mode
- **WHEN** the service starts serving source-scoped traffic after the cutover
- **THEN** scope-sensitive caches and registries SHALL be empty or rebuilt under
  the new `scope_id` namespace before serving requests

#### Scenario: Old tenant-only cache entry exists during rollout
- **WHEN** a stale tenant-only runtime cache entry exists for a logical tenant
- **THEN** scoped traffic for the same logical tenant but a different source
  SHALL NOT reuse that entry

