## Why

Managers need a quick way to verify whether selected tenants under a source can still run cron jobs with valid stored authorization. Today the relevant state is buried in each tenant's `cron_auth.json`, so checking a batch of tenants requires manual filesystem access and risks inspecting the wrong source-scoped directory.

## What Changes

- Add a manager-only Console page named "系统自检".
- Add an initial "鉴权过期查询" check on that page.
- Let managers manually enter a `source_id` defaulting to `RMASSIST` and a batch of tenant IDs.
- Add a read-only backend API that resolves each logical `tenant_id` with the requested `source_id`, reads the tenant's `cron_auth.json`, and returns a normalized status for table display.
- Distinguish missing auth files from invalid or unreadable auth file contents.
- Do not expose stored cookies, auth tokens, user info payloads, or local filesystem paths in the API response.

## Capabilities

### New Capabilities
- `system-check-auth-expiry`: Manager-only system self-check page and API for batch cron auth expiry inspection.

### Modified Capabilities

## Impact

- Backend: new route/service for system self-check auth expiry lookup, using source-scoped tenant path resolution.
- Frontend: new Console page, route, navigation entry, API module/types, and manager/admin access handling.
- Tests: backend unit tests for status classification and authorization; frontend tests for 403 behavior, form submission, and table rendering.
- Security: cross-tenant state inspection is limited to `manager`/`admin` callers and returns only diagnostic metadata.
