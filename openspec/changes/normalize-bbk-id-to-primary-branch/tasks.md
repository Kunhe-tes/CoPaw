## 1. OpenSpec

- [x] 1.1 Capture the primary-branch BBK normalization behavior and scope.
- [x] 1.2 Exclude historical migration and Console mapping work from this change.

## 2. BBK Utilities

- [x] 2.1 Update `src/swe/utils/bbk.py` with primary branch mappings and secondary-to-primary normalization.
- [x] 2.2 Update `monitor/src/monitor/utils/bbk.py` with the same Python helper behavior.

## 3. Write Path Normalization

- [x] 3.1 Normalize `bbk_id` before SWE tracing writes to `swe_tracing_traces`.
- [x] 3.2 Normalize `bbk_id` before SWE tracing writes to `swe_tracing_spans`.
- [x] 3.3 Normalize `bbk_id` before SWE tenant init source insert/update writes.
- [x] 3.4 Normalize `bbk_id` before Monitor cron sync writes to `swe_cron_jobs`.

## 4. Verification

- [x] 4.1 Review changed files for targeted scope.
- [x] 4.2 Defer runtime tests to the internal environment per request.
