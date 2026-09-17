# Skill-owned SubAgent Definitions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let enabled Skills package TOML-defined SubAgent Definitions that a Main Agent can explicitly delegate to after the user requests a SubAgent, with scoped Skills, MCP clients, model selection, parent-bounded built-in tools, immutable launch snapshots, and detailed run diagnostics.

**Architecture:** Parse `skills/<skill>/agents/*.toml` into a Skill-owned metadata extension of the existing `SubAgentDefinition` while retaining `source="stored"` for compatibility. Build an Agent-run catalog that reserves qualified names, resolves exact Skill-owned names before legacy stored/builtin matching, and passes a fully resolved launch snapshot to the background worker. The worker uses copied Skill packages, independently connects a private snapshot of declared MCP settings, and uses an optional resolved model slot; all tool calls remain constrained by parent configuration, the resolved Definition, Tool Guard, and noninteractive approval behavior.

**Tech Stack:** Python 3.12 `tomllib`, Pydantic v2, FastAPI runtime, AgentScope Toolkit/MCP clients, existing ProviderManager, pytest.

---

## Target File Structure

| Path | Responsibility |
| --- | --- |
| `src/swe/app/subagents/skill_definitions.py` | Parse and validate `agents/*.toml`, qualify names, resolve enabled Skill dependencies, and build catalog entries/descriptors. |
| `src/swe/app/subagents/launch_snapshot.py` | Copy selected Skill packages, write private MCP configuration snapshots, resolve model slots, and assemble safe audit diagnostics. |
| `src/swe/app/subagents/models.py` | Define skill-owned metadata, model reference, launch snapshot/diagnostic models, optional start instruction, and persisted record fields. |
| `src/swe/app/subagents/definition_service.py` | Combine Skill-owned, Stored, and built-in Definitions while preserving exact-name and run-scoped fallback behavior. |
| `src/swe/app/subagents/permissions.py` | Compose parent-bounded mutable built-in tool policies and authorize allowed MCP servers without allowing nested delegation. |
| `src/swe/app/subagents/supervisor.py` | Capture immutable snapshots before launching workers and persist safe diagnostics. |
| `src/swe/app/subagents/worker.py` | Load copied Skills, read private MCP configuration, independently connect MCP clients, bind model selection, and delete secret snapshot material. |
| `src/swe/app/subagents/runtime.py` | Construct a fresh `SWEAgent` from launch snapshots and build the instruction/objective/background prompt. |
| `src/swe/agents/react_agent.py` | Register an explicit Skill list for worker agents, accept an optional model slot, and retain the Main-Agent-only delegation boundary. |
| `src/swe/agents/model_factory.py` | Accept an explicit validated model slot without changing the default tenant active-model behavior. |
| `src/swe/agents/tool_guard_mixin.py` | Reject a SubAgent call that needs interactive approval and authorize MCP calls only for snapshotted servers. |
| `src/swe/agents/tools/subagent_background.py` | Publish the dynamic directory in `start_subagent`, resolve catalogs, and preserve legacy run-scoped fallback. |
| `tests/unit/subagents/test_skill_definitions.py` | TOML parsing, name ownership, dependency selection, invalid-package isolation, and tool directory tests. |
| `tests/unit/subagents/test_launch_snapshot.py` | Immutable Skill/MCP/model snapshots and safe diagnostics tests. |
| Existing `tests/unit/subagents/test_*.py` | Update model, tool, policy, runtime, worker, supervisor, and monitor expectations. |

### Task 1: Define TOML and Skill-owned Definition Models

**Files:**
- Create: `src/swe/app/subagents/skill_definitions.py`
- Modify: `src/swe/app/subagents/models.py`
- Modify: `src/swe/app/subagents/__init__.py`
- Test: `tests/unit/subagents/test_skill_definitions.py`

- [ ] **Step 1: Write failing parser tests for the public TOML contract.**

```python
def test_load_skill_definition_qualifies_local_name(tmp_path: Path) -> None:
    _write_skill_definition(
        tmp_path, "security", "reviewer", '''
name = "reviewer"
description = "Review code and identify security regressions."
instruction = "Inspect the change and cite evidence."
trigger_keywords = ["review", "security"]
skills = ["security"]
mcps = ["github"]

[tools]
allow = ["read_file", "write_file", "edit_file"]
deny = ["execute_shell_command"]

[model]
provider = "openai"
id = "gpt-5-mini"

[budget]
max_turns = 20
max_tool_calls = 10
timeout_ms = 120000
''')

    loaded = load_skill_owned_definitions(
        workspace_dir=tmp_path,
        effective_skill_names=["security"],
    )

    definition = loaded.definitions[0]
    assert definition.name == "security:reviewer"
    assert definition.source == "stored"
    assert definition.skill_owned is not None
    assert definition.skill_owned.local_name == "reviewer"
    assert definition.skill_owned.declared_skills == ["security"]
    assert definition.skill_owned.tools.inherit is True
```

