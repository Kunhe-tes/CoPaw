## 1. Runtime Env Helper

- [x] 1.1 Add backend env key validation for portable env names and reserved/protected names.
- [x] 1.2 Add a shared helper that loads all env values from an explicit or context-derived runtime scope `.secret/envs.json`.
- [x] 1.3 Add a runtime env builder that merges process env, tenant env, and optional call-specific env with documented precedence.
- [x] 1.4 Add final protected-key filtering for tenant env and tenant-controlled call-specific env, including `SWE_WORKING_DIR`, `SWE_SECRET_DIR`, `PATH`, `HOME`, `SHELL`, `BASH_ENV`, `ENV`, `ZDOTDIR`, `IFS`, `CDPATH`, `PYTHONPATH`, `PYTHONHOME`, `LD_LIBRARY_PATH`, and `DYLD_LIBRARY_PATH`.
- [x] 1.5 Ensure helper behavior does not mutate process-global `os.environ`.
- [x] 1.6 Ensure env store writes preserve secret directory/file permissions and use atomic replacement semantics.
- [x] 1.7 Add unit tests for key validation, merge precedence, protected-key filtering from both tenant and call-specific env, missing tenant context behavior, source-scoped env lookup, and atomic write behavior.
- [x] 1.8 Register injected tenant env values with the available tracing/logging redaction mechanism without logging raw values.

## 2. Shell Execution Integration

- [x] 2.1 Update shell subprocess env construction to use the shared runtime env builder.
- [x] 2.2 Preserve existing active-Python PATH behavior and Python runtime path guard behavior after tenant env merge.
- [x] 2.3 Ensure path-boundary validation still happens before subprocess creation and before tenant env injection is observable.
- [x] 2.4 Add shell tests proving commands can read tenant env values and cannot receive env when boundary validation rejects execution.

## 3. Hook Runtime Integration

- [x] 3.1 Update command hook handler env construction to use the shared runtime env builder.
- [x] 3.2 Preserve `handler.env` as a call-specific override over persisted tenant env values.
- [x] 3.3 Add hook runtime tests for tenant env injection, handler env override precedence, and no process-global env mutation.

## 4. MCP Stdio Integration

- [x] 4.1 Update tenant-aware MCP stdio launch config construction to merge tenant runtime env with MCP client config env.
- [x] 4.2 Preserve MCP client config env as a call-specific override over persisted tenant env values.
- [x] 4.3 Ensure rebuilt MCP stdio clients receive the same merged env semantics as initial clients.
- [x] 4.4 Ensure MCP stdio launch paths pass explicit runtime scope or execute under bound tenant context so startup/rebuild does not accidentally use default env.
- [x] 4.5 Add MCP stdio tests for tenant env injection, client env override precedence, protected-key filtering, missing context behavior, and rebuild behavior.

## 5. Tool Integration Env References

- [x] 5.1 Define and implement explicit tenant env reference syntax for MCP HTTP headers or similar tool integration auth references.
- [x] 5.2 Preserve existing literal header/env values while resolving explicit tenant env references from the current runtime scope.
- [x] 5.3 Add tests proving MCP HTTP/header env references resolve from tenant env without requiring `os.environ` mutation and remain source-scoped.

## 6. API And Console Semantics

- [x] 6.1 Confirm `/api/envs` continues to write only the current request scope and ignores any target-tenant fields in the request body.
- [x] 6.2 Add or update backend tests proving same logical tenant with different sources uses separate env stores.
- [x] 6.3 Change normal env list responses to return masked values or metadata by default.
- [x] 6.4 Add update semantics that let the console preserve unchanged secrets without reading full values or submitting masked placeholders as literal values.
- [x] 6.5 Keep v1 ordinary read/edit flows write-only or masked after save; do not add a routine full-value reveal path.
- [x] 6.6 Add a separate manager/internal target-scope env write API with explicit target tenant, source identity, validation, audit metadata, and tests.
- [x] 6.7 Ensure non-privileged callers cannot write env values for arbitrary target tenants.

## 7. Validation

- [x] 7.1 Run targeted tests for env store/router behavior.
- [x] 7.2 Run targeted shell tenant boundary tests.
- [x] 7.3 Run targeted hook runtime tests.
- [x] 7.4 Run targeted MCP stdio tests.
- [x] 7.5 Run targeted MCP HTTP/header env reference tests.
- [x] 7.6 Run `openspec validate tenant-runtime-env-injection --strict`.
