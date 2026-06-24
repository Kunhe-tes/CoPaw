## ADDED Requirements

### Requirement: Tenant env API persists current-scope runtime env values
The system SHALL persist environment variables submitted through the tenant env
API to the current runtime scope's secret env store without mutating the
process-global environment.

#### Scenario: Current scoped request saves env values
- **WHEN** a non-exempt request calls `PUT /api/envs` with valid
  `X-Tenant-Id` and `X-Source-Id` headers and a string env dictionary
- **THEN** the system SHALL write the dictionary to the resolved `scope_id`
  `.secret/envs.json`
- **AND** the system SHALL NOT write those values into process-global
  `os.environ`

#### Scenario: Different sources for the same tenant save separate env values
- **WHEN** two requests use the same logical `tenant_id` and different
  `source_id` values
- **THEN** their env dictionaries SHALL be stored under different runtime
  scope secret directories
- **AND** a later runtime env lookup for one scope SHALL NOT read values from
  the other scope

#### Scenario: Env file write preserves secret-store safety
- **WHEN** the system writes tenant env values to `.secret/envs.json`
- **THEN** the write SHALL use secret-store permissions where the platform
  supports them
- **AND** the write SHALL avoid leaving partially written JSON visible as the
  committed env file

### Requirement: Tenant env API validates env names and protected keys
The system SHALL validate tenant env keys on write before they can be persisted
or injected into runtime execution.

#### Scenario: API rejects malformed env key
- **WHEN** a caller submits an env key that is empty or does not match the
  supported environment variable name format
- **THEN** the system SHALL reject the request before writing `.secret/envs.json`
- **AND** the system SHALL return a validation error that identifies the key by
  name only

#### Scenario: API rejects protected env key
- **WHEN** a caller submits an env key that is reserved for runtime isolation,
  shell startup, interpreter behavior, dynamic loading, or executable
  resolution
- **THEN** the system SHALL reject the request before writing `.secret/envs.json`
- **AND** the system SHALL NOT persist the protected key as a tenant auth env
  value

### Requirement: Tenant env read APIs are secret-safe by default
The system SHALL avoid returning full secret-bearing env values from routine
tenant env read APIs.

#### Scenario: List envs returns masked values by default
- **WHEN** a caller lists tenant env values through the normal console-facing
  API
- **THEN** the system SHALL return env keys with masked values or metadata
- **AND** the response SHALL NOT include full secret values by default

#### Scenario: Client preserves an existing secret without reading it
- **WHEN** a client edits tenant env values after receiving masked values
- **THEN** the API SHALL provide update semantics that let the client preserve
  unchanged secrets without knowing their full values
- **AND** the client SHALL NOT need to submit masked placeholders as literal
  secret values

#### Scenario: First version does not require full secret reveal
- **WHEN** the system implements the first version of tenant runtime env
  injection
- **THEN** ordinary console-facing read APIs SHALL NOT reveal full env values
- **AND** no routine full-value reveal path SHALL be required for editing or
  runtime injection

### Requirement: Runtime env builder merges tenant env for subprocess execution
The system SHALL provide a shared runtime env builder that merges process env,
current-scope persisted tenant env, and call-specific env for subprocess
execution.

#### Scenario: Runtime env includes persisted tenant auth value
- **WHEN** the current scope has `.secret/envs.json` containing
  `{"API_TOKEN": "tenant-secret"}`
- **AND** a subprocess execution path asks for runtime env
- **THEN** the returned env SHALL contain `API_TOKEN=tenant-secret`

#### Scenario: Call-specific env overrides tenant env
- **WHEN** the current scope env contains `{"API_TOKEN": "tenant-secret"}`
- **AND** the execution path provides call-specific env
  `{"API_TOKEN": "call-secret"}`
- **THEN** the returned env SHALL contain `API_TOKEN=call-secret`

#### Scenario: Missing tenant context does not fall back to unrelated env store
- **WHEN** no runtime tenant or scope context is available
- **AND** a subprocess execution path asks for tenant runtime env
- **THEN** the system SHALL NOT read an unrelated default tenant env store
- **AND** the execution path SHALL either proceed with process env only where
  explicitly allowed or fail closed where tenant context is required

### Requirement: Runtime env injection protects isolation-sensitive variables
The system SHALL prevent persisted tenant env values from overriding
isolation-sensitive runtime variables during subprocess env construction.

#### Scenario: Tenant env contains protected runtime keys
- **WHEN** the current scope env contains `SWE_WORKING_DIR`, `SWE_SECRET_DIR`,
  `PATH`, `HOME`, `SHELL`, `BASH_ENV`, `ENV`, `ZDOTDIR`, `IFS`, `CDPATH`,
  `PYTHONPATH`, `PYTHONHOME`, `LD_LIBRARY_PATH`, or `DYLD_LIBRARY_PATH`
- **THEN** the runtime env builder SHALL NOT apply those tenant-provided values
  to the subprocess env
- **AND** existing process or tool-controlled values for those keys SHALL remain
  authoritative

#### Scenario: Call-specific env contains protected runtime keys
- **WHEN** tenant-controlled call-specific env from hook config or MCP client
  config contains a protected runtime key
- **THEN** the runtime env builder SHALL NOT apply that tenant-controlled value
  to the subprocess env
- **AND** call-specific override precedence SHALL apply only to non-protected
  keys

#### Scenario: Normal auth keys are preserved
- **WHEN** the current scope env contains auth keys that are not protected
- **THEN** the runtime env builder SHALL include those keys in the subprocess
  env according to the defined merge precedence

### Requirement: Runtime env handling avoids automatic secret disclosure
The system SHALL avoid automatically exposing tenant runtime env values through
logs, traces, diagnostics, or validation errors.