- [ ] **Step 2: Run the parser test and verify it fails because the module does not exist.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_skill_definitions.py -q`

Expected: FAIL during collection with `ModuleNotFoundError` for `skill_definitions`.

- [ ] **Step 3: Add strict TOML models and a file-local parser.**

Use `tomllib.loads`; accept only `name`, `description`, `instruction`, `trigger_keywords`, `skills`, `mcps`, `[tools]`, `[model]`, and `[budget]`. Reject unknown keys, non-string dependency names, blank names, duplicate local names in one Skill, invalid budgets, and unsafe tool names. Introduce models with defaults that do not alter existing definitions:

```python
class SkillOwnedToolConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inherit: bool = True
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)

class SkillOwnedModelReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    id: str

class SkillOwnedDefinitionMetadata(BaseModel):
    skill_name: str
    local_name: str
    declared_skills: list[str] = Field(default_factory=list)
    declared_mcps: list[str] = Field(default_factory=list)
    tools: SkillOwnedToolConfig = Field(default_factory=SkillOwnedToolConfig)
    model: SkillOwnedModelReference | None = None
```

Add `skill_owned: SkillOwnedDefinitionMetadata | None = None` to `SubAgentDefinition`; parser-created definitions use `source="stored"`, `owner_scope="skill:<skill-name>"`, and `name=f"{skill_name}:{local_name}"`. Do not add a new `DefinitionSource` value, so old JSON and schema consumers remain valid.

- [ ] **Step 4: Add isolation and validation tests.**

Cover malformed TOML, unknown TOML fields, a duplicate qualified name, a blank `instruction`, an invalid model table, tool entries outside `KNOWN_BUILTIN_TOOLS`, and one invalid sibling TOML beside a valid TOML. Assert that only the bad package is reported in `load_result.errors`; the owning Skill and valid sibling Definition remain loadable.

- [ ] **Step 5: Run focused tests.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_skill_definitions.py tests/unit/subagents/test_models_registry_policy.py -q`

Expected: PASS, including pre-existing built-in/Stored Definition validation tests.

- [ ] **Step 6: Commit the parser contract.**

```bash
git add src/swe/app/subagents/skill_definitions.py src/swe/app/subagents/models.py src/swe/app/subagents/__init__.py tests/unit/subagents/test_skill_definitions.py
git commit -m "feat(subagents): parse skill-owned definitions"
```

### Task 2: Build a Deterministic Definition Catalog and Preserve Legacy Fallback

**Files:**
- Modify: `src/swe/app/subagents/skill_definitions.py`
- Modify: `src/swe/app/subagents/definition_service.py`
- Modify: `src/swe/app/subagents/registry.py`
- Test: `tests/unit/subagents/test_skill_definitions.py`
- Test: `tests/unit/subagents/test_definition_store_service.py`
- Test: `tests/unit/subagents/test_definition_matcher.py`

- [ ] **Step 1: Write failing catalog tests for ownership and selection.**

```python
def test_catalog_resolves_skill_owned_name_exactly_before_legacy_matching():
    catalog = build_definition_catalog(
        skill_definitions=[_skill_definition("security:reviewer")],
        stored_definitions=[_stored_definition("reviewer")],
        builtin_definitions=[_builtin_definition("risk-reviewer")],
    )

    assert catalog.resolve_exact("security:reviewer").name == "security:reviewer"
    assert catalog.resolve_exact("reviewer").name == "reviewer"
    assert catalog.resolve_exact("security:missing") is None


def test_stored_definition_cannot_claim_skill_qualified_name():
    with pytest.raises(DefinitionValidationError, match="reserved"):
        build_definition_catalog(
            skill_definitions=[_skill_definition("security:reviewer")],
            stored_definitions=[_stored_definition("security:reviewer")],
            builtin_definitions=[],
        )
```

