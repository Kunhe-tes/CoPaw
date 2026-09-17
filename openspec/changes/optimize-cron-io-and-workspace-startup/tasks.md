## 1. Repository Nonblocking I/O Tests

- [x] 1.1 Add `JsonJobRepository.load()` test proving blocking read/parse/model validation is delegated through a thread boundary.
- [x] 1.2 Add `JsonJobRepository.save()` test proving dump/write/atomic replace is delegated through a thread boundary and persists the existing JSON format.
- [x] 1.3 Add `JsonJobRepository.get_job()` cache test proving repeated lookup with unchanged file signature does not reload the full file.
- [x] 1.4 Add cache invalidation test proving changed `jobs.json` signature refreshes the snapshot and job index.
- [x] 1.5 Add failure test proving invalid `jobs.json` raises and does not return stale cached data.

## 2. Repository Nonblocking I/O Implementation

- [x] 2.1 Run GitNexus impact for `JsonJobRepository.load`, `JsonJobRepository.save`, and `JsonJobRepository.get_job` before editing those symbols.
- [x] 2.2 Extract synchronous load/save helpers inside `src/swe/app/crons/repo/json_repo.py`.
- [x] 2.3 Implement `asyncio.to_thread()` wrapping for load/save helpers.
- [x] 2.4 Add file signature snapshot state and job id index to `JsonJobRepository`.
- [x] 2.5 Override `JsonJobRepository.get_job()` to use the cached index when the file signature is unchanged.
- [x] 2.6 Update snapshot state after successful `save()` and leave cache unchanged on failed load/save.

## 3. Dream Cron File Processing

- [x] 3.1 Add tests covering dream log reads and archive maintenance are called through a worker thread boundary.
- [x] 3.2 Run GitNexus impact for `CronManager._load_dream_logs`, `_load_dream_record_ids`, `_dual_write_dream_records`, and `run_dream`.
- [x] 3.3 Split dream log loading into an async wrapper and synchronous helper.
- [x] 3.4 Update `_load_dream_record_ids()` and `_dual_write_dream_records()` to await the async dream log loader.
- [x] 3.5 Wrap `run_dream_archive_maintenance()` with `asyncio.to_thread()` in `run_dream()`.

## 4. Workspace Startup Concurrency Tests

- [x] 4.1 Add a same-cache-key concurrency test proving concurrent `get_agent()` calls start exactly one workspace and return the same instance.
- [x] 4.2 Add a different-cache-key concurrency test proving one slow startup does not block another cache key behind the global manager lock.
- [x] 4.3 Add a cache-hit test proving existing cached workspace returns without creating an inflight startup task.
- [x] 4.4 Add a startup-failure test proving all waiters receive the error and a later call can retry.
- [x] 4.5 Add a race test proving a duplicate workspace created after another instance is cached is stopped and not stored.

## 5. Workspace Startup Concurrency Implementation

- [x] 5.1 Run GitNexus impact for `MultiAgentManager.get_agent` and report the HIGH risk before editing.
- [x] 5.2 Add per-cache-key inflight startup tracking to `MultiAgentManager`.
- [x] 5.3 Refactor `get_agent()` so the global lock protects only cache and inflight dictionaries.
- [x] 5.4 Move configuration load, `Workspace` construction, and `await instance.start()` outside the global lock.
- [x] 5.5 Ensure successful startup atomically stores one workspace instance and cleans up duplicate instances on races.
- [x] 5.6 Ensure startup failure clears inflight state and preserves existing exception behavior.

## 6. Verification

- [x] 6.1 Run targeted repository tests for cron JSON repository behavior.
- [x] 6.2 Run targeted cron manager dream/heartbeat tests affected by async dream log loading.
- [x] 6.3 Run lazy loading and multi-agent manager tests affected by `get_agent()` locking.
- [x] 6.4 Run `venv/bin/python -m pytest tests/unit/app -k "cron or lazy_loading or multi_agent" -q` or a narrower passing equivalent if collection cost is too high.
- [x] 6.5 Run GitNexus `detect_changes()` and confirm changed symbols and affected flows match this OpenSpec change.
- [x] 6.6 Update `analysis/playbook/` with the event-loop-lag mitigation note if implementation findings add new reusable troubleshooting guidance.
