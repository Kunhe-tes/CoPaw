# SubAgent Text Finalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace SubAgent native structured finalization with a single ordinary model call that produces only a final summary text.

**Architecture:** The research phase remains tool-enabled and bounded. The terminal call receives only the original `DelegationSpec` and a size-bounded chronological research record, reads plain model text, and constructs the runtime-owned `AgentResult`. Background tools continue to own lifecycle projection, but their nested terminal result becomes summary-only.

**Tech Stack:** Python 3, Pydantic, AgentScope `Msg`, pytest, existing Background SubAgent run store.

---

## Target

- Remove all structured SubAgent content types and contracts.
- Keep trusted `AgentResult` identity, status, metrics, and errors; keep only `summary` as model-authored content.
- Use one non-structured, tool-free final text call fed by `DelegationSpec` and a bounded research record for both normal and turn-limit exits.
- Preserve the agreed failure behavior and summary-only parent projection.

## Constraints

- Do not pass `structured_model`, parse JSON, retry a terminal call, or send Main Agent conversation state.
- Retire `expected_output` and `output_contract` without accepting legacy JSON; leave `schema_version` unchanged.
- Preserve the finalization turn reserve and the shared timeout budget.
- Prefer recent research messages; truncate an oversized entry to remaining capacity and mark it as truncated.
- Keep unrelated dirty changes untouched. Before each production-symbol edit, run GitNexus upstream impact analysis; before each commit, run `detect_changes`.

## Files and responsibilities

| File | Responsibility |
| --- | --- |
| `src/swe/app/subagents/models.py` | Define the reduced definition, delegation, and terminal-result contracts. |
| `src/swe/app/subagents/definition_service.py` | Construct stored and run-scoped definitions without an output contract. |
| `src/swe/app/subagents/builtins.py` | Remove structured-output wording and retired definition data. |
| `src/swe/app/subagents/runtime.py` | Produce and persist the text-finalized `AgentResult`. |
| `src/swe/agents/tools/subagent_background.py` | Project only terminal summary and optional finalization error code to the Main Agent. |
| `src/swe/app/subagents/__init__.py` | Stop re-exporting retired structured-result types. |
| `tests/unit/subagents/test_models_registry_policy.py` | Cover removed input fields and the reduced result contract. |
| `tests/unit/subagents/test_runtime_and_delegation.py` | Cover plain-text finalization, bounded context, terminal fallbacks, and turn-limit semantics. |
| `tests/unit/subagents/test_background_tools.py` | Cover the summary-only parent projection. |
| `CONTEXT.md`, `docs/adr/0022-subagent-text-finalization.md` | Record the new domain language and superseding decision. |

### Task 1: Retire structured contracts from the SubAgent models

**Files:**

- Modify: `src/swe/app/subagents/models.py:292-733`
- Modify: `src/swe/app/subagents/definition_service.py:1-110`
- Modify: `src/swe/app/subagents/builtins.py:10-80`
- Modify: `src/swe/app/subagents/__init__.py:13-95`
- Test: `tests/unit/subagents/test_models_registry_policy.py:28-180`

- [ ] **Step 1: Write failing model-contract tests**

```python
def test_definition_rejects_retired_output_contract() -> None:
    with pytest.raises(ValidationError):
        SubAgentDefinition.model_validate({
            "name": "analyst", "source": "stored",
            "description": "Checks facts.", "instruction": "Inspect facts.",
            "output_contract": "Return JSON.",
        })


def test_delegation_spec_rejects_retired_expected_output() -> None:
    with pytest.raises(ValidationError):
        DelegationSpec.model_validate({
            "name": "analyst", "objective": "Inspect facts.",
            "expected_output": {"format": "json"},
        })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_models_registry_policy.py -q`

Expected: FAIL because the retired fields are presently accepted.

- [ ] **Step 3: Reduce the contracts**

Remove `ExpectedOutput`; remove `output_contract` from `SubAgentDefinition` and `SubAgentRegistrationRequest`, including both validators; remove the structured content models used only by `SubAgentResponse`; define `AgentResult` directly with `summary` plus trusted runtime fields.

```python
class AgentResult(BaseModel):
    """Application-owned terminal result returned from a SubAgent run."""

    task_id: str
    agent_run_id: str
    agent_name: str
    status: AgentResultStatus
    summary: str
    metrics: Metrics = Field(default_factory=Metrics)
    errors: list[AgentError] = Field(default_factory=list)
```

Delete retired construction arguments from `SubAgentDefinitionService` and built-ins. Rewrite the built-in analyst instruction to ask for a concise evidence-based summary, and remove `SubAgentResponse` / `EvidenceRef` exports.

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_models_registry_policy.py -q`

Expected: PASS, including rejection of both retired fields.

- [ ] **Step 5: Commit the isolated model contract change**

```bash
git add src/swe/app/subagents/models.py src/swe/app/subagents/definition_service.py src/swe/app/subagents/builtins.py src/swe/app/subagents/__init__.py tests/unit/subagents/test_models_registry_policy.py
git commit -m "refactor(subagents): remove structured result contract"
```

### Task 2: Replace native structured finalization with plain text

**Files:**

- Modify: `src/swe/app/subagents/runtime.py:27-505`
- Test: `tests/unit/subagents/test_runtime_and_delegation.py:30-660`

- [ ] **Step 1: Write failing runtime tests**

Adjust the fake model to return `Msg("model", text, "assistant")`, then add tests that assert:

```python
assert created.finalization_kwargs == {}
assert result.summary == "final text"
assert result.status == "completed"