#### Scenario: Runtime env builder skips a protected key
- **WHEN** the runtime env builder ignores or rejects a protected env key
- **THEN** the system SHALL NOT log or return the protected key's value
- **AND** any diagnostic SHALL identify only the key name and reason

#### Scenario: Injected env values are registered for redaction
- **WHEN** tenant runtime env values are injected into a tool or integration
  execution path
- **THEN** the system SHALL make those secret values available to the existing
  tracing or logging redaction mechanism where such a mechanism records tool
  inputs, outputs, or diagnostics
- **AND** automatic traces or logs SHALL NOT persist raw injected secret values
  when redaction is available

### Requirement: Shell command execution receives tenant runtime env
The shell command tool SHALL execute commands with the current scope's tenant
runtime env merged into the subprocess env.

#### Scenario: Shell command reads tenant env value
- **WHEN** the current scope env contains `{"API_TOKEN": "tenant-secret"}`
- **AND** the agent invokes `execute_shell_command` with a command that reads
  `API_TOKEN`
- **THEN** the spawned shell process SHALL receive `API_TOKEN=tenant-secret`

#### Scenario: Shell env injection does not bypass path boundary checks
- **WHEN** a shell command is rejected because its `cwd` or explicit path token
  escapes the current tenant workspace
- **THEN** the system SHALL reject the command before starting a subprocess
- **AND** tenant env injection SHALL NOT occur for that rejected command

### Requirement: Command hook execution receives tenant runtime env
Command hook handlers SHALL execute with the current scope's tenant runtime env
merged into their subprocess env.

#### Scenario: Command hook reads tenant env value
- **WHEN** a command hook runs for a scoped agent execution
- **AND** the current scope env contains `{"HOOK_TOKEN": "tenant-secret"}`
- **THEN** the command hook subprocess SHALL receive
  `HOOK_TOKEN=tenant-secret`

#### Scenario: Command hook handler env overrides tenant env
- **WHEN** the current scope env contains `{"HOOK_TOKEN": "tenant-secret"}`
- **AND** the command hook handler config contains
  `env={"HOOK_TOKEN": "handler-secret"}`
- **THEN** the command hook subprocess SHALL receive
  `HOOK_TOKEN=handler-secret`

### Requirement: MCP stdio execution receives tenant runtime env
MCP stdio server processes SHALL launch with the current scope's tenant runtime
env merged into their configured process env.

#### Scenario: MCP stdio server reads tenant env value
- **WHEN** an MCP stdio client is started for a scoped tenant runtime
- **AND** the current scope env contains `{"MCP_TOKEN": "tenant-secret"}`
- **THEN** the MCP stdio server process SHALL receive
  `MCP_TOKEN=tenant-secret`

#### Scenario: MCP client config env overrides tenant env
- **WHEN** the current scope env contains `{"MCP_TOKEN": "tenant-secret"}`
- **AND** the MCP client config contains `env={"MCP_TOKEN": "client-secret"}`
- **THEN** the MCP stdio server process SHALL receive
  `MCP_TOKEN=client-secret`

#### Scenario: Existing MCP process keeps old env until reload
- **WHEN** a tenant env value changes after an MCP stdio server process has
  already started
- **THEN** the running MCP process SHALL NOT be expected to receive the new env
  value until the MCP client is restarted or reloaded

### Requirement: Tool integration env references use tenant-aware lookup
Tool integration configuration that resolves environment references SHALL use
tenant-aware env lookup for tenant auth values rather than process-global
environment expansion.

#### Scenario: MCP HTTP header references tenant env with explicit syntax
- **WHEN** an MCP HTTP client header configuration references a tenant env key
  for the current runtime scope using the supported tenant env reference syntax
- **THEN** the system SHALL resolve the header value from the current scope's
  tenant env store
- **AND** the system SHALL NOT require that value to exist in process-global
  `os.environ`

#### Scenario: Literal header value is not treated as tenant env reference
- **WHEN** an MCP HTTP client header configuration contains a literal value
  without the supported tenant env reference syntax
- **THEN** the system SHALL preserve the literal value
- **AND** the system SHALL NOT reinterpret the literal value as a tenant env key

#### Scenario: Env reference resolution stays source-scoped
- **WHEN** two different source scopes define different values for the same env
  key
- **THEN** tool integration env reference resolution SHALL use the value from
  the active runtime `scope_id`
- **AND** it SHALL NOT read the sibling source scope's value

### Requirement: Target-tenant env writes use an explicit privileged API
The system SHALL provide a privileged target-scope env write API and SHALL NOT
allow ordinary current-scope env API calls to write env values for arbitrary
target tenants.

#### Scenario: Ordinary env save cannot override target tenant
- **WHEN** a caller submits env values to the current-scope env API
- **THEN** the system SHALL derive the write target from request context
- **AND** request body fields SHALL NOT redirect the write to another tenant or
  source scope

#### Scenario: Manager target write includes target source identity
- **WHEN** a manager or internal caller writes env values for a specified target
  tenant
- **THEN** the API SHALL require explicit target tenant identity and source
  identity
- **AND** the API SHALL validate those identities before writing any target
  scope secret env store

#### Scenario: Non-privileged target write is rejected
- **WHEN** a caller without manager or internal authorization attempts to write
  env values for a specified target tenant
- **THEN** the system SHALL reject the request
- **AND** the target scope env store SHALL remain unchanged

#### Scenario: Target write records audit metadata
- **WHEN** a manager or internal target-scope env write succeeds
- **THEN** the system SHALL record enough audit metadata to identify the acting
  user or internal caller, target tenant, target source, and affected env keys
- **AND** the audit metadata SHALL NOT include raw env values
