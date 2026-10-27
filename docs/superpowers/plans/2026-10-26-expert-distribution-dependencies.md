# Expert Distribution Dependencies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Restore the expert distribution HTTP route and verify delivery of the published expert's complete private Skill/MCP snapshot.

**Architecture:** Keep the existing request/response schema and private dependency installer. Correct only the route's stale logging fields unless regression tests expose a dependency-delivery defect. Remote Agent reload is mocked at the service boundary in filesystem tests; real reload connectivity is outside this change.

**Tech Stack:** Python, FastAPI, Pydantic, pytest, existing TOML/JSON marketplace packages.

## Task 1: Reproduce and repair the route

**Files:** `market/src/market/app/routers/experts_market.py`, `tests/unit/market/test_experts_market.py`.

- [x] Run the existing `test_distribution_and_recall_require_manager`; confirm AttributeError on `req.target_tenant_ids` before service dispatch.
- [x] Add a parameterized route regression for `all`, `bbk_id`, and `user_id`; assert request values reach the service unchanged.
- [x] Replace the stale log arguments with:

```python
target_type=req.target_type,
target_values=req.target_values,
```

- [x] Run `PYTHONPATH=market/src ../../venv/bin/python -m pytest tests/unit/market/test_experts_market.py -q --tb=short` from the worktree; all route tests must pass.

## Task 2: Verify private frozen dependency delivery

**File:** `tests/unit/market/test_expert_service.py`.

- [x] Isolate the existing service fixture from real Agent reload HTTP with `AsyncMock(return_value=True)`; retain the dedicated reload-failure test's override.
- [x] Add HTTP-to-real-service distribution coverage with one recipient lacking normal dependencies and one holding same-name normal Skill/MCP resources. Assert expert content, nested Skill files, MCP env/headers, private runtime dependency capture, and unchanged normal resources.
- [x] Mutate source Skill/MCP after publication; assert distribution still copies the published content. Republish and distribute an update; assert new private content and retained disabled state.
- [x] Cover per-user delivery failure with a failed copy and another successful recipient; assert old definition and dependency content are preserved.
- [x] Run `PYTHONPATH=market/src ../../venv/bin/python -m pytest tests/unit/market/test_experts_market.py tests/unit/market/test_expert_service.py -q --tb=short`; expect no failures and no external reload calls.

## Task 3: Review and deliver

- [x] Run changed-file pre-commit checks and relevant SubAgent private-dependency tests that do not depend on retired builtin experts.
- [x] Review the source diff and request independent review against the confirmed scope.
- [x] Run GitNexus detect_changes; if graph results are incomplete, supplement with the exact source diff.
- [x] Transfer only verified implementation/test/plan files into the original workspace; preserve pre-existing changes.
- [x] Re-run the focused suite from the original workspace and update the design/report/playbook to reflect verified results.

No automatic commit, push, or unrelated runtime fixes are required for delivery.

## Verified result

The original workspace passes 58 relevant tests:

```bash
PYTHONPATH=market/src venv/bin/python -m pytest tests/unit/market/test_experts_market.py tests/unit/market/test_expert_service.py tests/unit/app/test_runner_selected_expert_dependency_views.py tests/unit/subagents/test_agent_definitions.py tests/unit/subagents/test_agent_owned_runtime_catalog.py -q --tb=short
```

Changed-file pre-commit checks all pass. Independent review found no actionable issues. Agent reload is mocked at the external boundary; real remote reload, LLM, and MCP connections are not covered.

GitNexus could not resolve the route symbol before editing. detect_changes mislabeled an unchanged TestPublishExpert class as critical and associated unrelated flows; an AST comparison against HEAD proved that class unchanged. The precise source diff confirms only the two route logging argument replacements in production code.
