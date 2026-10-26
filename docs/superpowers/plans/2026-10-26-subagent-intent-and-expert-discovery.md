# SubAgent Intent and Expert Discovery Implementation Plan

**Goal:** Implement the confirmed Q1–Q13 specification and deliver functionality and test reports with incremental commits and independent reviews.

**Architecture:** Separate start permission, catalog visibility and Chat-owned run management. Persist Goal delegation intent, but keep expert capabilities private and Source configuration current at subsequent turns.

**Tech Stack:** Python, FastAPI, Pydantic, pytest; React, TypeScript, Vitest.

## Tasks

- [ ] Intent/catalog/config: keyword helper, structured enablement, exclusive selection, Source default-off switch, frontend registry, tests. Verify TDD red/green and review before committing.
- [ ] Chat management/dependencies: separate management registration, owning Chat/session checks in get/wait/cancel, retained-run detection, per-expert Chat views and tests. Verify cross-Chat denial and frozen dependency reuse.
- [ ] Goal intent: durable backward-compatible field, creation request, real user request/Steering promotion, restore and per-turn toolkit/catalog refresh; test automatic turns and process recovery.
- [ ] Final integration: review against every requirement, run related suites and frontend checks, fix findings, changed-file pre-commit, GitNexus detect_changes, deliver reports.

## Verification

Use the project virtualenv. Relevant baseline command covers tests/unit/app/goals, source configuration, runner Goal lifecycle and selected expert dependency views. Add focused regression cases before implementing each feature. Use root console node_modules from the worktree when required. Never include unrelated current-branch changes in feature commits.

## Integration

Base branch: perf/event-loop-optimization. Feature worktree: .worktrees/subagent-intent-discovery. Do not push or open a PR without user instructions. Preserve current-branch uncommitted work; integrate only reviewed feature commits.
