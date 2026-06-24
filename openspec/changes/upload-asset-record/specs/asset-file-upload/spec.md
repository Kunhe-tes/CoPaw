## MODIFIED Requirements

### Requirement: Internal asset file upload
The system SHALL provide an authenticated internal API endpoint for uploading an asset file. Upon successful file save, the system SHALL also persist an upload record to the `swe_asset_upload_record` database table.

#### Scenario: Upload asset file successfully
- **WHEN** an internal caller sends `POST /internal/assets/upload` with a multipart `file` field and valid internal token
- **THEN** the system SHALL save the uploaded bytes to `WORKING_DIR / _ASSET_ROOT_DIRNAME / <file_name>`
- **AND** the system SHALL insert a record into `swe_asset_upload_record` with the file name, size, and asset path
- **AND** the response SHALL include `success: true`, `file_name`, `asset_path`, and `size`

#### Scenario: Reject unauthenticated upload when token is configured
- **WHEN** `SWE_INTERNAL_TOKEN` is configured and an upload request omits or sends an invalid `X-Internal-Token`
- **THEN** the system SHALL reject the request with HTTP 401
- **AND** the system SHALL NOT write the uploaded file to disk
- **AND** the system SHALL NOT insert any upload record

#### Scenario: Upload succeeds even if record persistence fails
- **WHEN** a file is uploaded and saved to disk successfully, but the database insert fails
- **THEN** the system SHALL still return the upload success response
- **AND** the system SHALL log a warning about the record persistence failure
