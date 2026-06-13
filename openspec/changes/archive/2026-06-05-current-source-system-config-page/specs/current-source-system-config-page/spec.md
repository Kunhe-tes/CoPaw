## ADDED Requirements

### Requirement: Console SHALL manage source system config for the current request source only
The Console system config page SHALL read and write source system configuration only for the current request `source_id`. The page MUST NOT expose a source selector or any other mechanism that allows editing a different source from the active iframe/source context.

#### Scenario: Manager opens current source config page
- **WHEN** a manager or admin opens the system config page while the active request context is `source_id=portal`
- **THEN** the Console SHALL load the current source system config for `portal`
- **AND** it SHALL NOT render a source selector or a writable `source_id` field

#### Scenario: Active source changes during a Console session
- **WHEN** the active iframe/source context changes from `portal` to `retail`
- **THEN** the current source config page SHALL discard the previous source data
- **AND** it SHALL reload the page state for `retail`

### Requirement: System SHALL expose raw current-source config APIs distinct from effective config APIs
The system SHALL expose `GET /api/source-system-config/current`, `PUT /api/source-system-config/current`, and `DELETE /api/source-system-config/current` for the current request `source_id`. These APIs SHALL operate on raw stored config, separate from `GET /api/source-system-config/effective`.

#### Scenario: Current source has no explicit record
- **WHEN** an authorized manager calls `GET /api/source-system-config/current` for a valid current source that has no stored config
- **THEN** the system SHALL return HTTP 200 with `config: {}` and `is_default: true`
- **AND** it SHALL return `version: 0`, `updated_by: null`, and `updated_at: null`

#### Scenario: Manager saves current source raw config
- **WHEN** an authorized manager calls `PUT /api/source-system-config/current`
- **THEN** the system SHALL persist the raw config record for the current request `source_id`
- **AND** it SHALL return the stored `source_id`, `config`, `version`, `updated_by`, and `updated_at`

#### Scenario: Caller attempts to target another source
- **WHEN** a client calls a current-source config API
- **THEN** the system SHALL resolve the target source only from the current request context
- **AND** it SHALL NOT accept a path or body field that overrides the target `source_id`

### Requirement: Console SHALL preserve unknown raw config keys when editing registered feature switches
The Console SHALL treat the current-source config page as a structured editor for registered fields, not as an overwrite of the entire raw config object. Saving the page MUST preserve unknown keys that already exist in the raw config.

#### Scenario: Page updates a registered feature switch
- **WHEN** the page saves a new value for a registered switch under `feature_switches`
- **THEN** the Console SHALL merge that change into the fetched raw config
- **AND** it SHALL preserve unrelated keys that are not managed by the page

#### Scenario: Saved value matches the built-in default
- **WHEN** a registered feature switch is saved with the same value as the built-in default
- **THEN** the system SHALL remove that explicit override from the stored raw config
- **AND** it SHALL treat the current source as inheriting the default value for that switch

#### Scenario: No explicit keys remain after pruning
- **WHEN** the page saves changes and the resulting raw config becomes an empty object
- **THEN** the Console SHALL delete the current source config record
- **AND** subsequent current-source reads SHALL return the default-state response for that source

### Requirement: Console SHALL expose registered feature switches on the current source config page
The current source config page SHALL render feature switches from a code-owned registry. The first registered switch SHALL be `feature_switches.chat_task_progress_enabled`.

#### Scenario: Page loads registered switches
- **WHEN** the current source config page is rendered
- **THEN** the Console SHALL show a switch for `feature_switches.chat_task_progress_enabled`
- **AND** the switch value SHALL reflect the current source raw config overlaid on the built-in default value

### Requirement: chat_task_progress_enabled SHALL control task progress generation for the current source
The system SHALL interpret `feature_switches.chat_task_progress_enabled` as a source-scoped capability switch. When the value is `false`, task progress generation and delivery MUST be disabled for requests under that source.

#### Scenario: Task progress is disabled for a source
- **WHEN** `feature_switches.chat_task_progress_enabled=false` for the current request source
- **THEN** the agent system prompt SHALL NOT require `update_task_progress`
- **AND** `update_task_progress` SHALL NOT persist task progress data
- **AND** the runner SHALL NOT attach task progress payloads to outgoing stream events
- **AND** the Console SHALL NOT render the task progress step bar for that request

#### Scenario: Task progress remains enabled by default
- **WHEN** the current source has no explicit override for `feature_switches.chat_task_progress_enabled`
- **THEN** the system SHALL use the built-in default enabled behavior
- **AND** existing task progress prompt, tool, stream, and UI behavior SHALL remain unchanged

### Requirement: Current source config page SHALL enforce manager-level access consistently
The current source config page and current-source config APIs SHALL require manager-level authorization consistent with existing administrative routes.

#### Scenario: Console sends admin role for super manager
- **WHEN** the iframe context marks the user as `isSuperManager=true`
- **THEN** the Console SHALL send `X-User-Role: admin` on current-source config requests
- **AND** the page SHALL allow the user to view and save current source config

#### Scenario: Console sends manager role for manager user
- **WHEN** the iframe context marks the user as `manager=true` and `isSuperManager=false`
- **THEN** the Console SHALL send `X-User-Role: manager` on current-source config requests
- **AND** the page SHALL allow the user to view and save current source config

#### Scenario: Non-manager opens the page
- **WHEN** a user without `manager` or `admin` privileges attempts to access the current source config page
- **THEN** the Console SHALL hide the page entry from normal navigation
- **AND** direct page access SHALL render a 403-style unavailable state
- **AND** the backend SHALL reject current-source config write requests

### Requirement: Saving current source config SHALL refresh effective source config in Console
The Console SHALL refresh its cached effective source system config after a successful current-source config save or delete, so later requests under the same active source observe the new behavior without a full page reload.

#### Scenario: Manager saves task progress switch
- **WHEN** a manager successfully saves or deletes current-source config for the active source
- **THEN** the Console SHALL reload the effective source system config for that active source
- **AND** subsequent chat requests from the same session SHALL use the refreshed effective config
