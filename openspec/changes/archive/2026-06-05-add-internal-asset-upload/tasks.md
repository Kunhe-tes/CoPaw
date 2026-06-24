## 1. Impact and Test Setup

- [x] 1.1 Run GitNexus impact analysis for the `internal.py` symbols that will be edited, especially `_validate_asset_file_name`, `_get_asset_file_path`, and the new route handler location.
- [x] 1.2 Add focused router tests for internal asset upload behavior under `tests/unit/routers/`.

## 2. API Implementation

- [x] 2.1 Add an upload response model containing `success`, `file_name`, `asset_path`, and `size`.
- [x] 2.2 Add a helper that validates `UploadFile.filename`, creates `WORKING_DIR / _ASSET_ROOT_DIRNAME`, writes uploaded bytes, and returns response metadata.
- [x] 2.3 Add `POST /internal/assets/upload` to `src/swe/app/routers/internal.py` with existing `X-Internal-Token` verification.

## 3. Verification

- [x] 3.1 Verify successful multipart upload saves bytes under `WORKING_DIR / _ASSET_ROOT_DIRNAME`.
- [x] 3.2 Verify invalid token requests do not write files when `SWE_INTERNAL_TOKEN` is configured.
- [x] 3.3 Verify invalid filenames are rejected and cannot write outside the asset root.
- [x] 3.4 Verify uploading the same filename replaces the previous asset content.
- [x] 3.5 Run the focused pytest file with `venv/bin/python -m pytest`.
