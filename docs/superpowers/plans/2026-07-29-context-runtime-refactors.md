# Context Runtime Refactors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Reduce query-runtime and context-reference-directive complexity without changing behavior, and align background-task cleanup typing with asyncio Future contract.

**Architecture:** Retain every current entry point as an orchestration boundary. Extract cohesive private helpers for normalized references, request-derived runtime inputs, resource startup, and runtime finalization. Existing ordering, cleanup, hook block, timeout, and directive validation behavior remain unchanged.

**Tech Stack:** Python 3.11+, asyncio, dataclasses, pytest, pytest-asyncio, mypy, GitNexus.

---

## File map

| File | Change |
| --- | --- |
| src/swe/app/context_references.py | Accept asyncio.Future[Any] in the callback consumer. |
| tests/unit/app/test_context_references.py | Cover the bare-Future callback boundary. |
| src/swe/app/runner/context_references.py | Separate normalization, capability lookup, and rendering. |
| tests/unit/app/test_runner_context_references.py | Preserve deduplication, validation, ordering, and no-discovery behavior. |
| src/swe/app/runner/runner.py | Separate query inputs, resource startup, and runtime finalization. |
| tests/unit/app/test_runner_hook_runtime.py | Preserve normal, blocked, and skill-restoration paths. |

### Task 1: Correct the background-task callback contract

**Files:**
- Modify: src/swe/app/context_references.py:283-294
- Modify: tests/unit/app/test_context_references.py:1-20

- [ ] **Step 1: Record the type-check failure.**

Run:

~~~bash
pre-commit run mypy --files src/swe/app/context_references.py
~~~

Expected: diagnostics identify that cancellation, timeout, and async-release paths can supply a Future where _consume_task_outcome declares only Task[Any].

- [ ] **Step 2: Add a focused regression test.**

Add import asyncio and this test:

~~~python
def test_consume_task_outcome_accepts_plain_future() -> None:
    from swe.app.context_references import _consume_task_outcome

    loop = asyncio.new_event_loop()
    try:
        future: asyncio.Future[None] = loop.create_future()
        _consume_task_outcome(future)
        future.set_result(None)
        loop.run_until_complete(asyncio.sleep(0))
    finally:
        loop.close()
~~~

- [ ] **Step 3: Run the regression test.**

Run:

~~~bash
venv/bin/python -m pytest tests/unit/app/test_context_references.py::test_consume_task_outcome_accepts_plain_future -q
~~~

Expected: PASS; it documents the runtime interface the callback uses.

- [ ] **Step 4: Make the minimal source change.**

Replace only the type contract, retaining callback behavior:

~~~python
def _consume_task_outcome(task: asyncio.Future[Any]) -> None:
    """Retrieve a background task outcome without delaying the response."""

    def consume(completed: asyncio.Future[Any]) -> None:
        try:
            completed.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("Background MCP discovery task failed", exc_info=True)

    task.add_done_callback(consume)
~~~

- [ ] **Step 5: Verify and commit this isolated change.**

Run:

~~~bash
pre-commit run mypy --files src/swe/app/context_references.py
venv/bin/python -m pytest tests/unit/app/test_context_references.py -q
git add src/swe/app/context_references.py tests/unit/app/test_context_references.py
git diff --cached --check
git commit -m "fix(context): accept futures for background task cleanup"
~~~

Expected: no callback argument type diagnostics and all discovery tests pass.

### Task 2: Decompose context-reference directive construction

**Files:**
- Modify: src/swe/app/runner/context_references.py:123-203
- Modify: tests/unit/app/test_runner_context_references.py:20-106

- [ ] **Step 1: Run impact analysis before changing the function.**

Call:

~~~text
impact({
  repo: "CoPaw",
  target: "build_context_reference_directives",
  file_path: "src/swe/app/runner/context_references.py",
  kind: "Function",
  direction: "upstream",
  minConfidence: 0.8,
  maxDepth: 3,
  includeTests: true,
})
~~~

Expected: LOW risk; AgentRunner._prepare_query_runtime is the direct caller. Review it before editing.

- [ ] **Step 2: Add the no-MCP-discovery characterization.**

Add from unittest.mock import AsyncMock and this test:

