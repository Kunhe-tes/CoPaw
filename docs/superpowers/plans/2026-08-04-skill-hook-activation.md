# Deterministic Skill Hook Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load skill hooks only from server-validated explicit selections or `SKILL.md` reads, and restrict actual skill attribution to exact skill-document and skill-asset evidence.

**Architecture:** The runner retains resolved `SkillUseDirective` objects until its startup hooks finish, then loads their hook sources into the persisted session overlay without creating detector state. The detector ignores inferred feature, declared-tool, MCP, keyword, hint, and sequence signals; it attributes only a resolved `SKILL.md` read or one unambiguous path below an enabled skill directory. Hook loading becomes an explicit activation flag, so asset attribution cannot bootstrap hooks.

**Tech Stack:** Python 3.10+, pytest, pytest-asyncio, Pydantic hook models.

---

## File Map

- `src/swe/app/runner/runner.py` — selection resolution, startup lifecycle, and persistent `HookSessionOverlay`.
- `src/swe/agents/skill_invocation_detector.py` — actual-use detection and skill tracing.
- `tests/unit/app/test_runner_hook_runtime.py` — selection loading, lifecycle order, and persistence.
- `tests/unit/agents/test_skill_invocation_detector.py` — exact evidence and prohibited-signal regression tests.
- `tests/unit/app/test_runner_session_skill_freshness.py` — session cleanup behavior.

### Task 1: Prove legacy runtime signals do not attribute a skill

**Files:**

- Modify: `tests/unit/agents/test_skill_invocation_detector.py:327-391, 659-740, 1125-1155, 2096-2440`

- [ ] **Step 1: Write the failing tests**

Replace tests that expect extension, keyword, tool-hint, sequence, declared-tool continuation, or MCP attribution with a parameterized detector test:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "tool_input", "mcp_server"),
    [
        ("execute_shell_command", {"command": "render report.md"}, None),
        ("execute_shell_command", {"command": "process keyword"}, None),
        ("execute_shell_command", {"command": "ordinary command"}, None),
        ("mcp_tool", {"query": "ordinary"}, "filesystem"),
    ],
)
async def test_runtime_never_attributes_legacy_inference_signals(...):
    detector = SkillInvocationDetector(inferencer=legacy_feature_inferencer)
    detector.set_enabled_skills(["sample"])
    assert await detector.on_tool_call(
        tool_name, tool_input, mcp_server
    ) == (None, {})
```

Add a separate configured-sequence case that also returns `(None, {})` after a real `SKILL.md` read.

- [ ] **Step 2: Verify RED**

Run:

```bash
/Users/shixiangyi/code/Swe/venv/bin/python -m pytest tests/unit/agents/test_skill_invocation_detector.py -q
```

Expected: failures show the old inference/continuation path still returns the feature-associated skill.

### Task 2: Restrict detector activation to resolved paths

**Files:**

- Modify: `src/swe/agents/skill_invocation_detector.py:560-1125, 1342-1437`
- Modify: `tests/unit/agents/test_skill_invocation_detector.py`

- [ ] **Step 1: Add exact-evidence RED tests**

Add these tests:

```python
async def test_reading_resolved_skill_md_activates_and_loads_hooks(...):
    loader = AsyncMock()
    detector = SkillInvocationDetector(
        workspace_dir=tmp_path, skill_hook_loader=loader
    )
    detector.set_enabled_skills(["sample"])
    skill, weights = await detector.on_tool_call(
        "read_file",
        {"file_path": str(tmp_path / "skills/sample/SKILL.md")},
    )
    assert (skill, weights) == ("sample", {"sample": 1.0})
    loader.assert_awaited_once_with("sample")

async def test_skill_asset_attribution_does_not_load_hooks(...):
    loader = AsyncMock()
    detector = SkillInvocationDetector(
        workspace_dir=tmp_path, skill_hook_loader=loader
    )
    detector.set_enabled_skills(["sample"])
    skill, weights = await detector.on_tool_call(
        "execute_shell_command",
        {"path": str(tmp_path / "skills/sample/scripts/run.py")},
    )
    assert (skill, weights) == ("sample", {"sample": 1.0})
    loader.assert_not_awaited()
```

- [ ] **Step 2: Verify RED**

Run the Task 1 command. Expected: the asset case fails because `start_skill()` always loads hooks.

- [ ] **Step 3: Implement minimal exact activation**

Replace the runtime body of `on_tool_call()` with this ordered decision:

```python
skill_name = self._detect_skill_from_skill_md_read(tool_name, tool_input)
if skill_name is not None:
    return await self._activate_and_record_skill(
        skill_name, 1.0, tool_name, mcp_server, load_hooks=True
    )

skill_name = self._detect_skill_from_tool_input_assets(tool_input)
if skill_name is not None:
    return await self._activate_and_record_skill(
        skill_name, 1.0, tool_name, mcp_server, load_hooks=False
    )

