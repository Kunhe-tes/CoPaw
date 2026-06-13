# html-preview-path-write Specification

## Purpose
TBD - created by archiving change add-html-preview-path-write. Update Purpose after archive.
## Requirements
### Requirement: Internal HTML preview path generation
The system SHALL provide an internal API that accepts `user_id` and `source_id`, resolves the runtime scope, creates an initial HTML preview file containing `文件正在生成中`, and returns the preview target using the existing public static route shape.

#### Scenario: Preview path generation succeeds
- **WHEN** the internal preview path API is called with a valid `user_id` and `source_id`
- **THEN** the system SHALL resolve the matching runtime `scope_id`
- **AND** it SHALL return a generated `.html` file name
- **AND** it SHALL return a public URL pointing to `/static/<scope_id>/default/<generated_file_name>`
- **AND** it SHALL return a route-relative static path pointing to the same target
- **AND** it SHALL create the corresponding HTML file under `<WORKING_DIR>/<scope_id>/workspaces/default/static/<generated_file_name>`
- **AND** the created HTML file SHALL display `文件正在生成中`

#### Scenario: Generated preview URL is immediately viewable
- **WHEN** the internal preview path API returns a public URL
- **THEN** requesting that URL through the static file route SHALL return the initialized HTML file
- **AND** the returned content SHALL include `文件正在生成中`

#### Scenario: Internal authorization is enforced
- **WHEN** internal API authentication is enabled and the preview path API is called without valid internal authorization
- **THEN** the system SHALL reject the request according to the existing internal API authorization convention

#### Scenario: Invalid identity input is rejected
- **WHEN** the internal preview path API is called with an invalid `user_id` or `source_id`
- **THEN** the system SHALL reject the request with HTTP 400

### Requirement: Text write endpoint accepts reserved preview target
The `/assets/text/write` endpoint SHALL accept an optional generated preview URL or static path in addition to its existing `user_id`, `source_id`, and `content` fields.

#### Scenario: Write uses reserved preview target
- **WHEN** `/assets/text/write` is called with valid content and a preview URL or static path produced for the same `user_id` and `source_id`
- **THEN** the system SHALL overwrite the initialized placeholder file represented by that preview target
- **AND** it SHALL return the same file name and public URL represented by the preview target

#### Scenario: Existing write behavior remains compatible
- **WHEN** `/assets/text/write` is called without a preview URL or static path
- **THEN** the system SHALL continue to generate a new `.html` file name
- **AND** it SHALL write the content to the generated static file
- **AND** it SHALL return the generated file name and public URL

#### Scenario: Preview target from another scope is rejected
- **WHEN** `/assets/text/write` is called with `user_id` and `source_id` that resolve to one scope
- **AND** the provided preview URL or static path points to a different scope
- **THEN** the system SHALL reject the request with HTTP 400
- **AND** it SHALL NOT write the content to either scope

#### Scenario: Unsafe preview target is rejected
- **WHEN** `/assets/text/write` is called with a preview URL or static path containing path traversal, a non-HTML file name, or a path outside `/static/<scope_id>/default/`
- **THEN** the system SHALL reject the request with HTTP 400
- **AND** it SHALL NOT write the content

### Requirement: Reserved preview URLs remain route-compatible
Generated preview targets SHALL use the same static route semantics as the existing text asset write response.

#### Scenario: Generated URL matches static serving route
- **WHEN** a preview URL is generated for a resolved runtime scope
- **THEN** the returned URL SHALL use the configured `FILE_URL` base when available
- **AND** its path SHALL be `/static/<scope_id>/default/<generated_file_name>`

#### Scenario: Content is visible at reserved URL after write
- **WHEN** content is written through `/assets/text/write` using a generated preview target
- **THEN** the public URL returned by the write response SHALL match the generated preview URL
- **AND** the file SHALL be stored under `<WORKING_DIR>/<scope_id>/workspaces/default/static/<generated_file_name>`

