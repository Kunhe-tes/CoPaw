## ADDED Requirements

### Requirement: Chat attachment upload SHALL reject executable code extensions

The system SHALL reject chat session attachment uploads whose uploaded filename has a denied executable code extension. Extension matching SHALL be case-insensitive and SHALL evaluate only the uploaded filename's outermost extension.

The denied extension set SHALL include `.py`, `.pyw`, `.java`, `.class`, `.jar`, `.js`, `.mjs`, `.cjs`, `.jsx`, `.ts`, `.tsx`, `.sh`, `.bash`, `.zsh`, `.fish`, `.ps1`, `.bat`, `.cmd`, `.php`, `.rb`, `.pl`, `.lua`, `.go`, `.rs`, `.c`, `.cc`, `.cpp`, `.cxx`, `.h`, `.hpp`, `.cs`, `.kt`, `.kts`, `.swift`, `.exe`, `.dll`, `.so`, and `.dylib`.

#### Scenario: Python file is rejected
- **WHEN** a user uploads a chat attachment named `script.py`
- **THEN** the system SHALL reject the upload
- **AND** it SHALL NOT write the uploaded file to the chat media directory

#### Scenario: Uppercase Java file is rejected
- **WHEN** a user uploads a chat attachment named `Example.JAVA`
- **THEN** the system SHALL reject the upload
- **AND** extension matching SHALL treat `.JAVA` as `.java`

#### Scenario: JavaScript file is rejected
- **WHEN** a user uploads a chat attachment named `app.min.js`
- **THEN** the system SHALL reject the upload
- **AND** it SHALL NOT create a preview URL for the file

#### Scenario: Archive containing code-like inner name is allowed
- **WHEN** a user uploads a chat attachment named `script.py.zip`
- **THEN** the system SHALL evaluate only the outer `.zip` extension
- **AND** it SHALL allow the upload if all other upload validations pass

### Requirement: Chat UI SHALL prevent blocked attachment uploads before calling the upload API

The chat session interface SHALL validate selected, pasted, and dragged attachment files against the denied executable code extension set before calling the upload API. When a file is blocked, the interface SHALL show a localized error message and SHALL mark the upload attempt as failed.

#### Scenario: Blocked file selected in the chat UI
- **WHEN** a user selects a chat attachment named `main.ts`
- **THEN** the chat UI SHALL show an error explaining that executable code files cannot be uploaded
- **AND** it SHALL NOT call `POST /console/upload`

#### Scenario: Blocked file is pasted or dropped
- **WHEN** a user pastes or drops a chat attachment named `run.sh`
- **THEN** the chat UI SHALL reject the file before upload
- **AND** it SHALL keep the chat input usable for other attachments or messages

### Requirement: Chat upload API SHALL enforce blocked extensions

The `POST /console/upload` endpoint SHALL enforce the denied executable code extension set before writing uploaded bytes to disk. Rejected uploads SHALL return HTTP 400 with an error detail that identifies the file type as unsupported for chat attachment upload.

#### Scenario: Direct API upload is rejected
- **WHEN** a caller sends `POST /console/upload` with a multipart file named `Program.cs`
- **THEN** the endpoint SHALL return HTTP 400
- **AND** it SHALL NOT write the uploaded bytes to the console media directory

#### Scenario: Non-code attachment still uploads
- **WHEN** a caller sends `POST /console/upload` with a multipart file named `report.pdf`
- **THEN** the endpoint SHALL preserve the existing successful upload response behavior
- **AND** it SHALL return the stored file path, original safe file name, and file size
