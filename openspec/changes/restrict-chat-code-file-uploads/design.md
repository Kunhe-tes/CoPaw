## Context

The chat page currently configures attachments with `accept: "*/*"` and the upload handler only checks model capability warnings and the 10 MB file size limit before calling `chatApi.uploadFile`. The backend `POST /console/upload` endpoint reads the multipart file, enforces the same size limit, sanitizes the filename, writes the bytes into the console channel media directory, and returns a preview URL path. There is no executable-code file type policy on either side.

This change is security-relevant because frontend-only validation is bypassable through drag/drop, paste, browser tooling, or direct API calls. The backend must be the authoritative enforcement point, while the frontend should provide fast user feedback.

## Goals / Non-Goals

**Goals:**
- Reject executable code files uploaded as chat session attachments.
- Apply the same denied extension set in the frontend and backend.
- Evaluate only the uploaded file's outer filename extension, case-insensitively.
- Preserve existing behavior for file size validation, filename sanitization, storage location, and successful upload response shape.
- Allow archives and multi-extension archive names without inspecting archive contents.

**Non-Goals:**
- Do not scan inside `.zip`, `.tar`, `.gz`, `.7z`, or other archive formats.
- Do not change non-chat asset upload endpoints such as `/assets/upload` or `/internal/assets/upload`.
- Do not introduce content-based malware scanning or MIME sniffing.
- Do not block generated files or static file preview behavior outside the chat attachment upload path.

## Decisions

### 1. Backend enforcement is authoritative

**Decision:** Add denied-extension validation to `POST /console/upload` before writing bytes to disk.

**Rationale:** The chat UI can be bypassed. Backend rejection ensures direct calls to `/console/upload` cannot store disallowed executable code files in the media directory.

**Alternative considered:** Frontend-only validation. Rejected because it provides user experience but not a security boundary.

### 2. Extension-based policy, not MIME-based policy

**Decision:** Determine disallowed uploads by `Path(filename).suffix.lower()` after extracting the outer extension.

**Rationale:** Browser-provided MIME types are inconsistent and request-controlled. The user's requested behavior is about code file types such as Python, Java, and JavaScript. Filename extension is the clearest and most testable policy for this scope.

**Alternative considered:** MIME type rejection. Rejected because many source files are sent as `text/plain`, `application/octet-stream`, or an empty MIME type.

### 3. Only outer extension is evaluated

**Decision:** Evaluate only the final suffix of the uploaded filename. For example, `code.py` is denied, while `code.py.zip` is allowed.

**Rationale:** The user explicitly does not want archive contents rejected. Inspecting archive contents would add CPU, memory, parser, and zip-bomb concerns that are outside this request.

### 4. Shared denied-extension list

**Decision:** Use the same denied extension list in frontend and backend:

```text
.py .pyw
.java .class .jar
.js .mjs .cjs .jsx .ts .tsx
.sh .bash .zsh .fish
.ps1 .bat .cmd
.php .rb .pl .lua
.go .rs .c .cc .cpp .cxx .h .hpp
.cs .kt .kts .swift
.exe .dll .so .dylib
```

**Rationale:** Keeping one explicit list per runtime avoids ambiguous wildcard logic and makes tests straightforward. The lists should remain textually aligned through tests and comments.

### 5. User-facing error behavior

**Decision:** The frontend rejects blocked files before `chatApi.uploadFile` and shows a localized error message. The backend returns HTTP 400 with a stable detail message.

**Rationale:** Users get immediate feedback in the common path, while API callers receive a predictable failure. Existing upload components already handle `onError` and notification flows.

## Risks / Trade-offs

- [Extension policy can be bypassed by renaming a file] → This is acceptable for this requirement; deeper content inspection is explicitly out of scope.
- [Frontend and backend extension lists may drift] → Cover representative blocked and allowed cases in both frontend and backend tests; keep the list in a named constant in each runtime.
- [Some legitimate developer documentation files may be blocked] → The requested safer scope intentionally blocks source code extensions in chat attachments. Users can upload archives when they need to share code bundles.
- [Binary library extensions may be platform-specific] → The denied list covers common executable and shared library suffixes; future additions can extend the list without changing the API contract.