context = json.loads(created.finalization_prompt[1].get_text_content())
assert context["delegation_spec"]["task_id"] == "task-1"
assert "research_record" in context
```

Add separate tests for blank final text, terminal exception, and terminal timeout. Each normal-research failure must assert `status == "partial"`, `summary == "research synthesis"`, and `errors[0].code == "text_finalization_failed"`. Add an oversized-record test asserting the retained entry contains an explicit truncation marker rather than disappearing.

- [ ] **Step 2: Run the runtime tests to verify they fail**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_runtime_and_delegation.py -q`

Expected: FAIL because the runtime currently passes `structured_model=SubAgentResponse`, consumes metadata, and skips oversized entries.

- [ ] **Step 3: Implement text finalization and bounded evidence handoff**

Replace the normal/turn-limit context split with one context builder using `DelegationSpec` and `_bounded_research_record(research)`. Call the model without `structured_model`, consume a streamed response's final item when necessary, then validate non-blank text with `get_text_content()`.

```python
response = await agent.model(prompt)
if hasattr(response, "__aiter__"):
    last_response = None
    async for chunk in response:
        last_response = chunk
    response = last_response
summary = (response.get_text_content() if response else "").strip()
if not summary:
    raise ValueError("Text finalization returned no summary.")
return summary
```

Construct `AgentResult(summary=summary, ...)`. Rename structured-finalization constants and error code to `text_finalization_failed`. On text-finalization failures, use `_research_synthesis(research.reply)` as the partial summary; retain the existing fixed fallback when the reply has no text. Keep research-phase timeout/exception handling unchanged.

When serializing each research message, preserve chronological output while selecting newest records first. If a rendered entry exceeds remaining capacity, truncate its content and add `"truncated": true` before including it.

- [ ] **Step 4: Run the runtime tests to verify they pass**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_runtime_and_delegation.py -q`

Expected: PASS, with no test asserting structured metadata or `SubAgentResponse`.

- [ ] **Step 5: Commit the runtime change**

```bash
git add src/swe/app/subagents/runtime.py tests/unit/subagents/test_runtime_and_delegation.py
git commit -m "refactor(subagents): finalize with model text"
```

### Task 3: Narrow the parent-facing terminal projection

**Files:**

- Modify: `src/swe/agents/tools/subagent_background.py:395-462`
- Test: `tests/unit/subagents/test_background_tools.py:133-240`

- [ ] **Step 1: Write the failing projection tests**

Update the existing partial-terminal assertion and add a completed-terminal assertion:

```python
assert terminal["result"] == {
    "summary": "partial research",
    "error_code": "text_finalization_failed",
}

assert completed["result"] == {"summary": "completed research"}
```

- [ ] **Step 2: Run the tool tests to verify they fail**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_background_tools.py -q`

Expected: FAIL because the projection currently repeats result status and structured list fields.

- [ ] **Step 3: Implement the summary-only result projection**

Replace `_compact_agent_result` with a projection that always emits `summary` and conditionally emits only the final error code.

```python
payload = {"summary": result.summary}
if result.errors:
    payload["error_code"] = str(result.errors[-1].code or "")
return payload
```

Keep `_parent_facing_record` top-level lifecycle status and the existing failed-without-result fallback unchanged.

- [ ] **Step 4: Run the tool tests to verify they pass**

Run: `venv/bin/python -m pytest tests/unit/subagents/test_background_tools.py -q`

Expected: PASS, with terminal projections containing no structured content lists or duplicate result status.

- [ ] **Step 5: Commit the projection change**

```bash
git add src/swe/agents/tools/subagent_background.py tests/unit/subagents/test_background_tools.py
git commit -m "refactor(subagents): project terminal summaries only"
```

### Task 4: Align documentation and verify the integrated contract

**Files:**

- Modify: `CONTEXT.md:111-165`
- Create: `docs/adr/0022-subagent-text-finalization.md`
- Create: `docs/superpowers/specs/2026-08-11-subagent-text-finalization-design.md`
- Create: `docs/superpowers/plans/2026-08-11-subagent-text-finalization.md`
- Test: `tests/unit/subagents/test_models_registry_policy.py`
- Test: `tests/unit/subagents/test_runtime_and_delegation.py`
- Test: `tests/unit/subagents/test_background_tools.py`

- [ ] **Step 1: Verify the documents state the implemented terms**

Confirm that the glossary uses Text Finalization, Final Summary, and Bounded SubAgent Research Record; confirm ADR 0022 supersedes ADR 0021; confirm no document claims native structured output remains in this path.

- [ ] **Step 2: Run the focused regression suite**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/subagents/test_models_registry_policy.py \
  tests/unit/subagents/test_runtime_and_delegation.py \
  tests/unit/subagents/test_background_tools.py \
  tests/unit/subagents/test_background_run_store.py \
  tests/unit/subagents/test_background_worker.py \
  tests/unit/subagents/test_background_supervisor.py -q
```

Expected: PASS.

- [ ] **Step 3: Check the final changed-symbol scope**

Run GitNexus `detect_changes({scope: "all", repo: "CoPaw"})` and inspect that only the SubAgent model, runtime, tool projection, their tests, and agreed documentation are affected.

- [ ] **Step 4: Commit the documentation and verification result**

```bash
git add CONTEXT.md docs/adr/0022-subagent-text-finalization.md docs/superpowers/specs/2026-08-11-subagent-text-finalization-design.md docs/superpowers/plans/2026-08-11-subagent-text-finalization.md
git commit -m "docs(subagents): define text finalization"
```

## References

- `docs/superpowers/specs/2026-08-11-subagent-text-finalization-design.md`
- `docs/adr/0022-subagent-text-finalization.md`
- `docs/adr/0021-subagent-research-and-structured-finalization.md`
- `docs/adr/0011-background-subagent-tools-return-parent-facing-projections.md`
- `CONTEXT.md`
