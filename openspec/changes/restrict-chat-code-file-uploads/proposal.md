## Why

The chat session upload surface currently accepts any file type and only enforces file size. Users can upload executable code files such as Python, Java, JavaScript, shell, or binary executable artifacts, which creates unnecessary risk for a chat attachment workflow.

## What Changes

- Add a chat attachment upload policy that rejects executable code file types by outer filename extension.
- Enforce the policy in the chat UI before upload so users get immediate feedback.
- Enforce the same policy in `POST /console/upload` so direct API calls cannot bypass the UI.
- Keep archive files allowed without inspecting archive contents; files such as `code.py.zip` remain uploadable because only the uploaded file's outer extension is evaluated.
- Keep existing upload size validation and filename sanitization behavior.

## Capabilities

### New Capabilities
- `chat-attachment-upload`: Chat session attachment upload validation, including executable code extension rejection and user-facing upload behavior.

### Modified Capabilities

## Impact

- **Frontend**: Chat attachment upload handler and localized error messaging in `console/src/pages/Chat/index.tsx` and locale files.
- **Backend API**: `POST /console/upload` rejects configured executable code extensions with HTTP 400 before writing files to disk.
- **Tests**: Add frontend upload validation coverage and backend router coverage for rejected executable extensions and allowed archive filenames.
- **Dependencies**: No new external dependencies.