- [ ] **Step 2: Run the catalog tests and verify they fail.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_skill_definitions.py -q`

Expected: FAIL because `build_definition_catalog` is not defined.

- [ ] **Step 3: Implement catalog construction without changing `AgentRegistry` collision semantics.**

Add a focused catalog object that contains exact Skill-owned names, a normal `AgentRegistry` for Stored/built-in entries, and stable `SubAgentDirectoryEntry` values. Build it from the current effective Skills in manifest order. Enforce:

```text
skill-qualified name: only the matching loaded Skill package may own it
built-in name: neither Stored nor Skill-owned definitions may own it
ordinary Stored name: cannot claim any reserved Skill-qualified or built-in name
```

Do not use a runtime priority tie-breaker for a duplicate name. Keep `SubAgentDefinitionMatcher` for legacy Stored/built-in short-circuit matching only; a Skill-owned Definition is selected only by an exact qualified `name`.

- [ ] **Step 4: Make the start service use the catalog.**

Refactor `SubAgentDefinitionService` to expose:

```python
def resolve_start_definition(
    self,
    request: SubAgentStartRequest,
    catalog: SubAgentDefinitionCatalog,
) -> ResolvedStartDefinition | None:
    exact = catalog.resolve_exact(request.name)
    if exact is not None:
        return ResolvedStartDefinition(
            exact,
            DefinitionMatchMetadata(
                matched=True,
                definition_name=exact.name,
                definition_source=exact.source,
                score=1.0,
                reason="exact_name",
            ),
        )
    return self.match_start_request(request)
```

If neither exact nor legacy matching resolves and `request.instruction` is non-empty, retain `build_run_scoped_definition`; otherwise return `None` so the tool can return `not_found`. A resolved Definition ignores caller `instruction`.

- [ ] **Step 5: Run compatibility tests.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_skill_definitions.py tests/unit/subagents/test_definition_store_service.py tests/unit/subagents/test_definition_matcher.py -q`

Expected: PASS. Existing run-scoped fallback tests must still pass after changing `instruction` to optional.

- [ ] **Step 6: Commit catalog resolution.**

```bash
git add src/swe/app/subagents/skill_definitions.py src/swe/app/subagents/definition_service.py src/swe/app/subagents/registry.py tests/unit/subagents/test_skill_definitions.py tests/unit/subagents/test_definition_store_service.py tests/unit/subagents/test_definition_matcher.py
git commit -m "feat(subagents): resolve skill-owned definition catalog"
```

### Task 3: Publish the Catalog Only Behind Explicit SubAgent Intent

**Files:**
- Modify: `src/swe/app/subagents/models.py`
- Modify: `src/swe/agents/tools/subagent_background.py`
- Modify: `src/swe/agents/react_agent.py`
- Test: `tests/unit/subagents/test_background_tools.py`
- Test: `tests/unit/subagents/test_react_agent_and_guard_integration.py`

- [ ] **Step 1: Write failing tool schema and registration tests.**

```python
async def test_start_subagent_resolves_skill_owned_definition_without_instruction(
    tmp_path: Path,
) -> None:
    tools = create_background_subagent_tools(
        supervisor=_supervisor(),
        parent_agent_config=_agent_config(tmp_path),
        workspace_dir=tmp_path,
        request_context={"tenant_id": "tenant-a", "agent_id": "default"},
        definition_catalog=_catalog(),
    )
    result = await tools["start_subagent"](
        name="security:reviewer",
        objective="Review the payment patch.",
        background="Focus on authorization changes.",
    )
    assert _json(result)["accepted"] is True


def test_main_agent_registers_directory_only_after_explicit_intent(tmp_path: Path):
    agent = _agent_with_skill_definition(tmp_path, current_user_text="delegate to a SubAgent")
    tool = SWEAgent._create_toolkit(agent).tools["start_subagent"]
    assert "security:reviewer" in tool.description
    assert "Review code" in tool.description

    hidden = _agent_with_skill_definition(tmp_path, current_user_text="review this patch")
    assert "start_subagent" not in SWEAgent._create_toolkit(hidden).tools
```

- [ ] **Step 2: Run the tool tests and verify they fail.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_background_tools.py tests/unit/subagents/test_react_agent_and_guard_integration.py -q`

Expected: FAIL because `instruction` is currently required and no directory is included.

- [ ] **Step 3: Make `instruction` optional and render a bounded directory in the tool description.**

Change `SubAgentStartRequest.instruction` to `str | None = None`; preserve size validation only when it is present. Keep tool arguments as:

```python
async def start_subagent(
    name: str | None = None,
    objective: str | None = None,
    background: str = "",
    instruction: str | None = None,
    **extra: Any,
) -> ToolResponse:
```

In `SWEAgent._register_background_subagent_tools`, build the catalog from the current workspace/runtime channel only after `has_subagent_intent(request_context)` succeeds. Pass it to `create_background_subagent_tools`, and set the callable docstring/description to a bounded deterministic directory of qualified name, description, and trigger keywords. Keep `wait`, `get`, and `cancel` behavior unchanged; do not register `start_subagent` for `agent_role="subagent"`.

- [ ] **Step 4: Add start-result assertions.**

Assert an exact Skill-owned name creates a run with the resolved Definition instruction, a supplied instruction cannot override it, an unknown name with an instruction creates a run-scoped Definition, and an unknown name without an instruction returns `{"status": "not_found"}`.

- [ ] **Step 5: Run focused tests.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_background_tools.py tests/unit/subagents/test_react_agent_and_guard_integration.py -q`

