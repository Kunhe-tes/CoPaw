## 1. Backend Upload Policy

- [x] 1.1 Add a named denied executable-extension set for chat attachments in `src/swe/app/routers/console.py`.
- [x] 1.2 Add a helper that evaluates only the outer filename extension case-insensitively.
- [x] 1.3 Update `POST /console/upload` to reject denied extensions with HTTP 400 before writing bytes to the media directory.
- [x] 1.4 Preserve existing file size validation, safe filename generation, storage path, and successful response shape for allowed uploads.

## 2. Frontend Upload Policy

- [x] 2.1 Add the matching denied executable-extension set to the chat page upload logic.
- [x] 2.2 Update `handleFileUpload` to reject blocked files before calling `chatApi.uploadFile`.
- [x] 2.3 Add localized chat attachment error text explaining that executable code files cannot be uploaded.
- [x] 2.4 Optionally narrow the file picker `accept` hint for common allowed formats without treating it as the security boundary.

## 3. Tests

- [x] 3.1 Add backend tests proving `.py`, `.JAVA`, `.js`, and `.cs` chat uploads return HTTP 400 and do not write files.
- [x] 3.2 Add backend tests proving `.zip`, `.py.zip`, and `.pdf` uploads remain allowed when other validations pass.
- [x] 3.3 Add frontend tests proving blocked files show the localized error and do not call `chatApi.uploadFile`.
- [x] 3.4 Add frontend tests proving allowed archive filenames still call the upload API.

## 4. Verification

- [x] 4.1 Run the focused backend router tests for console upload.
- [x] 4.2 Run the focused frontend tests for chat attachment upload.
- [x] 4.3 Run OpenSpec validation/status checks for `restrict-chat-code-file-uploads`.
