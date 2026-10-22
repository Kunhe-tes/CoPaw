# Managed Execution Model Identity Implementation Plan

> Execute sequentially in the main thread, as required by this repository's AGENTS.md.

**Goal:** Show the task ID in batch members and persist concrete provider/model identities for Agent executions using tenant defaults.

**Architecture:** Resolve the target tenant's model through SWE before Scheduler persists the execution snapshot. Freeze that concrete slot for this execution, leaving the task definition's default-model choice unchanged. Record execution-time fallback identities with the result. Workflow bindings retain their existing resolution; model-free text tasks retain their existing capacity grouping.

**Acceptance:** `job_id` is visible in the member row; no synthetic `default/default` is persisted for new Agent runs; tenant defaults are resolved per execution; explicit slots and workflow resolution still work; failures to resolve do not create misleading execution records; duplicate admission reuses its frozen snapshot.

## Tasks

- [x] Add failing frontend and backend regression tests.
- [x] Add a scoped internal model-resolution endpoint and Scheduler client; resolve and freeze Agent slots in `_snapshot`, before insertion. Preserve workflow and model-free text behavior.
- [x] Persist actual fallback identities on completion and display `job_id` in the existing member cell.
- [x] Run targeted pytest through `venv/bin/python` in WSL, affected Vitest tests, and scoped formatting/lint checks. Review tenant isolation, retry/idempotency, pool accounting, and existing diff preservation.

Verification: 491 managed-cron regression tests passed; after the final metadata guard, 37 targeted/router/HTTP-chain tests passed. Both BatchDetail tests, TypeScript typecheck, scoped ESLint/Prettier, and Python formatting checks passed. Playwright rendered the real component with mocked API data and confirmed the task ID, absence of the execution ID in the cell, and concrete model labels. No live MySQL deployment or historical update was performed. Reviews were sequential main-thread reviews, not independent subagent reviews, in accordance with AGENTS.md.

## Verification

Use `PYTHONPATH=src:scheduler/src:monitor/src venv/bin/python -m pytest` for the new model identity tests and existing managed execution, pool, broadcast model and router suites. Run `npm run test:run -- src/pages/Monitor/ManagedBatchDispatch/BatchDetail.test.tsx` in `console/`.

## Limits

No external DDL, deployment, automatic historical rewrite, commit, or push. Historical model identities must be recovered from their execution metadata, never inferred from today's default. GitNexus impact commands currently fail while opening its pending WAL; source callers are inspected directly and this limitation must be reported.