~~~python
@pytest.mark.asyncio
async def test_context_reference_directives_skip_mcp_discovery_without_mcp_reference(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from swe.app.runner import context_references

    discover = AsyncMock(return_value=[])
    monkeypatch.setattr(context_references, "discover_mcp_tools", discover)

    directives = await context_references.build_context_reference_directives(
        workspace_dir=tmp_path,
        channel="console",
        agent_config=SimpleNamespace(mcp=None),
        references=[
            {
                "type": "workspace_file",
                "id": "workspace_file:media/missing.txt",
                "root": "media",
                "relative_path": "missing.txt",
            },
        ],
    )

    assert directives == []
    discover.assert_not_awaited()
~~~

- [ ] **Step 3: Run characterization tests before extracting code.**

Run:

~~~bash
venv/bin/python -m pytest \
  tests/unit/app/test_runner_context_references.py::test_context_reference_directives_skip_mcp_discovery_without_mcp_reference \
  tests/unit/app/test_runner_context_references.py::test_build_context_reference_directives_validates_and_deduplicates \
  tests/unit/app/test_runner_context_references.py::test_context_reference_file_validation_rejects_missing_and_symlink_escape -q
~~~

Expected: PASS before and after the behavior-preserving extraction.

- [ ] **Step 4: Extract normalized-reference and lookup helpers.**

Add these helpers above build_context_reference_directives:

~~~python
def _normalize_context_references(
    references: Iterable[object],
) -> list[tuple[ContextReferenceType, dict[str, object]]]:
    normalized: list[tuple[ContextReferenceType, dict[str, object]]] = []
    seen: set[tuple[str, str]] = set()
    for raw in islice(references, MAX_CONTEXT_REFERENCES):
        parsed = _valid_reference_parts(raw)
        if parsed is None:
            continue
        reference_type, values = parsed
        identity = (reference_type, str(values["id"]))
        if identity not in seen:
            seen.add(identity)
            normalized.append((reference_type, values))
    return normalized


def _skill_directives_by_name(
    *,
    workspace_dir: Path,
    channel: str,
    normalized: Iterable[tuple[ContextReferenceType, dict[str, object]]],
) -> dict[str, SkillUseDirective]:
    skill_names = [
        raw["name"]
        for reference_type, raw in normalized
        if reference_type == "skill"
        and isinstance(raw.get("name"), str)
        and raw.get("id") == f"skill:{raw['name']}"
    ]
    return {
        directive.name: directive
        for directive in build_skill_use_directives(
            workspace_dir=workspace_dir,
            channel=channel,
            selected_skill_names=skill_names,
        )
    }


async def _requested_mcp_tools_by_id(
    *,
    normalized: Iterable[tuple[ContextReferenceType, dict[str, object]]],
    agent_config: Any,
) -> dict[str, tuple[str, str]]:
    requested_ids = {
        str(raw["id"])
        for reference_type, raw in normalized
        if reference_type == "mcp_tool"
    }
    if not requested_ids:
        return {}
    available_tools = await discover_mcp_tools(
        manager=_AgentRunnerMCPClientProvider(),
        agent_config=agent_config,
    )
    return {
        tool.id: (tool.server, tool.name)
        for tool in available_tools
        if tool.id in requested_ids
    }
~~~

Move the existing per-type conversion loop into
_build_directives_from_normalized_references(...) -> list[ContextReferenceDirective].
The public function calls phases in this order: normalization, skill lookup,
MCP lookup, conversion. Retain every ID, root, path, symlink, availability,
input-cap, and output-order check.

- [ ] **Step 5: Run the complete directive test module and commit.**

Run:

~~~bash
venv/bin/python -m pytest tests/unit/app/test_runner_context_references.py -q
git add src/swe/app/runner/context_references.py tests/unit/app/test_runner_context_references.py
git diff --cached --check
git commit -m "refactor(context): split directive resolution stages"
~~~

Expected: all directive-resolution tests pass.

### Task 3: Decompose query-runtime preparation

**Files:**
- Modify: src/swe/app/runner/runner.py:149-190,2918-3130
- Modify: tests/unit/app/test_runner_hook_runtime.py:1070-1232

- [ ] **Step 1: Run impact analysis before changing the method.**

Call:

~~~text
impact({
  repo: "CoPaw",
  target: "_prepare_query_runtime",
  file_path: "src/swe/app/runner/runner.py",
  kind: "Method",
  direction: "upstream",
  minConfidence: 0.8,
  maxDepth: 3,
  includeTests: true,
})
~~~

Expected: LOW risk. Also trace the direct runtime path from _stream_single_query_attempt because private-method graph edges may be incomplete.

- [ ] **Step 2: Add the blocked-start regression.**

Copy the fixture arrangement from
test_prepare_query_runtime_logs_agent_build_duration; patch
_emit_runner_hook to return
MergedHookResult(decision=HookDecision.BLOCK, reason="blocked").
Name the test test_prepare_query_runtime_returns_blocked_start_result and assert:

~~~python
assert result.runtime is None
assert result.block_response is not None
assert result.blocked_chat is chat
assert result.blocked_mcp_clients == []
assert result.blocked_session_id == "session-1"
~~~

- [ ] **Step 3: Run the blocked, normal, and restoration characterizations.**

Run:

~~~bash
venv/bin/python -m pytest \
  tests/unit/app/test_runner_hook_runtime.py::test_prepare_query_runtime_returns_blocked_start_result \
  tests/unit/app/test_runner_hook_runtime.py::test_prepare_query_runtime_logs_agent_build_duration \
  tests/unit/app/test_runner_hook_runtime.py::test_prepare_query_runtime_restores_confirmed_skill_from_session_snapshot -q
~~~

Expected: PASS before and after extraction.

- [ ] **Step 4: Add a request-derived inputs dataclass.**

Immediately after _QueryPreflight, add:

~~~python
@dataclass
class _QueryRuntimeInputs:
    session_id: str
    user_id: str
    channel: str
    skip_history: bool
    agent_config: Any
    tenant_hooks: HookConfig
    hook_overlay: HookSessionOverlay
    env_context: str
    selected_context_directives: list[str]
    auth_token: str | None
    passthrough_headers: dict[str, str]
~~~

- [ ] **Step 5: Extract the three implementation stages.**

Replace the large pre-try body of _prepare_query_runtime with
await self._build_query_runtime_inputs(request=request, preflight=preflight).
That helper retains the existing log, environment context, hook context,
agent config, directive construction, prompt injections, hook configuration,
and cookie/header merge.

Add:

~~~python
async def _start_query_runtime_resources(
    self,
    *,
    request: AgentRequest,
    msgs: list[Any],
    inputs: _QueryRuntimeInputs,
) -> tuple[list[Any], Any, str, _RuntimeStartResult | None]:
    """Connect request resources and run the session-start hook."""
~~~

It connects clients, creates turn_id, obtains chat, generates the title, and
emits the session-start hook. On a block it returns the existing blocked result
as the final tuple item.

Add:

~~~python
async def _finalize_query_runtime(
    self,
    *,
    request: AgentRequest,
    query: str | None,
    msgs: list[Any],
    inputs: _QueryRuntimeInputs,
    mcp_clients: list[Any],
    chat: Any,
    turn_id: str,
    env_context: str,
) -> _QueryRuntime:
    """Create the agent and initialize session-skill state for one turn."""
~~~

Move unchanged agent creation/registration, duration logging, _QueryRuntime
creation, detector attachment, snapshot restoration, and declared-skill start
there. Keep the outer try/except in _prepare_query_runtime as the sole owner
of _cleanup_mcp_clients(mcp_clients).

- [ ] **Step 6: Run focused verification and commit.**

Run:

~~~bash
venv/bin/python -m pytest \
  tests/unit/app/test_runner_hook_runtime.py \
  tests/unit/app/test_runner_context_references.py \
  tests/unit/app/test_context_references.py -q
pre-commit run black --files src/swe/app/runner/runner.py src/swe/app/runner/context_references.py src/swe/app/context_references.py
pre-commit run mypy --files src/swe/app/runner/runner.py src/swe/app/runner/context_references.py src/swe/app/context_references.py
git add src/swe/app/runner/runner.py tests/unit/app/test_runner_hook_runtime.py
git diff --cached --check
git commit -m "refactor(runner): split query runtime preparation"
~~~

Expected: all focused tests and static checks pass; the original two functions
are orchestration-only.

### Task 4: Final scope and regression verification

**Files:**
- Verify: the three source files and three test files above.

- [ ] **Step 1: Run the full focused suite.**

Run:

~~~bash
venv/bin/python -m pytest \
  tests/unit/app/test_context_references.py \
  tests/unit/app/test_runner_context_references.py \
  tests/unit/app/test_runner_hook_runtime.py -q
~~~

Expected: exit code 0 and no failed tests.

- [ ] **Step 2: Inspect final scope before any final commit.**

Run:

~~~bash
git diff --check
git diff -- src/swe/app/context_references.py src/swe/app/runner/context_references.py src/swe/app/runner/runner.py tests/unit/app/test_context_references.py tests/unit/app/test_runner_context_references.py tests/unit/app/test_runner_hook_runtime.py
~~~

Call:

~~~text
detect_changes({ repo: "CoPaw", scope: "compare", base_ref: "main" })
~~~

Expected: no unexpected execution flows or symbols outside the query-runtime and
context-reference area. Treat all other pre-existing worktree changes as
user-owned and do not stage them.
