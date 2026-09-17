# Broadcast Child Dispatch Synchronization Fix

## Scope

- Keep the gateway and existing cron API contracts unchanged.
- After a broadcast, strictly synchronize the selected tenants and previously known child tenants.
- Continue discovering other existing child tenants so a global parent-mode change reaches earlier broadcasts.
- During a standalone dispatch-mode change, continue discovering existing children across the source tenant list.
- Treat an unavailable tenant during broad discovery as an incomplete scan, not as a task-level failure.
- Keep failures while updating a discovered child, or while synchronizing an explicit broadcast target, as blocking failures.
- Preserve unrelated Worker capacity carousel changes already present in the worktree.

## Impact Boundary

- `broadcast_job` passes the normalized broadcast targets into the post-broadcast synchronization path.
- `_apply_batch_dispatch_after_broadcast` and `_synchronize_dispatch_broadcast_children` forward the optional target scope.
- `_process_dispatch_broadcast_children` distinguishes strict explicit/known-child synchronization from best-effort tenant discovery.
- The cron API response models, gateway routing, persistence schema, and frontend request shapes do not change.
- GitNexus could not resolve the newly introduced symbols or route and returned `UNKNOWN`; direct call-site inspection found only broadcast, mode-toggle, and startup reconciliation callers.

## Implementation Steps

1. Add a failing endpoint regression test where the selected broadcast tenant is available but an unrelated logical tenant is not.
2. Add focused processing tests for best-effort discovery and strict explicit-target failure behavior.
3. Thread explicit tenant IDs through the post-broadcast synchronization path and merge them with known-child snapshots.
4. Discover remaining logical tenants on a best-effort basis, track unavailable discovery tenants separately from real child-update failures, and persist the partial-scan summary.
5. Run focused backend tests, lint/format checks for edited Python files, broader cron tests as feasible, and GitNexus change detection.

## Verification

- Red: the broadcast task currently fails with `failed to synchronize broadcast child dispatch mode` when an unrelated logical tenant cannot resolve a workspace.
- Green: the same broadcast completes, its selected tenant is synchronized strictly, and unrelated unavailable tenants do not poison standalone discovery.
- `& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_tenant_cron_api.py -k "broadcast_applies_batch_dispatch_after_distribution or dispatch_child_processing"`
- `& .\.venv\Scripts\python.exe -m pytest tests/unit/app/test_tenant_cron_api.py`
- Python lint/format verification for `src/swe/app/crons/api.py` and `tests/unit/app/test_tenant_cron_api.py` using the repository's configured tools.
- GitNexus `detect_changes` for the final uncommitted diff.

## Complexity Follow-up

1. Preserve the existing broadcast-child synchronization tests as the behavior
   contract and reproduce the complexity failure with `mccabe --min 16`.
2. Extract tenant snapshot/discovery resolution from
   `_process_dispatch_broadcast_children` without changing its arguments,
   return value, persistence calls, or strict-versus-best-effort semantics.
3. Re-run the focused processing and broadcast endpoint tests, then verify the
   orchestration function no longer appears in `mccabe --min 16` output.
4. Run Python formatting/lint checks available in the workspace and GitNexus
   `detect_changes` before handoff.