Expected: PASS, including the existing explicit intent and no-nested-delegation tests.

- [ ] **Step 6: Commit the Main Agent entrypoint.**

```bash
git add src/swe/app/subagents/models.py src/swe/agents/tools/subagent_background.py src/swe/agents/react_agent.py tests/unit/subagents/test_background_tools.py tests/unit/subagents/test_react_agent_and_guard_integration.py
git commit -m "feat(subagents): expose skill-owned delegation directory"
```

### Task 4: Compose Parent-bounded Mutable Built-in Tool Policies

**Files:**
- Modify: `src/swe/app/subagents/models.py`
- Modify: `src/swe/app/subagents/permissions.py`
- Modify: `src/swe/agents/tools/subagent_background.py`
- Modify: `src/swe/agents/react_agent.py`
- Modify: `src/swe/agents/tool_guard_mixin.py`
- Test: `tests/unit/subagents/test_models_registry_policy.py`
- Test: `tests/unit/subagents/test_react_agent_and_guard_integration.py`

- [ ] **Step 1: Write failing policy tests for inherited writes and denial.**

```python
def test_skill_owned_tools_inherit_parent_then_apply_allow_and_deny():
    parent = parent_policy_from_enabled_tools(
        ["read_file", "write_file", "edit_file", "grep_search"],
    )
    definition = _skill_definition(
        tools={"inherit": True, "allow": ["read_file", "write_file", "edit_file"], "deny": ["write_file"]},
    )

    effective = resolve_skill_owned_policy(parent, definition)

    assert effective.tools.allow == ["edit_file", "read_file"]


@pytest.mark.asyncio
async def test_subagent_needing_approval_is_rejected_without_approval_ui(
    tmp_path: Path,
):
    result = await agent._acting(_guarded_write_call())
    assert "approval required" in _tool_text(result).lower()
    assert agent._acting_with_approval_called is False
```

- [ ] **Step 2: Run policy tests and verify they fail under the readonly MVP guard.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_models_registry_policy.py tests/unit/subagents/test_react_agent_and_guard_integration.py -q`

Expected: FAIL because `write_file` is outside `MVP_READONLY_TOOLS` and approval enters the interactive path.

- [ ] **Step 3: Resolve a concrete effective built-in set at launch.**

Replace `_parent_policy_from_config` with a helper that starts from currently enabled `ToolsConfig.builtin_tools`, excluding background-process controls and `start_subagent`. For a Skill-owned Definition:

```text
candidate = parent enabled built-ins when inherit=true, otherwise empty
candidate = candidate intersect allow when allow is non-empty
candidate = candidate minus deny
effective = candidate intersect parent/runtime/workspace policy
```

For built-in, Stored, and run-scoped Definitions, retain their current readonly defaults. Update `validate_tool_call` to allow known enabled built-ins in the computed policy rather than hard-rejecting every non-readonly tool; retain the readonly shell command policy unless a future feature separately changes shell policy.

- [ ] **Step 4: Enforce noninteractive approval and tool registration consistency.**

In `ToolGuardMixin._decide_guard_action`, return an auto-denied SubAgent action when a finding would otherwise create `needs_approval`; preserve normal preapprovals and automatic safe decisions. Keep the existing `agent_role="subagent"` early return in `_register_background_subagent_tools`. Make `_subagent_tool_settings` enumerate all supported built-in tools so a resolved `write_file`/`edit_file` policy is reflected in the worker Toolkit.

- [ ] **Step 5: Run policy and regression tests.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_models_registry_policy.py tests/unit/subagents/test_react_agent_and_guard_integration.py tests/unit/agents/test_tool_guard_hook_runtime.py -q`

Expected: PASS. Assert that a parent-disabled tool, a Definition-denied tool, and a guarded approval-required write all remain blocked.

- [ ] **Step 6: Commit bounded tool inheritance.**

```bash
git add src/swe/app/subagents/models.py src/swe/app/subagents/permissions.py src/swe/agents/tools/subagent_background.py src/swe/agents/react_agent.py src/swe/agents/tool_guard_mixin.py tests/unit/subagents/test_models_registry_policy.py tests/unit/subagents/test_react_agent_and_guard_integration.py
git commit -m "feat(subagents): inherit bounded built-in tools"
```

### Task 5: Capture and Load Immutable Skill Package Snapshots

**Files:**
- Create: `src/swe/app/subagents/launch_snapshot.py`
- Modify: `src/swe/app/subagents/models.py`
- Modify: `src/swe/app/subagents/supervisor.py`
- Modify: `src/swe/app/subagents/worker.py`
- Modify: `src/swe/app/subagents/runtime.py`
- Modify: `src/swe/agents/react_agent.py`
- Test: `tests/unit/subagents/test_launch_snapshot.py`
- Test: `tests/unit/subagents/test_runtime_and_delegation.py`

