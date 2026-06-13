## Context

Cron authorization state is stored per tenant in `.secret/cron_auth.json` and parsed by `src/swe/app/crons/auth_state.py`. In source-scoped runtime mode, a logical `tenant_id` plus `source_id` resolves to a runtime scope directory; checking the raw logical tenant directory can produce incorrect results for `RMASSIST` or any other source-scoped tenant.

The Console already sends `X-User-Role: manager` or `X-User-Role: admin` for manager contexts, and existing administrative pages use that role contract for access control. The new page is an operational self-check page, not a tenant-facing cron configuration page.

## Goals / Non-Goals

**Goals:**

- Add a Console page named "系统自检" for manager/admin users.
- Implement an initial "鉴权过期查询" check that accepts a `source_id` defaulting to `RMASSIST` and manually entered tenant IDs.
- Return batch results that distinguish valid, expired, unknown, missing file, and invalid content states.
- Resolve every checked tenant through source-scoped runtime identity before reading local auth state.
- Avoid exposing sensitive stored auth material in the API response.

**Non-Goals:**

- Automatically discovering tenant IDs for the check.
- Refreshing or repairing expired authorization state.
- Displaying raw `user_info`, cookies, access tokens, auth tokens, or local file paths.
- Replacing existing cron job management or cron auth configuration flows.
- Adding other system self-check items in this change.

## Decisions

### Decision 1: Add a dedicated system-check route

Use a dedicated backend route such as `POST /api/system-check/cron-auth-expiry` instead of overloading `/api/cron/jobs` or `/api/auth/cron-auth`.

Rationale: the capability is a cross-tenant diagnostic for managers, while existing cron routes are tenant cron management and existing auth routes configure the current workspace's cron auth. A dedicated route keeps the access model and response contract explicit.

Alternative considered: add `POST /api/cron/auth-status/batch`. This would reuse the cron router but makes the endpoint look like normal cron management even though it reads cross-tenant diagnostic state.

### Decision 2: Require manager/admin on both page and API

The Console SHALL hide the navigation entry for non-manager users and render a 403 state on direct access. The backend SHALL reject calls whose `X-User-Role` is not `manager` or `admin`.

Rationale: the endpoint performs cross-tenant state inspection. Frontend hiding alone is not sufficient.

Alternative considered: allow any tenant to query only itself. That does not match the batch operational use case and would complicate the contract with partial authorization semantics.

### Decision 3: Request body source_id overrides the active request source for checked tenants

The API SHALL accept `source_id` in the request body and default the UI field to `RMASSIST`. For each submitted tenant ID, the backend SHALL resolve the runtime tenant scope from that body `source_id`, not from the caller's `X-Source-Id` header.

Rationale: this page is a manager diagnostic tool for a selected source. The Console's default non-iframe `X-Source-Id` may be `default`, and tying the diagnostic to that header would make the `RMASSIST` default misleading.

Alternative considered: only use the request header `X-Source-Id`. This is consistent with current-source config APIs but does not fit the requested source selector for this self-check.

### Decision 4: Classify missing file and invalid content separately

The backend SHALL check file existence before parsing. If the `cron_auth.json` file is absent, the result status is `missing_file`. If the file exists but cannot be read, parsed as JSON, validated as cron auth state, or interpreted for expiry, the result status is `invalid_content`.

Rationale: absence and corrupt/unreadable state require different remediation. Missing means the tenant likely has no cron auth configured; invalid content means stored state may need cleanup or repair.

Alternative considered: collapse both into `not_configured`. That would hide operationally important corruption and parsing failures.

### Decision 5: Return a normalized, non-sensitive response

Each result SHALL include only diagnostic metadata: logical `tenant_id`, requested `source_id`, status, `is_expired`, `user_info_expires_at`, and a short message. It SHALL NOT include path, token, cookie, or `user_info` data.

Rationale: the endpoint reads from secret tenant storage. The page only needs expiry status for operational triage.

## Risks / Trade-offs

- Cross-tenant diagnostics can leak tenant state existence -> mitigate with manager/admin enforcement and minimal response fields.
- Body-level `source_id` differs from current-source-only API patterns -> mitigate by naming the endpoint as system-check and validating `source_id` explicitly.
- Large tenant lists can perform many filesystem reads -> mitigate with input limits and sequential or bounded-concurrency reads.
- `user_info_expires_at` timezone formats may vary -> mitigate by reusing existing datetime parsing/model validation where possible and normalizing output to UTC.
- Existing `load_cron_auth_state()` currently swallows parse errors into state -> the self-check should use a stricter read path or helper so invalid content can be distinguished from missing configuration.
