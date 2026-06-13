## ADDED Requirements

### Requirement: Internal asset file upload
The system SHALL provide an authenticated internal API endpoint for uploading an asset file.

#### Scenario: Upload asset file successfully
- **WHEN** an internal caller sends `POST /internal/assets/upload` with a multipart `file` field and valid internal token
- **THEN** the system SHALL save the uploaded bytes to `WORKING_DIR / _ASSET_ROOT_DIRNAME / <file_name>`
- **AND** the response SHALL include `success: true`, `file_name`, `asset_path`, and `size`

#### Scenario: Reject unauthenticated upload when token is configured
- **WHEN** `SWE_INTERNAL_TOKEN` is configured and an upload request omits or sends an invalid `X-Internal-Token`
- **THEN** the system SHALL reject the request with HTTP 401
- **AND** the system SHALL NOT write the uploaded file to disk

### Requirement: Upload filename safety
The system MUST validate the uploaded file name before writing to disk.

#### Scenario: Reject path traversal filename
- **WHEN** an upload request uses a file name containing a path separator, absolute path, empty value, `.` or `..`
- **THEN** the system SHALL reject the request with HTTP 400
- **AND** the system SHALL NOT create or modify files outside `WORKING_DIR / _ASSET_ROOT_DIRNAME`

### Requirement: Upload preserves file bytes
The system SHALL store uploaded file content without text decoding or content transformation.

#### Scenario: Upload binary file
- **WHEN** an internal caller uploads binary content that is not valid UTF-8
- **THEN** the system SHALL save the exact uploaded bytes under the asset root directory
- **AND** the response `size` SHALL equal the number of uploaded bytes

### Requirement: Upload overwrites matching asset filename
The system SHALL overwrite an existing asset file when an authenticated upload uses the same validated file name.

#### Scenario: Replace existing asset file
- **WHEN** an asset file already exists under `WORKING_DIR / _ASSET_ROOT_DIRNAME`
- **AND** an internal caller uploads a new file with the same file name
- **THEN** the system SHALL replace the stored file content with the newly uploaded bytes