- [ ] **Step 1: Write failing immutable-Skill snapshot tests.**

```python
def test_skill_snapshot_copies_only_effective_declared_skills(tmp_path: Path):
    snapshot = create_skill_snapshot(
        run_dir=tmp_path / "runs",
        workspace_dir=tmp_path / "workspace",
        effective_skill_names=["security", "python"],
        declared_skill_names=["security", "disabled", "missing"],
    )

    assert snapshot.loaded_skills == ["security"]
    assert snapshot.skipped_skills == ["disabled", "missing"]
    assert (snapshot.skill_roots["security"] / "SKILL.md").is_file()

    (tmp_path / "workspace" / "skills" / "security" / "SKILL.md").write_text("changed")
    assert snapshot.skill_roots["security"].joinpath("SKILL.md").read_text() != "changed"
```

- [ ] **Step 2: Run snapshot tests and verify they fail.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_launch_snapshot.py -q`

Expected: FAIL because `launch_snapshot.py` does not exist.

- [ ] **Step 3: Implement safe package-copy snapshots.**

Create `SubAgentLaunchSnapshot` and `SubAgentLaunchDiagnostics` Pydantic models. At supervisor start, resolve declared Skills only against current `resolve_effective_skills(workspace_dir, channel)` entries, copy selected package trees into `<run_store_dir>/<run_id>.skills/<skill-name>/`, and record their source freshness token. Reject a symlink or copy failure for that one dependency and add the name to `skipped_skills`; never follow a link outside the Skill root. Retain snapshots with the run record in the first release so detailed inspection remains reproducible.

- [ ] **Step 4: Add explicit Skill roots to the worker Agent.**

Add `workspace_skill_dirs: dict[str, Path] | None = None` to `SWEAgent`. When supplied, `_register_skills` must use exactly these roots, call `toolkit.register_agent_skill` for each, and build Skill runtime profiles/tool attribution only from that mapping. Existing Main Agent construction must keep its current `resolve_effective_skills` path. In the worker, set `enable_workspace_skills=True` only when the snapshot has roots; never load unrelated workspace Skills.

- [ ] **Step 5: Run worker and runtime tests.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_launch_snapshot.py tests/unit/subagents/test_runtime_and_delegation.py tests/unit/subagents/test_background_worker.py -q`

Expected: PASS. The old test that expects `enable_workspace_skills=False` remains true for an ordinary built-in SubAgent; add a Skill-owned assertion that only copied roots are registered.

- [ ] **Step 6: Commit immutable Skill loading.**

```bash
git add src/swe/app/subagents/launch_snapshot.py src/swe/app/subagents/models.py src/swe/app/subagents/supervisor.py src/swe/app/subagents/worker.py src/swe/app/subagents/runtime.py src/swe/agents/react_agent.py tests/unit/subagents/test_launch_snapshot.py tests/unit/subagents/test_runtime_and_delegation.py
git commit -m "feat(subagents): snapshot declared skill packages"
```

### Task 6: Independently Connect Declared MCP Clients from Private Snapshots

**Files:**
- Modify: `src/swe/app/subagents/launch_snapshot.py`
- Modify: `src/swe/app/subagents/models.py`
- Modify: `src/swe/app/subagents/supervisor.py`
- Modify: `src/swe/app/subagents/worker.py`
- Modify: `src/swe/app/subagents/runtime.py`
- Modify: `src/swe/app/subagents/permissions.py`
- Modify: `src/swe/agents/tool_guard_mixin.py`
- Test: `tests/unit/subagents/test_launch_snapshot.py`
- Test: `tests/unit/subagents/test_background_worker.py`
- Test: `tests/unit/subagents/test_react_agent_and_guard_integration.py`

- [ ] **Step 1: Write failing MCP snapshot and authorization tests.**

```python
def test_mcp_snapshot_contains_only_enabled_declared_clients_and_not_run_json_secrets(
    tmp_path: Path,
):
    snapshot = create_mcp_snapshot(
        run_dir=run_dir,
        mcp_config=_mcp_config(github=True, disabled=False),
        declared_names=["github", "disabled", "missing"],
    )
    assert snapshot.loaded_mcps == ["github"]
    assert snapshot.skipped_mcps == ["disabled", "missing"]
    assert "token" not in (run_dir / "run.launch.json").read_text()


def test_subagent_rejects_mcp_tool_from_unsnapshotted_server() -> None:
    assert not validate_tool_call(
        policy,
        "search_issues",
        {},
        mcp_server="unlisted-server",
    ).allowed
```

