# Scope Tools And Cron Model Design

## Summary

This change adds two internal HTTP tool endpoints for converting runtime scope IDs and extends the `copaw cron` CLI so callers can choose an execution model in the same way the scheduled task configuration page already does.

The design intentionally reuses existing behavior:

- Scope encoding and decoding continue to use the current canonical runtime scope rules.
- Cron model selection continues to use `model_slot`.
- Cron execution, validation, and fallback behavior remain unchanged.

## Goals

- Expose scope ID encode and decode as callable HTTP interfaces for internal system integration.
- Support both single-item and batch scope conversion requests.
- Add optional cron CLI model arguments that produce the same `model_slot` behavior as the console scheduled task page.
- Keep implementation small by reusing existing router, validation, and execution paths.

## Non-Goals

- No new public API namespace; the endpoints stay under `/internal`.
- No change to the existing human-readable output format of `scripts/decode_scope_ids.py` and `scripts/encode_scope_ids.py`.
- No UI change for cron jobs; the console already supports execution model selection.
- No new CLI flag for explicitly clearing an existing cron `model_slot`.
- No change to cron executor fallback semantics or model validation rules.

## Existing Context

### Scope conversion

Two scripts already implement the required conversion logic:

- `scripts/encode_scope_ids.py`
- `scripts/decode_scope_ids.py`

Those scripts already support:

- Single-item conversion
- Batch conversion
- Validation of invalid empty inputs
- Rejection of legacy `scope.v1.` decode input

The runtime scope implementation lives in `swe.config.context`, especially:

- `encode_scope_id`
- `decode_scope_id`
- `canonicalize_scope_id`
- `resolve_scope_id`

### Cron model selection

The console cron page already reads and writes `model_slot`:

- `console/src/pages/Control/CronJobs/helpers.ts`
- `console/src/pages/Control/CronJobs/components/JobDrawer.tsx`

The backend already supports this field:

- `src/swe/app/crons/models.py` defines `model_slot`
- `src/swe/app/crons/api.py` validates `model_slot`
- `src/swe/app/crons/executor.py` resolves the effective execution model and falls back to the tenant default when needed

The CLI currently builds cron payloads without any way to set `model_slot` through inline arguments.

## Design Decisions

### 1. Use the existing internal router

The new scope conversion APIs will be added to `src/swe/app/routers/internal.py`.

Reasons:

- This is the existing home for internal service-to-service helper APIs.
- It already has the internal token verification pattern used by this class of endpoints.
- It avoids introducing a new router namespace for only two small endpoints.

### 2. Reuse canonical scope conversion logic

The HTTP endpoints must not reimplement scope conversion rules.

They should call shared conversion helpers that ultimately use:

- `encode_scope_id`
- `decode_scope_id`

The scripts and the HTTP endpoints should share the same conversion and validation semantics so the project has one behavioral source of truth.

### 3. Keep cron model selection mapped to `model_slot`

The CLI will expose:

- `--model-provider`
- `--model`

These arguments map directly to:

```json
{
  "model_slot": {
    "provider_id": "<provider>",
    "model": "<model>"
  }
}
```

No new cron field will be introduced.

### 4. Match console semantics

The console scheduled task page uses the following model behavior:

- If no model is specified, the job uses the tenant default model.
- If a model is specified, the job uses an explicit `model_slot`.
- Only agent jobs use `model_slot`.
- Text jobs do not retain `model_slot`.

The CLI will follow the same rules.

## API Design

## `POST /internal/scope/encode`

Encodes logical `tenant_id` and `source_id` pairs into canonical runtime `scope_id` values.

### Request shapes

Single item:

```json
{
  "tenant_id": "tenant-a",
  "source_id": "feishu"
}
```

Batch:

```json
{
  "items": [
    {
      "tenant_id": "tenant-a",
      "source_id": "feishu"
    },
    {
      "tenant_id": "tenant-b",
      "source_id": "dingtalk"
    }
  ]
}
```

### Success responses

Single item:

```json
{
  "success": true,
  "item": {
    "tenant_id": "tenant-a",
    "source_id": "feishu",
    "scope_id": "..."
  }
}
```

Batch:

```json
{
  "success": true,
  "items": [
    {
      "tenant_id": "tenant-a",
      "source_id": "feishu",
      "scope_id": "..."
    },
    {
      "tenant_id": "tenant-b",
      "source_id": "dingtalk",
      "scope_id": "..."
    }
  ]
}
```

### Validation rules

- Accept exactly one request shape: single item or batch.
- Reject mixed input that includes both top-level single fields and `items`.
- Reject empty strings.
- Reject an empty `items` list.
- Return `400` with the standard internal error payload:

```json
{
  "detail": "..."
}
```

## `POST /internal/scope/decode`

Decodes canonical runtime `scope_id` values into logical `tenant_id` and `source_id`.

### Request shapes

Single item:

```json
{
  "scope_id": "..."
}
```

Batch:

```json
{
  "scope_ids": ["...", "..."]
}
```

### Success responses

Single item:

```json
{
  "success": true,
  "item": {
    "scope_id": "...",
    "tenant_id": "tenant-a",
    "source_id": "feishu"
  }
}
```

