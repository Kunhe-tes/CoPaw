## ADDED Requirements

### Requirement: Asset upload record persistence
The system SHALL persist an upload record to the `swe_asset_upload_record` database table each time a file is successfully uploaded via the `/assets/upload` endpoint.

#### Scenario: Record created on successful upload
- **WHEN** a file is uploaded via `POST /assets/upload` and the file is successfully saved to disk
- **THEN** the system SHALL insert a record into `swe_asset_upload_record` with `file_name`, `file_size`, `asset_path`, `source_id` (NULL if unavailable), and auto-generated `id`, `created_at`, `updated_at`

#### Scenario: Upload succeeds even if record persistence fails
- **WHEN** a file is uploaded and saved to disk successfully, but the database insert fails
- **THEN** the system SHALL still return the upload success response to the caller
- **AND** the system SHALL log a warning about the record persistence failure

### Requirement: Asset upload record query API
The system SHALL provide a `GET /assets/records` endpoint to query upload records with pagination and optional filtering.

#### Scenario: Query all records with pagination
- **WHEN** a caller sends `GET /assets/records?page=1&page_size=20`
- **THEN** the system SHALL return a paginated list of upload records ordered by `created_at` DESC
- **AND** the response SHALL include `items` (list of records), `total` (total count), `page`, and `page_size`

#### Scenario: Filter records by source_id
- **WHEN** a caller sends `GET /assets/records?source_id=xxx`
- **THEN** the system SHALL return only records matching the given `source_id` (using NULL-safe equality)

#### Scenario: Module not initialized
- **WHEN** the database is not connected and a caller sends `GET /assets/records`
- **THEN** the system SHALL return HTTP 503 with an error message indicating the module is not available

### Requirement: Asset upload record data model
The `swe_asset_upload_record` table SHALL have the following columns: `id` (BIGINT AUTO_INCREMENT PK), `file_name` (VARCHAR 256 NOT NULL), `file_size` (BIGINT NOT NULL), `asset_path` (VARCHAR 512 NOT NULL), `source_id` (VARCHAR 64 NULL), `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP), `updated_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP).

#### Scenario: Table schema matches project conventions
- **WHEN** the `swe_asset_upload_record` table is created
- **THEN** it SHALL use InnoDB engine, utf8mb4 charset, `swe_` prefix, and include indexes on `source_id` and `created_at`
