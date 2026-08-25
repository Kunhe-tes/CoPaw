# Three Core Runtime Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the three largest runtime classes—`AgentRunner`, `SWEAgent`, and `ProviderManager`—into compatibility façades over cohesive internal modules without changing query, tenant, persistence, or streaming contracts.

**Architecture:** Each public class remains its current integration and backward-compatible entry point. Query execution becomes one deep `QueryExecution` module; Agent construction and per-turn execution become `agent_runtime` components; Provider storage, catalog operations, freshness and instance caching become separate provider collaborators. Internal helpers may be moved only when their caller-visible order, exception behavior, and patch seam are characterized first.

**Tech Stack:** Python 3.12, asyncio, pytest, Pydantic, AgentScope, GitNexus, pre-commit.

---

## Constraints and acceptance criteria

- Preserve public method signatures and response/persistence formats.
- Preserve ordered `(Msg, last)` output, `trace_id`, approval, Hook, Stop, Goal, retry and cancellation semantics.
- Preserve tenant-root resolution, source-template provisioning, atomic Provider persistence, cache invalidation and single-flight startup.
- Do not stage user-owned files; commit each bounded slice separately.
- Before every symbol edit run GitNexus upstream impact. Stop for HIGH/CRITICAL risk. Before every commit run staged `detect_changes`, focused tests, `py_compile`, pre-commit and `git diff --cached --check`.
- A phase is complete only when its focussed contract suite is green and its façade is no longer the sole owner of the extracted implementation.

## Target structure

```text
src/swe/app/runner/
  runner.py                         # AgentScope façade/composition root
  query_execution/                  # one deep complete-query module
  query_runtime.py                  # activation internals
  query_cleanup.py                  # RuntimeLease disposal internals

src/swe/agents/
  react_agent.py                    # SWEAgent compatibility façade
  agent_runtime/                    # toolkit, prompts, skills, MCP, phases

src/swe/providers/
  provider_manager.py               # tenant-facing façade
  tenant_provider_repository.py     # scoped disk read/write/discovery
  provider_runtime_cache.py         # instances, refresh executor, epochs
  provider_catalog_service.py       # provider/model CRUD and activation
  provider_freshness.py             # mtime snapshots and refresh policy
```

## Workstream A — AgentRunner / QueryExecution

### Task A1: Finish activation ownership

**Files:** modify `src/swe/app/runner/query_runtime.py`, `runner.py`, `query_contracts.py`; test `tests/unit/app/test_runner_query_boundaries.py`, `test_runner_hook_runtime.py`.

- [ ] Write direct `query_runtime` contracts for: chat before MCP discovery; scenario context selection; SESSION_START block returns a blocked lease; selected Skill Hooks load only after successful SESSION_START.
- [ ] Run each new test first; expected failure is a missing collaborator entry point.
- [ ] Move `_start_query_runtime_resources` implementation to `query_runtime.activate_resources(owner, ...)`; retain the Runner method as one delegation preserving runner-level patched helpers (`_build_lazy_mcp_clients`, `build_env_context`, config loading).
- [ ] Model normal and blocked results as a `RuntimeLease`-compatible value without changing `_RuntimeStartResult` fields.
- [ ] Run: `venv/bin/python -m pytest tests/unit/app/test_runner_query_boundaries.py tests/unit/app/test_runner_hook_runtime.py -q`.
- [ ] Commit: `refactor(runner): extract runtime resource activation`.

### Task A2: Move attempt/finally control flow behind QueryExecution

**Files:** create `query_execution/execution.py`, `query_execution/observability.py`; modify `query_execution/adapters.py`, `query_attempt.py`, `runner.py`; test `test_query_execution.py`, `test_runner_query_boundaries.py`.

- [ ] Characterize frame sequences for approval denial, prompt-Hook block, command, retry notice/exhaustion, cancellation, normal completion and blocked activation cleanup.
- [ ] Make the test fail against a fake `QueryExecution` adapter that records frames and cleanup calls.
- [ ] Move retry loop, exception conversion, trace completion and finally ordering to `QueryExecution.stream`; keep `query_handler`/`stream_query` only as AgentScope adapters.
- [ ] Keep `asyncio.gather(return_exceptions=True)` and first post-gather exception propagation unchanged.
- [ ] Delete one redundant runner forwarding body only after its frame contract passes.
- [ ] Run the runner  query matrix and `tests/unit/app/test_session_state_merge_coordination.py`.
- [ ] Commit: `refactor(runner): centralize query attempt ownership`.

### Task A3: Consolidate continuation and delete migration protocols

**Files:** create `query_execution/continuation.py`, `session_state.py`; modify `turn_lifecycle.py`, `session_lifecycle.py`, `query_contracts.py`, `runner.py`; tests under `tests/unit/app/` for goals, hooks, sessions and query boundaries.

- [ ] Add ordered contracts for Stop continuation, Goal waiting/review/finalization, session-skill restore/freshness, and one terminal `last=True` frame.
- [ ] Move the complete turn/continuation loop behind `QueryExecution`; do not split Goal and Stop into public phases.
- [ ] Replace wide `*Owner` Protocols with the three live/fake adapters: runtime, state, observation.
- [ ] Remove legacy forwarding methods only after their contract test uses the public execution interface.
- [ ] Run focussed runner, workspace and tenant tests.
- [ ] Commit: `refactor(runner): complete query execution deep module`.

