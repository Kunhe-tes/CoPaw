## 1. Backend Contract

- [x] 1.1 Run GitNexus impact analysis before editing existing backend symbols touched by this change.
- [x] 1.2 Add request/response models for the system-check cron auth expiry batch API.
- [x] 1.3 Add manager/admin authorization for the new system-check API.
- [x] 1.4 Implement tenant and source identity validation for the batch request.
- [x] 1.5 Implement strict `cron_auth.json` lookup that resolves each logical tenant through the submitted `source_id`.
- [x] 1.6 Classify tenant results as `valid`, `expired`, `missing_file`, `invalid_content`, or `unknown` without returning secrets or file paths.
- [x] 1.7 Register the new backend route under `/api/system-check/cron-auth-expiry`.

## 2. Frontend Page

- [x] 2.1 Add Console API types and request helper for the auth expiry self-check.
- [x] 2.2 Add the "系统自检" route and page shell.
- [x] 2.3 Add manager/admin-only navigation entry and direct-access 403 state.
- [x] 2.4 Implement the "鉴权过期查询" form with `source_id` defaulting to `RMASSIST`.
- [x] 2.5 Parse manually entered tenant IDs from newline, comma, Chinese comma, space, or semicolon separators and de-duplicate them.
- [x] 2.6 Render results in a table with tenant ID, source ID, status, expiry time, expired flag, and message columns.
- [x] 2.7 Preserve form inputs and show an error message when the query fails.

## 3. Tests

- [x] 3.1 Add backend unit tests for manager/admin authorization and unauthorized rejection.
- [x] 3.2 Add backend unit tests for source/tenant validation and source-scoped path resolution.
- [x] 3.3 Add backend unit tests for all result statuses, including missing file and invalid content.
- [x] 3.4 Add frontend tests for manager rendering, non-manager 403 behavior, form validation, tenant parsing, successful table rendering, and failed query handling.

## 4. Verification

- [x] 4.1 Run targeted backend tests with `venv/bin/python -m pytest`.
- [x] 4.2 Run targeted Console tests with the repository's existing Console test command.
- [x] 4.3 Run `openspec status --change add-system-check-auth-expiry` and confirm the change is apply-ready.
- [x] 4.4 Run `gitnexus_detect_changes()` before committing or handing off implementation changes.
