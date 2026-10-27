# SubAgent Intent and Expert Discovery Implementation Plan

**Goal:** Implement the confirmed Q1–Q13 specification and deliver functionality and test reports with incremental commits and independent reviews.

**Architecture:** Separate start permission, catalog visibility and Chat-owned run management. Persist Goal delegation intent, but keep expert capabilities private and Source configuration current at subsequent turns.

**Tech Stack:** Python, FastAPI, Pydantic, pytest; React, TypeScript, Vitest.

## Tasks

- [x] Intent/catalog/config: keyword helper, structured enablement, exclusive selection, Source default-off switch, frontend registry, tests. Reviewed and committed as `d4ca8466f`.
- [x] Chat management/dependencies: owning Chat/session checks, management-only registration, private expert views and concurrent initialization. Reviewed and committed as `343ee43c7`.
- [x] Goal intent: durable field, trusted draft/create/Steering intent, recovery and Source refresh; monotonic store protection and worker preparation. Reviewed and committed as `740db02db`.
- [ ] Final integration: review against every requirement, run related suites and frontend checks, fix findings, changed-file pre-commit, GitNexus detect_changes, deliver reports.

## Verification

Use the project virtualenv. Relevant baseline command covers tests/unit/app/goals, source configuration, runner Goal lifecycle and selected expert dependency views. Add focused regression cases before implementing each feature. Use root console node_modules from the worktree when required. Never include unrelated current-branch changes in feature commits.

## Integration

Base branch: perf/event-loop-optimization. Feature worktree: .worktrees/subagent-intent-discovery. Do not push or open a PR without user instructions. Preserve current-branch uncommitted work; integrate only reviewed feature commits.