return None, {}
```

Implement `_detect_skill_from_tool_input_assets()` by iterating the strings from `_iter_tool_input_strings()`, applying the existing resolved-directory helper to every enabled skill, and returning a name only for exactly one match. Thread `load_hooks: bool` through `_activate_and_record_skill()`, `_ensure_skill_active()`, and `start_skill()`; invoke `skill_hook_loader` only when it is true. Remove feature, message, declared-tool, MCP, hint, sequence, lock, and pending-continuation calls from runtime flow.

- [ ] **Step 4: Verify GREEN and commit**

Run:

```bash
/Users/shixiangyi/code/Swe/venv/bin/python -m pytest tests/unit/agents/test_skill_invocation_detector.py -q
git add src/swe/agents/skill_invocation_detector.py tests/unit/agents/test_skill_invocation_detector.py
git commit -m "fix(skills): require exact activation evidence"
```

Expected: detector tests pass; only exact skill-document and skill-asset evidence is attributed.

### Task 3: Load selected hooks after startup hooks without actual-use state

**Files:**

- Modify: `src/swe/app/runner/runner.py:164-205, 723-768, 3116-3178`
- Modify: `tests/unit/app/test_runner_hook_runtime.py:140-280, 2620-2668`

- [ ] **Step 1: Write runner RED tests**

Create a workspace skill containing a valid `hooks/hooks.json` and script. Patch `_emit_runner_hook` and assert explicit structured selection produces an overlay source only after startup:

```python
assert [call.args[0] for call in emit_hook.await_args_list] == [
    HookEventName.USER_PROMPT_SUBMIT,
    HookEventName.SESSION_START,
]
assert [source.source_id for source in runtime.hook_overlay.loaded_skill_sources] == [
    "skill:sample"
]
assert runtime.session_skill_detector._context_manager.current_skill is None
```

Add a two-turn test selecting `first`, then `second`, reloading session state, and reselecting `first`. Assert source order is `["skill:first", "skill:second"]` and the confirmed-skill callback remains uncalled.

- [ ] **Step 2: Verify RED**

Run:

```bash
/Users/shixiangyi/code/Swe/venv/bin/python -m pytest tests/unit/app/test_runner_hook_runtime.py -q
```

Expected: the selected source is absent because selection currently only renders a prompt directive.

- [ ] **Step 3: Implement selection-only overlay loading**

Add resolved `SkillUseDirective` objects to `_QueryRuntimeInputs` alongside rendered directives. Keep the directive order built from `context_references` and `selected_skill_names`. After `_emit_session_start_hook()` succeeds, call a runner helper that applies `load_skill_hooks_for_session()` in directive order:

```python
state: HookSessionState = inputs.hook_overlay
for directive in inputs.selected_skill_directives:
    state = load_skill_hooks_for_session(
        skill_name=directive.name,
        skill_root=directive.path.parent,
        workspace_dir=workspace_dir,
        session_state=state,
        approved_http_urls=approved_urls,
    )
inputs.hook_overlay = HookSessionOverlay.model_validate(
    state.model_dump(mode="json", by_alias=True)
)
```

Catch `SkillHookLoadError` per directive, log it, and continue. Do not call detector `start_skill()`, a trace method, or the confirmed-skill callback. The agent must be created only after this new overlay is assigned.

- [ ] **Step 4: Verify GREEN and commit**

Run:

```bash
/Users/shixiangyi/code/Swe/venv/bin/python -m pytest tests/unit/app/test_runner_hook_runtime.py -q
git add src/swe/app/runner/runner.py tests/unit/app/test_runner_hook_runtime.py
git commit -m "feat(hooks): load explicitly selected skill hooks"
```

Expected: hooks load after the two startup events, persist in source order, and produce no skill invocation attribution.

### Task 4: Confirm session cleanup and run final regression

**Files:**

- Modify: `tests/unit/app/test_runner_session_skill_freshness.py:950-1008`
- Modify only if RED proves necessary: `src/swe/app/runner/runner.py:4721-4815`

- [ ] **Step 1: Write session-boundary tests**

Extend the existing stale-overlay test to persist a selected source, invoke the normal clear/save path with `hook_overlay=None`, and assert:

```python
assert "hook_overlay" not in state
assert state["session_skill_snapshot"] == expected_snapshot
```

Add a query-level test that selects a skill in one session id, then starts a different session id with no selection and sees no loaded skill sources.

- [ ] **Step 2: Verify cleanup**

Run:

```bash
/Users/shixiangyi/code/Swe/venv/bin/python -m pytest \
  tests/unit/app/test_runner_session_skill_freshness.py \
  tests/unit/app/test_runner_hook_runtime.py -q
```

Expected: existing `_save_regular_session_state(..., hook_overlay=None)` removes the overlay while leaving the skill freshness snapshot intact. Fix only a failing clear/new-session path.

- [ ] **Step 3: Run final checks and commit**

Run:

```bash
/Users/shixiangyi/code/Swe/venv/bin/python -m pytest \
  tests/unit/agents/test_skill_invocation_detector.py \
  tests/unit/app/test_runner_hook_runtime.py \
  tests/unit/app/test_runner_session_skill_freshness.py -q
/Users/shixiangyi/code/Swe/venv/bin/python -m black --check \
  src/swe/agents/skill_invocation_detector.py \
  src/swe/app/runner/runner.py \
  tests/unit/agents/test_skill_invocation_detector.py \
  tests/unit/app/test_runner_hook_runtime.py \
  tests/unit/app/test_runner_session_skill_freshness.py
git diff --check
```

Run GitNexus `detect_changes()`, inspect affected processes, then commit only the Task 4 files if they changed:

```bash
git add src/swe/app/runner/runner.py \
  tests/unit/app/test_runner_session_skill_freshness.py \
  tests/unit/app/test_runner_hook_runtime.py
git commit -m "test(hooks): cover selected skill session lifecycle"
```

Expected: all focused tests and format checks pass; no legacy runtime signal reaches attribution or hook loading.

