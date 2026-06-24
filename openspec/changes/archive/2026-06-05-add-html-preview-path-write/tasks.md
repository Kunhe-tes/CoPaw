## 1. Tests

- [x] 1.1 Add route tests for successful internal HTML preview path generation with valid `user_id` and `source_id`
- [x] 1.2 Add tests showing preview path generation creates an HTML file containing `文件正在生成中`
- [x] 1.3 Add write tests showing `/assets/text/write` overwrites the initialized placeholder file for a supplied generated preview URL or static path
- [x] 1.4 Add regression tests showing `/assets/text/write` keeps generating a new file when no preview target is supplied
- [x] 1.5 Add validation tests for cross-scope preview targets, path traversal, non-HTML names, and invalid identities

## 2. API Models And Route

- [x] 2.1 Add request and response models for the internal preview path generation API
- [x] 2.2 Add the internal preview path route in `src/swe/app/routers/internal.py` using the existing internal token guard
- [x] 2.3 Create the target static directory and initialized HTML file containing `文件正在生成中`
- [x] 2.4 Return `file_name`, `scope_id`, `public_url`, and route-relative `static_path` from the preview path route

## 3. Write Path Implementation

- [x] 3.1 Extend the text write request model with an optional preview target field
- [x] 3.2 Add helper logic to normalize a generated public URL or `/static/...` path into a validated static file target
- [x] 3.3 Update the write helper to overwrite the supplied initialized target when present and preserve generated-name behavior when absent
- [x] 3.4 Ensure target directories are created on demand and returned write responses match the chosen target

## 4. Verification

- [x] 4.1 Run the focused router tests for internal text asset APIs
- [x] 4.2 Run formatting or lint checks required for the touched Python files
- [x] 4.3 Run `gitnexus_detect_changes()` before any commit to confirm affected symbols match the expected route/helper scope
