# Expert Community Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add model-configurable experts and a source-scoped Expert Community whose received packages run only with frozen private Skill and MCP dependencies.

**Architecture:** Extend the existing revisioned Agent-owned Definition Package with community provenance and a colocated immutable dependency directory. Add expert-specific marketplace models, filesystem snapshots and admin/browse routes alongside the existing skill/MCP market; installation materializes a new local definition ID. The chat request carries an explicit one-turn `selected_expert_id`; the runner resolves it directly and launches the expert without implicit Main-Agent discovery.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, filesystem-backed market store, React/TypeScript, Ant Design, pytest, Vitest.

---

## File map

- `src/swe/app/subagents/models.py` — community provenance, package dependency metadata, explicit selection request types.
- `src/swe/app/subagents/agent_definitions.py` — safe read/write/delete of definition companion dependencies and installation metadata.
- `src/swe/app/subagents/launch_snapshot.py` — strict snapshot source selection for frozen dependencies.
- `src/swe/app/subagents/supervisor.py`, `src/swe/app/runner/runner.py`, `src/swe/agents/react_agent.py` — explicit direct execution and disabled implicit discovery.
- `market/src/market/marketplace/{models,schemas,fs,service}.py` — item/version storage, snapshots, install/distribution/withdrawal services.
- `market/src/market/app/routers/{experts_market,experts_browse,expert_versions}.py` — community HTTP surface using the existing `X-Manager` convention.
- `console/src/pages/{Experts,ExpertCommunity,Chat}/` and Console routing/navigation — model picker, community UI, composer selection and Plan Mode mutual exclusion.
- `tests/unit/{subagents,app,marketplace}/`, `market/tests/`, `console/src/**/*.test.tsx` — focused regression coverage.

### Task 1: Expert model selection and persisted community provenance

**Files:**
- Modify: `src/swe/app/subagents/models.py`
- Modify: `src/swe/app/subagents/agent_definitions.py`
- Modify: `src/swe/app/routers/experts.py`
- Modify: `console/src/pages/Experts/index.tsx`
- Test: `tests/unit/subagents/test_agent_definitions.py`
- Test: `tests/unit/app/test_experts_router.py`
- Test: `console/src/pages/Experts/index.test.tsx`

- [ ] **Step 1: Write failing backend tests** for round-tripping `model={provider,id}`, preserving a now-unavailable stored model reference, and serializing received-community metadata (`item_id`, `received_version`, content fingerprint) without changing definition IDs.
- [ ] **Step 2: Run the targeted pytest tests** and verify they fail because community provenance is not represented.
- [ ] **Step 3: Add the smallest Pydantic metadata and TOML normalization changes** so local definitions retain model selection and received definitions retain their source identity.
- [ ] **Step 4: Add failing API/UI tests** asserting that the Experts form obtains tenant chat models, renders `provider / model`, offers inherit-current-chat-model, and submits the selected reference.
- [ ] **Step 5: Run the focused API/Vitest tests** and verify failure before UI implementation.
- [ ] **Step 6: Add the model picker** using the existing provider API and preserve unavailable references as a selectable display value.
- [ ] **Step 7: Re-run focused tests** and commit `feat(experts): configure expert model references`.

### Task 2: Frozen dependency package repository and launch isolation

**Files:**
- Modify: `src/swe/app/subagents/agent_definitions.py`
- Modify: `src/swe/app/subagents/launch_snapshot.py`
- Modify: `src/swe/app/subagents/supervisor.py`
- Test: `tests/unit/subagents/test_agent_definitions.py`
- Test: `tests/unit/subagents/test_launch_snapshot.py`
- Test: `tests/unit/subagents/test_supervisor.py`

