## Context

`src/swe/app/routers/internal.py` already contains text asset read/write helpers and `/assets/text/write` can publish HTML text into `<WORKING_DIR>/<scope_id>/workspaces/default/static` while returning a public URL. Its current write flow generates the file name at write time.

The new workflow needs a separate internal step that prepares an HTML preview URL before final content exists. That step must create an initial HTML file showing `文件正在生成中`, and a later call to `/assets/text/write` must be able to replace that placeholder content in the same target instead of creating a second file.

## Goals / Non-Goals

**Goals:**

- Add an internal preview path generation API that accepts `user_id` and `source_id`.
- Create an initial HTML file containing `文件正在生成中` when the preview path is generated.
- Return enough data for callers to pass the reserved target into `/assets/text/write`.
- Allow `/assets/text/write` to write to the supplied reserved target.
- Keep the existing write behavior unchanged when no reserved target is supplied.
- Prevent arbitrary file writes by validating that the supplied target maps to the expected tenant/source static directory.

**Non-Goals:**

- No public preview path generation endpoint.
- No new binary upload behavior.
- No file deletion, expiry, listing, or reservation persistence table.
- No change to the public static serving route.

## Decisions

### Decision 1: Add a dedicated internal preview path generation route that creates placeholder HTML

Add a route under the existing internal router, for example `POST /api/internal/assets/text/preview-path`, with the same internal token behavior as other internal endpoints.

Request:

```json
{
  "user_id": "alice",
  "source_id": "portal"
}
```

Response:

```json
{
  "success": true,
  "file_name": "alice-20260525093000123.html",
  "scope_id": "alice__portal",
  "public_url": "http://localhost:8088/static/alice__portal/default/alice-20260525093000123.html",
  "static_path": "/static/alice__portal/default/alice-20260525093000123.html"
}
```

Rationale:
- The route remains service-to-service only.
- Returning both `public_url` and `static_path` lets callers store or display the browser URL while passing a route-relative path if preferred.
- Creating the file immediately makes the generated URL useful as a live preview URL before final content is ready.
- The placeholder text gives users a clear loading state and avoids a temporary 404.

### Decision 2: Extend the write request with an optional generated target

Extend the existing write request model with an optional field such as `preview_url` or `preview_path`. The implementation should accept the generated public URL or its `/static/...` path form, normalize it, and write to that file.

When the optional field is omitted, the current server-generated file name behavior remains unchanged. When the optional field is present, `/assets/text/write` overwrites the placeholder HTML file with the supplied content.

Rationale:
- Existing callers remain compatible.
- The write endpoint stays the single place that writes HTML content.
- Callers do not need to send raw filesystem paths.

### Decision 3: Validate the generated target against the resolved scope

The write endpoint must resolve `scope_id` from `user_id` and `source_id`, then accept only targets that match:

```text
/static/<scope_id>/default/<file_name>.html
```

The file name must pass the same safe-name checks as generated names and must end in `.html`. The normalized destination must remain inside:

```text
<WORKING_DIR>/<scope_id>/workspaces/default/static
```

Rationale:
- `preview_url`/`preview_path` is caller-controlled input at write time.
- Scope validation prevents writing into another user's static directory.
- Path containment validation prevents traversal or arbitrary filesystem writes.

### Decision 4: Share filename and URL builders

Reuse the existing `_generate_text_asset_file_name`, `_build_public_url`, and static directory helpers for both preview generation and content writing. Add a small parser/validator that converts a generated URL/path back into `(scope_id, file_name)`.

Rationale:
- Keeps route behavior consistent.
- Reduces the chance that preview generation and write-time URL validation drift.

## Risks / Trade-offs

- Caller passes a stale or typoed generated URL -> Reject with HTTP 400 and do not create a fallback file, because silently generating a new file would break the preview contract.
- A generated preview URL is never written -> The URL continues to show the placeholder `文件正在生成中`; this avoids 404s but may leave stale placeholder pages without a separate cleanup policy.
- Public URL base changes between generation and write -> Validate against the path component rather than requiring the exact configured host to match.
- Duplicate preview file name collision -> Continue using timestamp-based names with millisecond precision; if the target already exists, write behavior should be explicit in implementation and covered by tests.
