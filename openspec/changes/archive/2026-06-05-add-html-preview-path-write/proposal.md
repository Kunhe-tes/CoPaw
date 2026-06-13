## Why

Callers currently need to publish HTML preview content, but `/assets/text/write` generates the final file name only when content is written. This makes it hard for upstream systems to reserve or pass around a preview URL before the HTML body is ready.

## What Changes

- Add a new internal API in `src/swe/app/routers/internal.py` that accepts `user_id` and `source_id`, resolves the runtime scope, creates a safe `.html` preview file containing `文件正在生成中`, and returns the corresponding public preview URL.
- Extend `/assets/text/write` so callers can optionally pass the URL/path produced by the new internal API.
- Update the write implementation so, when a generated preview URL/path is provided, it writes content to that exact static file instead of generating another file name.
- Preserve the current `/assets/text/write` behavior for callers that do not provide a generated preview URL/path.
- Validate that supplied preview URL/path values point to the expected tenant/source static preview location before writing.

## Capabilities

### New Capabilities
- `html-preview-path-write`: reserve HTML preview URLs for a tenant/source scope and write text content into the reserved static file through `/assets/text/write`.

### Modified Capabilities
- None.

## Impact

- Backend:
  - New internal route in `src/swe/app/routers/internal.py`.
  - Initial placeholder HTML creation during preview path generation.
  - Request/response model changes for the text write API.
  - Shared validation for converting a generated public preview URL/path back to a static file path.
- API compatibility:
  - Existing `/assets/text/write` callers remain supported because the new path field is optional.
- Tests:
  - New coverage for preview path generation, placeholder HTML creation, scoped path validation, write-to-reserved-path behavior, and legacy generated-name write behavior.