- [ ] **Step 1: Write failing tests** for `agents/<definition-id>.dependencies/{skills,mcp}` companion paths, atomic copy/remove, safe path validation, and no symlink acceptance.
- [ ] **Step 2: Run the tests** and verify dependency package helpers are absent.
- [ ] **Step 3: Implement minimal repository helpers** that copy a complete frozen package, persist a content fingerprint, and delete the companion directory only when deleting the owning definition.
- [ ] **Step 4: Write failing launch tests** proving a received expert uses only frozen declared Skill/MCP content; missing/corrupt declared content blocks launch; no agent-profile same-name fallback occurs.
- [ ] **Step 5: Run the tests** and verify the existing launch snapshot skips/falls back instead of failing closed.
- [ ] **Step 6: Change snapshot capture** to select validated frozen dependencies for received experts, serialize all MCP fields unchanged, and retain regular local-expert behavior.
- [ ] **Step 7: Re-run unit tests** and commit `feat(experts): isolate frozen community dependencies`.

### Task 3: Expert Community marketplace data and lifecycle API

**Files:**
- Modify: `market/src/market/marketplace/{models,schemas,fs,service}.py`
- Create: `market/src/market/marketplace/expert_version_service.py`
- Create: `market/src/market/app/routers/experts_market.py`
- Create: `market/src/market/app/routers/experts_browse.py`
- Create: `market/src/market/app/routers/expert_versions.py`
- Modify: `market/src/market/app/routers/__init__.py`
- Test: `market/tests/marketplace/test_expert_service.py`
- Test: `market/tests/app/routers/test_experts_market.py`

- [ ] **Step 1: Write failing service tests** for publish of `1.0.0`, no-op identical publication, patch version snapshots, missing declared dependency rejection, source-scoped same-name conflict/confirmed continuation, unpublish and version restore.
- [ ] **Step 2: Run the service tests** and verify no Expert Community item service exists.
- [ ] **Step 3: Implement filesystem snapshot layouts** under `experts/<item-id>/versions/<version>/` containing definition TOML, `skills/`, `mcp/`, and Skill scan result; reuse existing category and BBK visibility conventions.
- [ ] **Step 4: Write failing route tests** for browse/detail/version history and manager-only publish/restore/unpublish endpoints.
- [ ] **Step 5: Run route tests** and verify routes are unregistered.
- [ ] **Step 6: Add routers** using the established `X-Manager: true` convention; do not add expert-specific authorization.
- [ ] **Step 7: Re-run market tests** and commit `feat(market): add versioned expert community packages`.

### Task 4: Receive, distribute, silently update, and withdraw experts

**Files:**
- Modify: `market/src/market/marketplace/service.py`
- Modify: `market/src/market/marketplace/fs.py`
- Modify: `market/src/market/app/routers/experts_market.py`
- Modify: `market/src/market/app/routers/experts_browse.py`
- Test: `market/tests/marketplace/test_expert_installation.py`
- Test: `market/tests/app/routers/test_experts_market.py`

- [ ] **Step 1: Write failing installation tests** for user+profile+item identity, new definition ID, default enablement, current-profile receive, duplicate receive rejection, and unrelated enabled-name conflict rollback.
- [ ] **Step 2: Run the tests** and verify installation behavior is absent.
- [ ] **Step 3: Implement receipt materialization** by copying the exact version dependency directory into the newly assigned definition companion directory and recording item/version/fingerprint metadata.
- [ ] **Step 4: Write failing distribution/withdrawal tests** for default-profile targeting, partial batch failures, retained enabled state on silent update, replacement of local edits for the same item, withdrawn-copy removal by item ID, and unpublish preserving installed copies.
- [ ] **Step 5: Run the tests** and verify no lifecycle service exists.
- [ ] **Step 6: Implement manager distribution and withdrawal** with existing async task/log patterns; explicitly omit self-service update and copy-as-new actions.
- [ ] **Step 7: Re-run market tests** and commit `feat(market): install and administer received experts`.

### Task 5: Explicit one-turn Chat expert execution