- [ ] **Step 2: Run MCP tests and verify they fail.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_launch_snapshot.py tests/unit/subagents/test_background_worker.py -q`

Expected: FAIL because no MCP snapshot or server-aware policy exists.

- [ ] **Step 3: Persist a private configuration snapshot without exposing credentials in run records.**

For enabled declared clients, serialize complete `MCPClientConfig` objects to `<run_store_dir>/<run_id>.mcp.json` with mode `0600`; record only the file path internally in `WorkerLaunchSpec`, never in `BackgroundSubAgentRunRecord`, compact APIs, or launch diagnostics. Keep `WorkerLaunchSpec.keep_only_safe_request_context` and secret-like-field stripping intact. The diagnostics retain only loaded/skipped server keys.

- [ ] **Step 4: Connect clients in the worker and enforce server scope.**

In `worker.py`, load the private file before constructing `SubAgentRuntime`, call the existing `_create_mcp_client_with_headers` once for each snapshotted client, catch/log failures, and pass only successful clients plus their client keys to runtime. Delete the private file after loading. In `runtime.py`, pass those clients to the fresh `SWEAgent` and call `register_mcp_clients`; in `ToolGuardMixin`, pass the resolved MCP server to `validate_tool_call` and reject any server outside `subagent_allowed_mcp_servers` in request context. Every successfully registered MCP tool continues through the normal guard and the noninteractive-approval rule.

- [ ] **Step 5: Run MCP and Tool Guard regressions.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_launch_snapshot.py tests/unit/subagents/test_background_worker.py tests/unit/subagents/test_react_agent_and_guard_integration.py tests/unit/app/mcp/test_http_header_resolution.py -q`

Expected: PASS. Assert failed connection omits the client without failing the run, and no secret appears in persisted run or launch diagnostics JSON.

- [ ] **Step 6: Commit independent MCP connections.**

```bash
git add src/swe/app/subagents/launch_snapshot.py src/swe/app/subagents/models.py src/swe/app/subagents/supervisor.py src/swe/app/subagents/worker.py src/swe/app/subagents/runtime.py src/swe/app/subagents/permissions.py src/swe/agents/tool_guard_mixin.py tests/unit/subagents/test_launch_snapshot.py tests/unit/subagents/test_background_worker.py tests/unit/subagents/test_react_agent_and_guard_integration.py
git commit -m "feat(subagents): connect declared mcp clients in workers"
```

### Task 7: Resolve Skill-owned Model References Without Affecting Legacy Definitions

**Files:**
- Modify: `src/swe/app/subagents/launch_snapshot.py`
- Modify: `src/swe/app/subagents/models.py`
- Modify: `src/swe/app/subagents/runtime.py`
- Modify: `src/swe/agents/react_agent.py`
- Modify: `src/swe/agents/model_factory.py`
- Test: `tests/unit/subagents/test_launch_snapshot.py`
- Test: `tests/unit/subagents/test_runtime_and_delegation.py`
- Test: `tests/unit/agents/test_model_factory_tenant.py`

- [ ] **Step 1: Write failing model selection tests.**

```python
def test_skill_owned_model_reference_resolves_configured_tenant_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = resolve_skill_owned_model_slot(
        tenant_id="tenant-a",
        definition=_skill_definition(model={"provider": "openai", "id": "gpt-5-mini"}),
        fallback=ModelSlotConfig(provider_id="anthropic", model="claude"),
    )
    assert resolved == ModelSlotConfig(provider_id="openai", model="gpt-5-mini")


def test_unknown_skill_owned_model_silently_uses_parent_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fallback = ModelSlotConfig(provider_id="anthropic", model="claude")
    assert resolve_skill_owned_model_slot(
        tenant_id="tenant-a",
        definition=_skill_definition(
            model={"provider": "missing", "id": "unavailable"},
        ),
        fallback=fallback,
    ) == fallback
```

- [ ] **Step 2: Run model tests and verify they fail.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_launch_snapshot.py tests/unit/subagents/test_runtime_and_delegation.py -q`

Expected: FAIL because no model-slot resolver or factory override exists.

- [ ] **Step 3: Resolve and snapshot a model slot only for Skill-owned Definitions.**

Use `ProviderManager.get_instance(tenant_id)`, `get_provider(provider_id)`, and `provider.has_model(model_id)` to validate a TOML `[model]`. Store only `ModelSlotConfig(provider_id, model)` in the launch snapshot. If no reference is present, it is unavailable, or the Definition is built-in/Stored/run-scoped, snapshot the parent tenant active slot instead. Do not accept Provider URLs, headers, or credentials in TOML.

- [ ] **Step 4: Add a narrow model-factory override.**

Extend `create_model_and_formatter` with `model_slot_override: ModelSlotConfig | None = None`; when supplied, use that already-validated slot in place of `_get_model_slot(manager)`, while retaining tenant resolution, formatter selection, tracing, retry, and rate-limit wrappers. Thread `model_slot_override` through the `SWEAgent` constructor solely for worker construction. Do not change any default caller.

- [ ] **Step 5: Run provider and runtime tests.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_launch_snapshot.py tests/unit/subagents/test_runtime_and_delegation.py tests/unit/agents/test_model_factory_tenant.py -q`

