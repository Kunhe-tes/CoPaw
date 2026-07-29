## Why

External user information now supplies branch identifiers that may be
secondary branch BBK IDs. The operational analytics tables still aggregate and
display data by primary branch. If secondary IDs are stored directly, Monitor
pages can show raw numeric branch IDs instead of primary branch names and the
same primary branch can be split across multiple BBK IDs.

## What Changes

- Add shared SWE and Monitor Python BBK helpers that normalize any known
  secondary branch BBK ID to its primary branch BBK ID.
- Preserve known primary branch BBK IDs unchanged.
- Leave unknown BBK IDs unchanged and log a warning so ingestion does not lose
  data.
- Normalize `bbk_id` before new writes to:
  - `swe_tracing_traces`
  - `swe_tracing_spans`
  - `swe_cron_jobs`
  - `swe_tenant_init_source`
- Keep historical data migration out of scope.
- Keep Console mapping changes out of scope.

## Impact

- SWE BBK utility and tracing store writes.
- SWE tenant init source insert/update writes.
- Monitor BBK utility and cron job sync writes.
- Existing Monitor query code continues to display primary branch names from
  stored primary branch IDs.