Batch:

```json
{
  "success": true,
  "items": [
    {
      "scope_id": "...",
      "tenant_id": "tenant-a",
      "source_id": "feishu"
    },
    {
      "scope_id": "...",
      "tenant_id": "tenant-b",
      "source_id": "dingtalk"
    }
  ]
}
```

### Validation rules

- Accept exactly one request shape: single item or batch.
- Reject mixed input that includes both top-level single fields and `scope_ids`.
- Reject empty strings.
- Reject an empty `scope_ids` list.
- Reject legacy `scope.v1.` values.
- Reject malformed canonical scope payloads.
- Return `400` with the standard internal error payload:

```json
{
  "detail": "..."
}
```

## Authentication

Both endpoints use the existing internal token pattern already used by `internal.py`.

- If `SWE_INTERNAL_TOKEN` is configured, the caller must send `Authorization: Bearer <token>`.
- If it is not configured, the router behaves the same as the existing internal endpoints.

## CLI Design

The cron CLI inline create and update commands will gain:

- `--model-provider`
- `--model`

## Parameter rules

- The two flags must be provided together.
- Supplying only one of them is a CLI usage error.
- The flags are optional.

## Create behavior

For `copaw cron create`:

- If neither flag is provided, do not set `model_slot`.
- If both flags are provided and `task_type=agent`, set:

```json
{
  "model_slot": {
    "provider_id": "<provider>",
    "model": "<model>"
  }
}
```

- If both flags are provided and `task_type=text`, do not persist `model_slot`.

This matches the console behavior where only agent jobs use execution model selection.

## Update behavior

For `copaw cron update`:

- If neither flag is provided, preserve the existing `model_slot`.
- If both flags are provided and the effective task type is `agent`, replace the existing `model_slot`.
- If both flags are provided and the effective task type is `text`, clear `model_slot` from the updated payload.

This mirrors the current console submit behavior where text jobs do not keep a model selection.

## No explicit clear flag in this change

This design does not add a dedicated flag like `--clear-model-slot`.

Reason:

- The requirement is to add optional model inputs and match the console’s model behavior.
- Explicit clear semantics for update introduce a separate state-management concern.
- It can be added later without blocking the current scope.

## Error Handling

### Scope endpoints

- Invalid request shapes return `400`.
- Invalid identifiers return `400`.
- Legacy scope decode input returns `400`.

### Cron CLI

- Missing one half of the provider/model pair returns `click.UsageError`.
- Backend validation remains authoritative for provider/model existence.
- Existing API behavior is unchanged:
  - Unknown provider returns `404`
  - Unknown model under a known provider returns `400`

## Files Expected To Change

### New or refactored shared scope conversion logic

One small shared helper module may be added if needed so the scripts and HTTP router use the same behavior.

Candidate locations:

- `src/swe/app/routers/internal.py` local helper functions if reuse is trivial
- or a small shared module under `src/swe/config/` or `src/swe/app/routers/` if that produces cleaner reuse

The final implementation should choose the smallest option that avoids duplicate conversion logic.

### Router changes

- `src/swe/app/routers/internal.py`

### CLI changes

- `src/swe/cli/cron_cmd.py`

### Tests

- Router tests near existing internal router coverage
- CLI tests near existing cron CLI coverage

### Docs

- `website/public/docs/cli.zh.md`
- `website/public/docs/cli.en.md`

## Testing Strategy

### Scope endpoint tests

Add tests for:

- encode single success
- encode batch success
- encode mixed single-and-batch rejection
- encode empty field rejection
- encode empty batch rejection
- decode single success
- decode batch success
- decode legacy `scope.v1.` rejection
- decode malformed scope rejection

### Cron CLI tests

Add tests for:

- create agent job with provider/model produces `model_slot`
- create text job ignores provider/model and omits `model_slot`
- create with only one of the two flags raises `UsageError`
- update without provider/model preserves existing `model_slot`
- update with provider/model replaces existing `model_slot`
- update to text job clears `model_slot`

## Documentation updates

Update CLI documentation and examples so the new flags are discoverable and use the real parameter names.

## Risks And Tradeoffs

### Internal route naming

Using `/internal` is slightly less semantically pure than adding a new dedicated namespace, but it keeps the API surface small and aligned with how the project already exposes internal-only helper endpoints.

### CLI update clear semantics

This design intentionally does not support explicitly clearing an existing agent job’s `model_slot` while remaining an agent job. That avoids ambiguous meaning for omitted optional flags. If users need that later, a dedicated clear flag should be added explicitly.

### Shared helper placement

The implementation should avoid over-engineering a new abstraction layer just for two endpoints. Shared conversion logic is important, but the chosen location should remain small and obvious.

## Approved Decisions

The following decisions were explicitly confirmed during design:

- Use HTTP API, not MCP tool or CLI subcommand, for the external scope conversion interface.
- Support batch conversion in addition to single-item conversion.
- Place the new endpoints on the existing `internal` router.
- Use `--model-provider` and `--model` as the new cron CLI inputs.
- Match console model behavior by writing `model_slot` only for agent jobs and using tenant default behavior when unset.