Expected: PASS. Assert a built-in and ordinary Stored Definition cannot select a different model even when a model field is injected in test data.

- [ ] **Step 6: Commit Skill-owned model selection.**

```bash
git add src/swe/app/subagents/launch_snapshot.py src/swe/app/subagents/models.py src/swe/app/subagents/runtime.py src/swe/agents/react_agent.py src/swe/agents/model_factory.py tests/unit/subagents/test_launch_snapshot.py tests/unit/subagents/test_runtime_and_delegation.py tests/unit/agents/test_model_factory_tenant.py
git commit -m "feat(subagents): select configured skill-owned models"
```

### Task 8: Persist Safe Launch Diagnostics and Expose Them Only in Detailed Inspection

**Files:**
- Modify: `src/swe/app/subagents/models.py`
- Modify: `src/swe/app/subagents/run_store.py`
- Modify: `src/swe/app/subagents/supervisor.py`
- Modify: `src/swe/agents/tools/subagent_background.py`
- Test: `tests/unit/subagents/test_background_run_store.py`
- Test: `tests/unit/subagents/test_background_tools.py`
- Test: `tests/unit/subagents/test_monitor_api.py`

- [ ] **Step 1: Write failing visibility tests.**

```python
def test_detailed_run_record_exposes_safe_launch_diagnostics(
    record: BackgroundSubAgentRunRecord,
) -> None:
    payload = _compact_record(record, include_details=True)
    assert payload["launch_diagnostics"] == {
        "resolved_model": {"provider_id": "openai", "model": "gpt-5-mini"},
        "loaded_skills": ["security"],
        "skipped_skills": ["disabled"],
        "loaded_mcps": ["github"],
        "skipped_mcps": ["offline"],
    }


def test_compact_start_projection_does_not_expose_launch_diagnostics(
    record: BackgroundSubAgentRunRecord,
) -> None:
    assert "launch_diagnostics" not in _serialize_start_result(record)
```

- [ ] **Step 2: Run the diagnostic tests and verify they fail.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_background_run_store.py tests/unit/subagents/test_background_tools.py tests/unit/subagents/test_monitor_api.py -q`

Expected: FAIL because records have no `launch_diagnostics` field.

- [ ] **Step 3: Persist only safe diagnostics.**

Add `launch_diagnostics: SubAgentLaunchDiagnostics | None` to `BackgroundSubAgentRunRecord` and pass it through `PerRunSubAgentRunStore.create`. Include it only in `_compact_record(..., include_details=True)`. It must contain only the selected provider/model IDs and loaded/skipped names; exclude source paths, MCP URL/headers/env, Skill document contents, raw Definition instruction, and any secret-like field.

- [ ] **Step 4: Verify monitor compatibility.**

Keep `start_subagent`, `wait_subagent`, monitoring snapshots, and regular `get_subagent` compact. Detailed `get_subagent(include_details=true)` is the sole public route for diagnostics; existing monitor APIs should continue to return their pre-feature schema.

- [ ] **Step 5: Run detailed API tests.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_background_run_store.py tests/unit/subagents/test_background_tools.py tests/unit/subagents/test_monitor_api.py -q`

Expected: PASS, including serialization tests that verify secret-like fields do not leak.

- [ ] **Step 6: Commit diagnostics.**

```bash
git add src/swe/app/subagents/models.py src/swe/app/subagents/run_store.py src/swe/app/subagents/supervisor.py src/swe/agents/tools/subagent_background.py tests/unit/subagents/test_background_run_store.py tests/unit/subagents/test_background_tools.py tests/unit/subagents/test_monitor_api.py
git commit -m "feat(subagents): expose detailed launch diagnostics"
```

### Task 9: Run End-to-end Contract Tests and Final Verification

**Files:**
- Modify: `tests/unit/subagents/test_background_tools.py`
- Modify: `tests/unit/subagents/test_background_worker.py`
- Modify: `tests/unit/subagents/test_react_agent_and_guard_integration.py`
- Modify: `tests/unit/agents/test_skill_freshness_token.py` only if package snapshots need a new freshness assertion
- Modify: `CONTEXT.md` only if implementation proves a documented term inaccurate
- Modify: `docs/adr/0023-skill-owned-subagent-definitions.md` only if implementation proves an ADR decision inaccurate