## Workstream B — SWEAgent / agent_runtime

### Task B1: Make construction a component assembly boundary

**Files:** create `src/swe/agents/agent_runtime/components.py`, `builder.py`; modify `react_agent.py`; tests `tests/unit/agents/test_agent_runtime_builder.py` and source-tool tests.

- [ ] Characterize toolkit composition: enabled built-ins, source tools, subagents, background tasks, Skills and MCP rebuild metadata.
- [ ] Introduce `AgentRuntimeComponents` as a private value object and `AgentRuntimeBuilder.build(config, context)`.
- [ ] Move `_create_toolkit`, tool registration and source-tool registration bodies; leave same-named SWEAgent methods as temporary delegators.
- [ ] Verify registration ordering and duplicate-tool rejection.
- [ ] Commit: `refactor(agent): extract runtime component builder`.

### Task B2: Separate prompt/memory from execution phases

**Files:** create `agent_runtime/prompting.py`, `memory.py`, `phases.py`; modify `react_agent.py`; tests for prompt freshness, media stripping, reasoning/summarizing and watchdog behavior.

- [ ] Add contracts that prompt freshness rebuilds exactly once, media fallback retains non-media memory, and phase transitions start/reset/stop the watchdog.
- [ ] Move system prompt construction and memory setup into prompting/memory modules.
- [ ] Move `_reasoning`, summarization, reply/research and interruption state transitions into `phases.py`; `SWEAgent.reply` remains the public entry.
- [ ] Run agent runtime, Hook and runner integration tests.
- [ ] Commit: `refactor(agent): isolate prompt memory and execution phases`.

### Task B3: Finalize MCP registration façade

**Files:** create `agent_runtime/mcp_registrar.py`; modify `react_agent.py`; test MCP collision, rebuild and cancellation semantics.

- [ ] Move `register_mcp_clients` implementation and retain the existing public async method as a thin call.
- [ ] Assert pending MCP tasks are shielded/cancelled as before and errors retain their original source client identity.
- [ ] Delete obsolete Agent private registration helpers after contract coverage.
- [ ] Commit: `refactor(agent): isolate mcp registration runtime`.

## Workstream C — ProviderManager

### Task C1: Complete repository/cache ownership

**Files:** modify `tenant_provider_repository.py`, `provider_runtime_cache.py`, `provider_manager.py`; tests `tests/unit/providers/test_provider_*`.

- [ ] Characterize tenant path selection, seed/template concurrency, atomic JSON replacement, per-tenant instance single-flight and refresh epoch invalidation.
- [ ] Move every raw file discovery/read/write and lock operation from ProviderManager into the repository.
- [ ] Move instance map, inflight futures, executor and refresh due/epoch state into runtime cache.
- [ ] Keep `ProviderManager.get_instance` and async startup return types unchanged.
- [ ] Commit: `refactor(providers): complete repository and cache ownership`.

### Task C2: Isolate freshness policy

**Files:** create `provider_freshness.py`; modify `provider_manager.py`, cache/repository; test builtin/custom/active-model changes and invalidate-during-refresh regression.

- [ ] Add red tests for changed builtin, custom create/delete, active-model change, and a stale refresh completing after invalidation.
- [ ] Move mtime snapshots, detection and refresh plan calculation into `ProviderFreshnessPolicy`.
- [ ] Let ProviderManager apply an explicit refresh plan through catalog/repository APIs; it must not inspect storage directly.
- [ ] Commit: `refactor(providers): extract provider freshness policy`.

### Task C3: Collapse ProviderManager to a tenant façade

**Files:** modify `provider_manager.py`, `provider_catalog_service.py`; tests `tests/unit/providers/test_provider_boundary_services.py` plus manager integration tests.

- [ ] Characterize CRUD, model mutation, activation, multimodal probing and persistence boundaries.
- [ ] Route all catalog CRUD/activation through `ProviderCatalogService`; keep tenant resolution and public method signatures in ProviderManager.
- [ ] Remove duplicated ProviderManager storage/catalog methods only after service contract tests are green.
- [ ] Run provider package tests in both isolated and normal import order.
- [ ] Commit: `refactor(providers): reduce manager to tenant facade`.

## Final hardening

### Task D1: Architecture and regression gate

**Files:** modify only required docs/ADRs and targeted tests.

- [ ] Run `rg` to confirm runner/agent/provider façades contain no duplicated ownership bodies.
- [ ] Run GitNexus `detect_changes(scope:"compare", base_ref:"main")`; review any HIGH/CRITICAL path.
- [ ] Run: `venv/bin/python -m pytest tests/unit/app/ tests/unit/agents/ tests/unit/providers/ -q` and the tenant/workspace integration suite.
- [ ] Run `venv/bin/python -m pre_commit run --all-files` if the worktree is isolated; otherwise run only changed files and report user-owned failures separately.
- [ ] Commit documentation/ADR only if an architectural decision changed; do not bundle it with code slices.

## Ordering and exit criteria

Execute A before B: `SWEAgent` internals remain stable while query lifecycle seams are completed. Execute C independently after A’s provider activation contract is green. The refactor is done when the three original files are framework/domain façades, each public workflow is covered through its public entry point, and no temporary wide owner Protocol is needed to coordinate one query.
