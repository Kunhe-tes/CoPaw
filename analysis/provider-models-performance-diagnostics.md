# Provider Models API Performance Diagnostics

Date: 2026-06-15

## Scope

This note records the diagnostic plan for slow provider model APIs:

- `GET /api/models`
- `GET /api/models/active?scope=xxx&agent_id=xxx`

The observed production symptom is that these two APIs repeatedly take
6-9 seconds while other APIs are around 100 ms. The current conclusion is not
that tenant/source double parsing is the proven root cause. Double parsing is a
confirmed correctness/cache-key issue, but repeated 6-9 second latency still
requires production evidence.

## Instrumentation Added

Slow logs are emitted only when a measured segment takes at least 500 ms.

### `provider_manager_dependency_slow`

Emitted from `get_provider_manager()` when dependency resolution is slow.

Important fields:

- `path`: request path.
- `total_ms`: total time spent in provider manager dependency resolution.
- `resolve_ms`: tenant/source/scope resolution time.
- `ensure_ms`: time spent in `ProviderManager.ensure_tenant_provider_storage(...)`.
- `get_instance_ms`: time spent in `ProviderManager.get_instance(...)`.
- `route_tenant_id`: tenant id after router-level storage resolution.
- `provider_tenant_id`: tenant id after ProviderManager-level resolution.
- `manager_tenant_id`: tenant id on the returned manager instance.
- `source_id`: request source id.
- `scope_id`: request scope id.
- `cache_hit_before`: whether the provider manager instance existed before
  `get_instance`.
- `cache_hit_after`: whether the returned manager is now in the instance cache.
- `root_path`: provider storage path used by ProviderManager.
- `root_exists`: whether that provider storage path exists.

### `provider_list_info_slow`

Emitted from `GET /api/models` when `manager.list_provider_info()` is slow.

Important fields:

- `tenant_id`: manager tenant id.
- `duration_ms`: time spent listing provider info.
- `provider_count`: number of providers returned.
- `custom_count`: number of custom providers loaded.
- `root_path`: provider storage path.

### `provider_active_model_read_slow`

Emitted from `GET /api/models/active` when the handler body is slow after
dependency injection.

Important fields:

- `tenant_id`: manager tenant id.
- `duration_ms`: time spent reading the active model from the manager.
- `scope`: request scope query value.
- `root_path`: provider storage path.

## How To Interpret Logs

### Dependency Resolution Is Slow

If `provider_manager_dependency_slow.total_ms` is high, the latency is before
the endpoint body. This explains both `/api/models` and `/api/models/active`.

Use the segment fields:

- `ensure_ms` high:
  - Provider storage existence checks are slow.
  - Provider storage initialization/copy is slow.
  - File lock wait is slow.
  - Storage path may be on slow PVC/NFS/object-backed volume.
  - `root_exists=false` with repeated requests suggests repeated failed or
    ineffective initialization.

- `get_instance_ms` high:
  - ProviderManager cache missed.
  - Constructor work is slow: directory creation, provider JSON loads,
    `active_model.json`, legacy tenant model recovery, capability annotation,
    or mtime snapshot.
  - If `cache_hit_before=false` repeats for the same logical request identity,
    investigate unstable effective tenant keys or process restarts.

- `resolve_ms` high:
  - Tenant/source/scope parsing itself is unexpectedly slow.
  - This is less likely because local reproduction shows this path is normally
    tiny.

### Tenant Key Mismatch Is Present

Compare:

- `route_tenant_id`
- `provider_tenant_id`
- `manager_tenant_id`

If these differ, router-level storage resolution and ProviderManager-level
resolution are not idempotent for the request. A known example is:

- raw identity: `tenant=default`, `source=RMASSIST`
- expected storage key: `default_RMASSIST`
- double-resolved key: an encoded scope for `default_RMASSIST + RMASSIST`

This confirms the double parsing/correctness issue. It does not by itself prove
6-9 second latency unless paired with repeated cache misses, slow storage,
directory initialization, or lock waits.

### `/api/models` Is Slow But `/api/models/active` Is Not

If only `provider_list_info_slow` appears, while
`provider_manager_dependency_slow` does not, the likely cause is inside
`list_provider_info()`:

- `_refresh_if_stale()` does per-request filesystem checks.
- Custom provider directory scanning may be slow.
- Provider JSON count or storage latency may be high.

Production follow-up:

- Count files under `{root_path}/custom/*.json`.
- Check storage latency for `stat`, `glob`, and small JSON reads.
- Check whether provider files are being modified frequently, causing reloads.

### `/api/models/active` Handler Body Is Slow

If `provider_active_model_read_slow` appears, this is abnormal because
`manager.get_active_model()` should be an in-memory read.

Likely interpretations:

- The event loop was blocked by another synchronous operation before the handler
  resumed.
- Logging timestamps around dependency and handler execution need correlation.
- The process is under CPU starvation or global interpreter/thread contention.

This log should be rare. If it appears consistently, inspect concurrent slow
logs in the same time window.

## Production Log Collection Checklist

When the issue reproduces in production, collect logs around the same time
window for these strings:

- `provider_manager_dependency_slow`
- `provider_list_info_slow`
- `provider_active_model_read_slow`
- `Initializing provider config`
- `Provider config initialized`
- `Waiting for concurrent provider initialization`
- `Failed to initialize provider config`
- `ensure_bootstrap duration_ms`
- `bootstrap_fast_path_hit`
- `bootstrap_fast_path_miss`

For each slow request, preserve the full line. The key fields needed for root
cause analysis are:

- path
- total_ms
- ensure_ms
- get_instance_ms
- route_tenant_id
- provider_tenant_id
- manager_tenant_id
- source_id
- scope_id
- cache_hit_before
- root_path
- root_exists

## Current Working Hypotheses

These remain hypotheses until production logs confirm them:

1. Provider storage key is double-resolved or unstable, causing repeated cache
   misses or wrong provider directories.
2. Provider storage is on slow production storage, making synchronous
   `exists/stat/glob/copytree` operations block the single Uvicorn worker.
3. Concurrent frontend requests to `/api/models` and `/api/models/active`
   amplify ProviderManager initialization or lock waits.
4. `/api/models` has an additional per-request filesystem scan via
   `_refresh_if_stale()`.

The next analysis step should start from production log lines, not from another
speculative code change.
