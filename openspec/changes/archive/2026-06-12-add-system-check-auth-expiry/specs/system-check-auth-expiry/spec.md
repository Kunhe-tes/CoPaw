## ADDED Requirements

### Requirement: Console SHALL provide a manager-only system self-check page
The Console SHALL expose a page named "系统自检" for manager and admin users. The page SHALL initially contain only the "鉴权过期查询" self-check.

#### Scenario: Manager opens system self-check page
- **WHEN** a Console user has manager or admin privileges
- **THEN** the normal navigation SHALL include the "系统自检" page entry
- **AND** the page SHALL render the "鉴权过期查询" check

#### Scenario: Non-manager attempts to access system self-check page
- **WHEN** a Console user without manager or admin privileges uses normal navigation
- **THEN** the Console SHALL NOT show the "系统自检" navigation entry
- **AND** direct access to the page route SHALL render a 403-style unavailable state

### Requirement: Auth expiry check SHALL accept source and manual tenant input
The "鉴权过期查询" check SHALL let a manager submit a source ID and a manually entered list of tenant IDs. The source ID field SHALL default to `RMASSIST`.

#### Scenario: System self-check page opens
- **WHEN** a manager opens the "系统自检" page
- **THEN** the auth expiry source ID field SHALL be populated with `RMASSIST`
- **AND** the tenant ID list SHALL be empty

#### Scenario: Manager submits tenant IDs
- **WHEN** a manager enters tenant IDs separated by newlines, commas, Chinese commas, spaces, or semicolons
- **THEN** the Console SHALL normalize the input into a de-duplicated tenant ID list
- **AND** the Console SHALL submit the entered source ID and normalized tenant IDs to the backend

#### Scenario: Manager submits no tenant IDs
- **WHEN** a manager attempts to run the auth expiry check without any tenant IDs
- **THEN** the Console SHALL show a validation error
- **AND** it SHALL NOT call the backend

### Requirement: Backend SHALL expose a manager-only batch auth expiry API
The system SHALL expose a read-only batch API for cron auth expiry inspection. The API SHALL require manager or admin authorization and SHALL reject unauthorized callers.

#### Scenario: Authorized manager calls batch auth expiry API
- **WHEN** a request to the batch auth expiry API includes `X-User-Role: manager` or `X-User-Role: admin`
- **THEN** the system SHALL process the request
- **AND** it SHALL return one result per submitted tenant ID

#### Scenario: Unauthorized caller calls batch auth expiry API
- **WHEN** a request to the batch auth expiry API omits manager/admin role authorization
- **THEN** the system SHALL reject the request with HTTP 403
- **AND** it SHALL NOT read any tenant `cron_auth.json` files

#### Scenario: Request contains invalid source identity
- **WHEN** a request contains an empty, malformed, or unsafe `source_id`
- **THEN** the system SHALL reject the request with HTTP 400
- **AND** it SHALL NOT read any tenant `cron_auth.json` files

#### Scenario: Request contains invalid tenant identity
- **WHEN** a request contains an empty, malformed, duplicate-only, or unsafe tenant ID entry
- **THEN** the system SHALL reject invalid entries before filesystem access
- **AND** it SHALL return a validation error instead of reading an unintended path

### Requirement: Auth expiry lookup SHALL use source-scoped tenant paths
For each submitted logical tenant ID, the backend SHALL resolve the runtime tenant scope using the request body's `source_id` before locating `cron_auth.json`.

#### Scenario: RMASSIST tenant is checked
- **WHEN** the API receives `source_id=RMASSIST` and `tenant_id=tenant-a`
- **THEN** the system SHALL resolve the runtime scope for `(tenant-a, RMASSIST)`
- **AND** it SHALL read `cron_auth.json` from that resolved runtime tenant's secret directory

#### Scenario: Caller request source differs from checked source
- **WHEN** the caller's request headers contain a different `X-Source-Id` than the body `source_id`
- **THEN** the auth expiry lookup SHALL use the body `source_id` for checked tenant paths
- **AND** the response SHALL identify the checked `source_id`

### Requirement: Auth expiry API SHALL classify auth state without exposing secrets
The batch auth expiry API SHALL return normalized diagnostic statuses for each tenant and SHALL NOT expose stored cookies, tokens, user info payloads, or local filesystem paths.

#### Scenario: User info expiry is in the future
- **WHEN** a tenant's `cron_auth.json` exists, is valid, and contains `user_info_expires_at` later than the current time
- **THEN** the tenant result status SHALL be `valid`
- **AND** `is_expired` SHALL be `false`
- **AND** `user_info_expires_at` SHALL be returned in the response

#### Scenario: User info expiry is in the past
- **WHEN** a tenant's `cron_auth.json` exists, is valid, and contains `user_info_expires_at` earlier than or equal to the current time
- **THEN** the tenant result status SHALL be `expired`
- **AND** `is_expired` SHALL be `true`
- **AND** `user_info_expires_at` SHALL be returned in the response

#### Scenario: Auth file does not exist
- **WHEN** the resolved tenant secret directory does not contain `cron_auth.json`
- **THEN** the tenant result status SHALL be `missing_file`
- **AND** `is_expired` SHALL be `null`
- **AND** the response message SHALL indicate that no auth file was found

#### Scenario: Auth file content is invalid
- **WHEN** `cron_auth.json` exists but cannot be read, parsed as JSON, validated as cron auth state, or interpreted for expiry
- **THEN** the tenant result status SHALL be `invalid_content`
- **AND** `is_expired` SHALL be `null`
- **AND** the response message SHALL indicate that the auth file content is invalid

#### Scenario: Auth file is valid but expiry is missing
- **WHEN** `cron_auth.json` exists and is valid but does not contain `user_info_expires_at`
- **THEN** the tenant result status SHALL be `unknown`
- **AND** `is_expired` SHALL be `null`
- **AND** the response message SHALL indicate that expiry cannot be determined

#### Scenario: Response is returned for display
- **WHEN** the API returns tenant results
- **THEN** each result SHALL include `tenant_id`, `source_id`, `status`, `is_expired`, `user_info_expires_at`, and `message`
- **AND** no result SHALL include cookies, access tokens, auth tokens, raw user info, or local filesystem paths

### Requirement: Console SHALL display auth expiry results in a table
The "鉴权过期查询" check SHALL display returned tenant results in a table suitable for operational review.

#### Scenario: Query succeeds
- **WHEN** the backend returns auth expiry results
- **THEN** the Console SHALL render a table with tenant ID, source ID, status, expiry time, expired flag, and message columns
- **AND** status values SHALL be visually distinguishable

#### Scenario: Query fails
- **WHEN** the backend rejects or fails the auth expiry query
- **THEN** the Console SHALL show an error message
- **AND** it SHALL keep the submitted form inputs available for correction or retry
