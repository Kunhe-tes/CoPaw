## ADDED Requirements

### Requirement: Skill scan history uses the database as its only data source
The system SHALL persist new SWE blocked and warned skill scan history in the configured application database and SHALL use that database as the sole source for history reads and mutations. The system SHALL NOT read, migrate, write, or fall back to `skill_scanner_blocked.json`.

#### Scenario: Unsafe scan creates a database history record
- **WHEN** an enabled skill scan produces an unsafe result in block or warn mode
- **THEN** the system submits a history record containing the skill name, scan timestamp, maximum severity, findings, content hash, and action to the database-backed history store
- **AND** the system does not write a JSON history file

#### Scenario: Legacy JSON history exists
- **WHEN** `skill_scanner_blocked.json` exists during startup or a history request
- **THEN** the system ignores the file
- **AND** none of its records appear in database-backed history unless they were independently created in the database

### Requirement: History persistence does not weaken scan enforcement
The system SHALL preserve the configured skill scan block or warn outcome independently of database history persistence success.

#### Scenario: Blocked scan cannot be persisted
- **WHEN** a scan must block an unsafe skill and submitting or writing its history record fails
- **THEN** the unsafe skill remains blocked
- **AND** the system records an actionable persistence error without writing a JSON fallback

#### Scenario: Warned scan cannot be persisted
- **WHEN** a scan is configured to warn and submitting or writing its history record fails
- **THEN** the scanner preserves the configured warn-mode result
- **AND** the system records an actionable persistence error without writing a JSON fallback

#### Scenario: Worker-thread submission is flushed
- **WHEN** a worker thread receives successful acknowledgement for a history submission before a history read, mutation, or graceful shutdown begins
- **THEN** the flush waits until that submission has been written or has completed with a logged persistence failure
- **AND** graceful shutdown does not discard it behind the recorder stop marker

#### Scenario: New submissions do not extend an active flush
- **WHEN** a flush begins and additional history submissions are accepted after its boundary
- **THEN** the flush completes after all submissions accepted through its captured boundary finish
- **AND** it does not wait for the later submissions

#### Scenario: Persistence stalls during a bounded flush
- **WHEN** a database insert does not complete before a history route or graceful-shutdown timeout
- **THEN** the history route returns an explicit service-unavailable error or shutdown continues with an actionable timeout log
- **AND** the application does not wait indefinitely

### Requirement: History retrieval is bounded and database-paginated
The blocked-history endpoint SHALL accept `page` values of at least 1 and `page_size` values from 10 through 100, default them to 1 and 20, and return `items`, `total`, `page`, and `page_size`. It SHALL query only the requested database page and SHALL NOT expose an unpaginated list mode.

#### Scenario: Client requests the first page
- **WHEN** a client requests page 1 with page size 20
- **THEN** the endpoint returns at most 20 records under `items`
- **AND** `total`, `page`, and `page_size` describe the complete matching history and requested page

#### Scenario: Client requests a later page
- **WHEN** a client requests a valid page after page 1
- **THEN** the database applies the corresponding limit and offset before returning records
- **AND** the endpoint does not load or serialize all history records

#### Scenario: Client requests a page beyond the result set
- **WHEN** a valid requested page begins after the final history record
- **THEN** `items` is empty
- **AND** `total`, `page`, and `page_size` remain accurate

#### Scenario: Client sends invalid pagination
- **WHEN** `page` is below 1, `page_size` is below 10, or `page_size` exceeds 100
- **THEN** the endpoint rejects the request as invalid

### Requirement: Paginated history has stable newest-first ordering
The system SHALL order paginated history by scan timestamp descending and stable record ID descending before applying the requested page boundary.

#### Scenario: Records have different scan timestamps
- **WHEN** the requested history contains records with different scan timestamps
- **THEN** newer scan records appear before older scan records

#### Scenario: Records share a scan timestamp
- **WHEN** two history records have the same scan timestamp
- **THEN** descending stable record ID deterministically breaks the tie

### Requirement: Operation warning checks are skill-specific, current, and bounded
The system SHALL capture a server-issued time cursor immediately before install, import, save, or broadcast operations and SHALL query at most the newest warned history record for the requested skill created after that cursor.

#### Scenario: Batch operation creates more than one page of warnings
- **WHEN** a batch operation creates warnings for more skills than the history page size
- **THEN** each skill warning check queries that skill directly
- **AND** a matching warning is not omitted because it falls outside global history page 1

#### Scenario: Skill has a warning from an earlier operation
- **WHEN** a current skill operation completes without producing a new warning and the same skill has older warned history
- **THEN** the post-operation warning query excludes the older history using the pre-operation server cursor
- **AND** the Console does not report the historical warning as an outcome of the current operation

### Requirement: History records have stable mutation identity
Each history item SHALL expose its stable database ID. Single-record deletion SHALL target that ID, while clear-all SHALL remove all database history records.

#### Scenario: Client deletes an existing record
- **WHEN** the client deletes a history record by an existing stable ID
- **THEN** the database removes exactly that record
- **AND** the endpoint reports success

#### Scenario: Client deletes an unknown record
- **WHEN** the client deletes a history record by an ID that does not exist
- **THEN** the endpoint returns 404

#### Scenario: Client clears history
- **WHEN** the client confirms clear-all
- **THEN** all database-backed history records are removed
- **AND** a subsequent page reports a total of zero

### Requirement: History storage unavailability is explicit and isolated
When the database-backed history store is unavailable, history read and mutation endpoints SHALL return HTTP 503, and the Console SHALL keep unrelated Security controls interactive while presenting a history-specific error.

#### Scenario: History page is requested without a database store
- **WHEN** the blocked-history endpoint is called while the database store is unavailable
- **THEN** the endpoint returns HTTP 503
- **AND** it does not return an empty history response or read JSON

#### Scenario: Console history request fails
- **WHEN** the Console cannot load a requested history page
- **THEN** it presents an error scoped to scan history
- **AND** users can still operate other Security page controls and tabs

### Requirement: Console loads only the active history page
The Console SHALL request the active history page and page size from the backend and SHALL use the returned total for pagination without slicing a complete history collection locally.

#### Scenario: User opens the skill scanner tab
- **WHEN** the user opens the Skill Scanner tab
- **THEN** the Console requests only the current bounded history page
- **AND** rendering work is bounded by the selected page size

#### Scenario: Deletion empties the current page
- **WHEN** deleting the final item on a non-first page makes that page empty
- **THEN** the Console moves to the preceding valid page and refetches that bounded page

#### Scenario: User changes page size
- **WHEN** the user selects a different supported page size
- **THEN** the Console resets to page 1 and requests that page size from the backend

#### Scenario: Pagination responses arrive out of order
- **WHEN** an older page response arrives after a newer page request has completed
- **THEN** the Console ignores the older response
- **AND** the table remains consistent with the active page

#### Scenario: Requested page becomes invalid
- **WHEN** concurrent deletions make the active page exceed the final valid page
- **THEN** the Console moves to the final valid page and performs one bounded refetch
- **AND** pagination remains available while records still exist

#### Scenario: History mutation fails
- **WHEN** single deletion or clear-all fails
- **THEN** the Console reports the failure and leaves the current history state intact
- **AND** mutation controls expose an in-progress state while the request is pending