**Files:**
- Modify: `src/swe/app/runner/runner.py`
- Modify: `src/swe/agents/react_agent.py`
- Modify: `src/swe/app/subagents/supervisor.py`
- Modify: `src/swe/app/routers/experts.py`
- Test: `tests/unit/app/test_runner_selected_expert.py`
- Test: `tests/unit/subagents/test_react_agent_and_guard_integration.py`

- [ ] **Step 1: Write failing tests** for reading `selected_expert_id` only from current request metadata, rejecting disabled/withdrawn/missing definitions, direct launch of the exact definition, clearing the selection after use, and Main Agent summary after completion.
- [ ] **Step 2: Run tests** and verify current code only conditionally exposes background tools through intent detection.
- [ ] **Step 3: Add runner request parsing and direct launch plumbing** that gives the selected definition the current prompt/objective and records ordinary run progress/cancellation/failure.
- [ ] **Step 4: Write failing isolation tests** that unselected turns have neither expert directory exposure nor Background SubAgent tool registration, and selected turns cannot be substituted by Main Agent intent routing.
- [ ] **Step 5: Run tests** and verify implicit registration still occurs.
- [ ] **Step 6: Gate Background SubAgent tool registration and selected execution** on explicit metadata; resolve expert model before the current chat model and never change the Main Agent summary model.
- [ ] **Step 7: Re-run tests** and commit `feat(chat): run explicitly selected experts`.

### Task 6: Expert Community and composer interface

**Files:**
- Create: `console/src/pages/ExpertCommunity/index.tsx`
- Create: `console/src/pages/Chat/ExpertSelector/index.tsx`
- Modify: Console route/menu configuration and `console/src/pages/Chat/index.tsx`
- Modify: `console/src/pages/Chat/planMode.tsx`
- Test: `console/src/pages/ExpertCommunity/index.test.tsx`
- Test: `console/src/pages/Chat/ExpertSelector/index.test.tsx`
- Test: `console/src/pages/Chat/index.test.tsx`

- [ ] **Step 1: Write failing UI tests** for a top-level Expert Community menu immediately after Application Marketplace, browse/receive state, manager publication/lifecycle actions, and no direct execution from community list.
- [ ] **Step 2: Run Vitest** and verify components/routes do not exist.
- [ ] **Step 3: Implement the community page** by following existing My Skills/My MCP market APIs and manager affordances, retaining only requested receive/distribute/withdraw/unpublish/version actions.
- [ ] **Step 4: Write failing composer tests** for a searchable Expert selector beside Model, enabled current-profile entries only, outgoing `biz_params.selected_expert_id`, post-submit clearing, profile-change clearing, and mutual clearing with Plan Mode.
- [ ] **Step 5: Run Vitest** and verify the composer has no selector state.
- [ ] **Step 6: Implement selector and Plan Mode integration** without disabling either control; selecting expert clears Plan Mode and enabling Plan Mode clears expert selection.
- [ ] **Step 7: Run frontend tests and the CoPaw frontend review checklist**, then commit `feat(console): add expert community and chat selector`.

### Task 7: End-to-end regression, documentation, and final review

**Files:**
- Modify: `docs/adr/0028-community-experts-use-frozen-private-dependencies.md` only if implementation necessitates an already-agreed terminology clarification.
- Test: focused Python/market/console suites from Tasks 1–6.

- [ ] **Step 1: Run all focused pytest suites and Console Vitest suites**; fix only observed regressions with a new RED/GREEN loop.
- [ ] **Step 2: Run `pre-commit run --all-files` and `git diff --check`**; make formatting-only corrections if needed.
- [ ] **Step 3: Run GitNexus `detect_changes` against staged changes** and inspect all affected symbols/flows before each commit.
- [ ] **Step 4: Dispatch a specification review, then a code-quality review**; resolve every important finding and re-run the appropriate tests.
- [ ] **Step 5: Commit remaining verification fixes** and report the precise commits plus test evidence.
