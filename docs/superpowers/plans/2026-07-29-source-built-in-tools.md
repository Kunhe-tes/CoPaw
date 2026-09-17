# Source Built-in Tool Library — Implementation Plan

> **For Codex:** Execute with test-first development. Keep the worktree isolated from the user’s existing uncommitted changes.

**Goal:** Allow a source manager/admin to upload, statically validate, test, publish, deactivate, inspect, and download Python source tools. Published source tools are available to every tenant beneath that source, override only code-defined built-ins with compatible schemas, and execute within the invoking tenant’s established tool guard and runtime boundaries.

**Architecture:** Add a source-owned tool catalogue with immutable published versions and mutable single drafts, separate from Source System Config JSON. A runtime resolver snapshots the active catalogue when an agent is built; an AgentScope adapter registers source tools after code built-ins, rejects Skill/MCP collisions, and invokes a per-call constrained subprocess using the active tenant workspace and allowlisted tenant credentials. The existing Agent tool setting remains the only enable/disable decision.

**Tech Stack:** FastAPI/Pydantic; existing database abstraction and source context middleware; AgentScope Toolkit; Python ast static validation; existing tenant runtime env, path guard, Tool Guard, tracing/audit conventions; React/TypeScript console.

---

### Task 1: Define the source-tool domain, persistence, and static validation

**Files:**
- Create: src/swe/app/source_tools/models.py
- Create: src/swe/app/source_tools/store.py
- Create: src/swe/app/source_tools/service.py
- Create: src/swe/app/source_tools/validation.py
- Create: src/swe/app/source_tools/audit.py
- Create: tests/unit/app/source_tools/test_validation.py
- Create: tests/unit/app/source_tools/test_service.py

1. Write failing validation tests for the 1 MB cap, Python syntax, static literal metadata/schema/env list, fixed async execute(arguments, context), identifier rules, restricted imports, code-built-in schema compatibility, Skill/MCP collision rejection, and scan-unavailable/finding rejection.
2. Run ../../venv/bin/python -m pytest tests/unit/app/source_tools/test_validation.py -q and observe failures.
3. Implement models plus AST-only contract validation and a safety-scan gateway; do not import or execute uploaded modules.
4. Write service/store tests for one draft per source/name, explicit draft replacement/discard, immutable published history, explicit same-name publish confirmation, activation/deactivation, metadata-only audit, and source-scoped lookup.
5. Implement transactional store/service semantics; retain script content only in source-owned version records and never store it in Source System Config JSON.
6. Run the two test files until green.

### Task 2: Add source-scoped management/read APIs and application initialization

**Files:**
- Create: src/swe/app/source_tools/router.py
- Modify: src/swe/app/source_tools/__init__.py
- Modify: src/swe/app/_app.py
- Modify: src/swe/app/routers/__init__.py
- Create: tests/unit/app/source_tools/test_router.py
- Modify: tests/unit/app/test_app_initialization.py (or nearest existing startup test)

1. Write failing API tests for manager/admin-only mutation/read/download, source context requirement, draft upload, manual-test request shape, publish confirmation, deactivate, history, audit, and regular users’ effective-metadata access.
2. Run the router tests and observe failures.
3. Initialize the source-tool service separately on app.state, mount the source-scoped router, and translate persistence/validation/safety failures to safe HTTP responses.
4. Ensure audit responses never contain script text, input JSON, or credential values; download is manager/admin only.
5. Run source-tool API/startup tests until green.

### Task 3: Build the tenant-executed runtime adapter

**Files:**
- Create: src/swe/agents/source_tools.py
- Modify: src/swe/envs/runtime.py
- Modify: src/swe/agents/react_agent.py
- Create: tests/unit/agents/test_source_tools.py
- Modify: tests/unit/agents/test_tool_failure.py

1. Write failing tests for active-catalog snapshotting, source-first override, code-built-in schema equality, disabled Agent tool precedence, no fallback after source runtime failure, deactivation behavior on later agent creation, exactly allowlisted tenant env injection, missing-env structured errors, 60-second cap, and ToolResponse normalization.
2. Run ../../venv/bin/python -m pytest tests/unit/agents/test_source_tools.py tests/unit/agents/test_tool_failure.py -q and observe failures.
3. Implement a source-tool runner that creates an isolated subprocess per invocation, applies existing workspace/path guard and tenant process boundaries, passes only declared tenant variables, and returns bounded/redacted structured ToolResponse results.
4. Integrate into SWEAgent._create_toolkit: register enabled code built-ins first, snapshot/register source tools second using explicit override semantics, then register skills; fail closed on guard/runtime setup errors and reject source collisions with skills/MCP.
5. Preserve execute_shell_command async setting only for its source override; all other source tools stay synchronous.
6. Run the runtime test group until green.

### Task 4: Surface effective tools and persist only Agent deviations

**Files:**
- Modify: src/swe/app/routers/tools.py
- Modify: src/swe/config/config.py
- Create: tests/unit/app/test_source_tools_effective_list.py
- Modify: tests/unit/config/test_builtin_tool_defaults.py

1. Write failing tests that the effective tool endpoint includes source/version/origin fields, defaults new source tools to enabled without materializing every Agent config, saves only explicit Agent choices, preserves choices through deactivate/reactivate, and keeps source-owned metadata read-only to normal tenant users.
2. Run the focused API/config tests and observe failures.
3. Add sparse source-tool enablement deviations to Agent config and merge them only while serving the current source catalogue.
4. Update list/toggle responses and reload behavior so the next agent run receives the new snapshot while in-flight runs retain their snapshot.
5. Run focused tests until green.

### Task 5: Implement the System Configuration and Agent Tools UI

**Files:**
- Create: console/src/api/modules/sourceTools.ts
- Create: console/src/pages/SystemConfigPage/SourceToolLibrary.tsx
- Modify: console/src/pages/SystemConfigPage/index.tsx
- Modify: console/src/pages/Agent/Tools/index.tsx
- Modify: console/src/pages/Agent/Tools/useTools.ts
- Modify: console/src/api/modules/tools.ts
- Create: console/src/pages/SystemConfigPage/__tests__/SourceToolLibrary.test.tsx
- Modify: nearest Agent Tools test location

1. Write failing UI/API adapter tests for manager-only library visibility, upload-to-draft flow, explicit draft replacement/discard and publish confirmations, manual-test warning, deactivate/history/download/audit actions, and effective origin/version-only Agent Tools display.
2. Run the focused frontend tests and observe failures.
3. Implement the library on System Configuration; do not expose a browser code editor or management controls on Agent Tools.
4. Implement effective-tool metadata/toggle rendering and source version/origin labels.
5. Run the focused frontend tests and the production type/build check.

### Task 6: Documentation, integration validation, and review

**Files:**
- Modify: CONTEXT.md
- Create: docs/adr/0019-source-built-in-tools-are-source-owned-and-tenant-executed.md

1. Apply the agreed glossary/ADR in the feature worktree; use ADR number 0019 to avoid collision with the user’s unrelated untracked 0018 in the original worktree.
2. Run backend unit suite for changed modules, frontend tests/build, git diff --check, and GitNexus change detection against the linked worktree.
3. Review the diff for accidental changes, safety regressions, missing source/tenant isolation, and leaked sensitive fields.
4. Report concrete verification results and the isolated-worktree handoff.