- [ ] **Step 1: Add one end-to-end launch-contract test.**

```python
@pytest.mark.asyncio
async def test_skill_owned_run_uses_exact_definition_snapshot_and_parent_bounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange an enabled Skill with agents/reviewer.toml, a disabled dependency,
    # an enabled declared MCP, an unavailable declared MCP, and a configured model.
    # Start through the explicit user-intent path.
    # Mutate the original SKILL.md and MCP config after the run starts.

    detailed = await supervisor.get(scope, run_id)

    assert detailed.definition_name == "security:reviewer"
    assert detailed.launch_diagnostics.loaded_skills == ["security"]
    assert detailed.launch_diagnostics.skipped_skills == ["disabled-skill"]
    assert detailed.launch_diagnostics.loaded_mcps == ["github"]
    assert detailed.launch_diagnostics.skipped_mcps == ["offline"]
    assert detailed.launch_diagnostics.resolved_model.model == "gpt-5-mini"
    assert worker_skill_document == "original skill instructions"
    assert "start_background_process" not in worker_builtin_tool_names
```

- [ ] **Step 2: Run the end-to-end test and verify it fails before its final fixture wiring.**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_background_tools.py -q`

Expected: FAIL only until the fixture uses the newly implemented launch contract; do not weaken any assertion to make it pass.

- [ ] **Step 3: Complete fixture wiring using real catalog, snapshot, and WorkerLaunchSpec paths.**

Use a fake MCP client factory and fake `SWEAgent` where network isolation is needed, but assert the actual supervisor -> launch JSON -> worker -> runtime parameter flow. Verify invalid TOML does not prevent a sibling Definition or normal Skill load, unknown names without an instruction return `not_found`, and run-scoped fallback still works when an instruction is supplied.

- [ ] **Step 4: Run the complete SubAgent suite.**

Run: `venv/bin/python -m pytest tests/unit/subagents -q`

Expected: PASS.

- [ ] **Step 5: Run adjacent Agent, MCP, and Skill regressions.**

Run: `venv/bin/python -m pytest tests/unit/agents/test_skill_runtime_profile.py tests/unit/agents/test_tool_guard_hook_runtime.py tests/unit/app/test_runner_hook_runtime.py tests/unit/app/mcp -q`

Expected: PASS.

- [ ] **Step 6: Run static and scope verification.**

Run: `venv/bin/python -m pre_commit run --files src/swe/app/subagents/skill_definitions.py src/swe/app/subagents/launch_snapshot.py src/swe/app/subagents/models.py src/swe/app/subagents/definition_service.py src/swe/app/subagents/permissions.py src/swe/app/subagents/supervisor.py src/swe/app/subagents/worker.py src/swe/app/subagents/runtime.py src/swe/agents/react_agent.py src/swe/agents/model_factory.py src/swe/agents/tool_guard_mixin.py src/swe/agents/tools/subagent_background.py`

Expected: PASS.

Before committing, run GitNexus `detect_changes()` and confirm only the planned SubAgent, Agent Toolkit, model factory, and targeted tests are affected; investigate any unplanned execution-flow impact.

- [ ] **Step 7: Commit final integration.**

```bash
git add tests/unit/subagents tests/unit/agents/test_skill_freshness_token.py CONTEXT.md docs/adr/0023-skill-owned-subagent-definitions.md
git commit -m "test(subagents): cover skill-owned delegation contract"
```

## Coverage Review

| Requirement | Tasks |
| --- | --- |
| `agents/<agent>.toml`, validation, invalid-file isolation | 1 |
| `<skill>:<local>` names and reserved ownership | 1, 2 |
| explicit Main Agent intent gate and catalog directory | 3 |
| exact Skill-owned selection plus legacy run-scoped fallback | 2, 3 |
| instruction + objective + background worker prompt | 3, 5, 9 |
| declared Skill-only loading and immutable package behavior | 5 |
| declared MCP independent connection and silent failures | 6 |
| cloud/local configured model selection and fallback | 7 |
| inherited built-ins, mutable writes, guard and approval boundaries | 4 |
| no nested delegation | 3, 4, 9 |
| launch snapshot diagnostics only in detailed inspection | 5, 6, 8 |
| existing built-in, Stored, and run-scoped compatibility | 2, 3, 4, 7, 9 |

## Plan Self-review

- All TOML, lifecycle, dependency, model, tool, approval, snapshot, audit, and compatibility decisions from ADR 0023 are mapped to one or more test-backed tasks.
- The plan introduces no new user-visible CRUD/UI surface, automatic delegation, nested delegation, arbitrary provider configuration, or tool/MCP permission bypass.
- Exact type names and method contracts are introduced before they are used in later tasks. Existing implementation symbols are named with their current file locations.
