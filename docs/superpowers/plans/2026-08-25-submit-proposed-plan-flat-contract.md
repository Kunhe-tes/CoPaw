# Submit Proposed Plan Flat Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Goal Mode expose the same shallow, strict completion-criterion and constraint contract that it validates after confirmation.

**Architecture:** `GoalProposal` composes the existing Goal domain item types instead of accepting arbitrary dictionaries and validating keys by hand. The planning tool exposes these types in its callable signature, so the generated JSON schema describes the four criterion strings and two constraint arrays. The Goal Mode prompt supplies the same compact contract to models.

**Tech Stack:** Python 3.12, Pydantic v2, AgentScope tool schema generation, pytest.

**Workspace note:** `CLAUDE.md` requires direct work in the current repository unless the user explicitly asks for a worktree. Do not touch unrelated dirty files.

---

### Task 1: Lock down the public tool schema and validation behavior

**Files:**
- Modify: `tests/unit/agents/tools/test_planning.py:413-506`

- [ ] **Step 1: Write the failing valid-contract schema test**

Add `from pydantic import ValidationError`, then add this test:

```python
def test_submit_proposed_plan_schema_exposes_goal_contract_item_fields(
    tmp_path: Path,
) -> None:
    tool = create_submit_proposed_plan_tool(request_context={}, workspace_dir=tmp_path)
    toolkit = Toolkit()
    toolkit.register_tool_function(tool)

    parameters = toolkit.tools["submit_proposed_plan"].json_schema["function"]["parameters"]
    definitions = parameters["$defs"]
    assert set(definitions["CompletionCriterion"]["properties"]) == {
        "requirement",
        "observable_assertion",
        "verification_method",
        "expected_outcome",
    }
    assert set(definitions["GoalConstraints"]["properties"]) == {
        "must_preserve",
        "must_not_do",
    }
```

- [ ] **Step 2: Write the failing field-path validation test**

```python
@pytest.mark.asyncio
async def test_submit_proposed_plan_reports_the_invalid_criterion_field(
    tmp_path: Path,
) -> None:
    tool = create_submit_proposed_plan_tool(request_context={}, workspace_dir=tmp_path)

    with pytest.raises(ValidationError, match="expected_outcome"):
        await tool(
            objective="Ship a verified change",
            completion_criteria=[{
                "requirement": "Tests pass",
                "observable_assertion": "The focused suite succeeds",
                "verification_method": "Run pytest",
            }],
            constraints={"must_preserve": [], "must_not_do": []},
            autonomy_boundary="No deployment",
        )
```

- [ ] **Step 3: Run the new tests and verify red**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/agents/tools/test_planning.py::test_submit_proposed_plan_schema_exposes_goal_contract_item_fields \
  tests/unit/agents/tools/test_planning.py::test_submit_proposed_plan_reports_the_invalid_criterion_field -q
```

Expected: the schema test fails because the tool emits anonymous arbitrary dictionaries; the validation test fails because the current error does not identify `expected_outcome`.

### Task 2: Reuse shallow Goal domain types in the proposal and tool

**Files:**
- Modify: `src/swe/app/plans/models.py:139-162`
- Modify: `src/swe/agents/tools/planning.py:387-423`
- Test: `tests/unit/agents/tools/test_planning.py`

- [ ] **Step 1: Replace manual dictionary validation in `GoalProposal`**

Import the existing types and use them directly:

```python
from ..goals.models import CompletionCriterion, GoalConstraints


class GoalProposal(_StrictPlanModel):
    """Goal-ready proposal shared by explicit Goal Mode and Plan Mode."""

    card_type: Literal["goal_proposal"] = "goal_proposal"
    objective: str
    completion_criteria: list[CompletionCriterion] = Field(min_length=1)
    constraints: GoalConstraints
    autonomy_boundary: str
```

Keep `_goal_text_required`; remove `_validate_goal_criteria`. Do not change the Goal domain models.

- [ ] **Step 2: Expose the same shallow types from the callable signature**

```python
async def submit_proposed_plan(
    objective: str,
    completion_criteria: list[CompletionCriterion] | str,
    constraints: GoalConstraints | str,
    autonomy_boundary: str,
) -> ToolResponse:
```

Keep `_coerce_json_array` for the JSON-text alternative. If `constraints` is text, decode it with `json.loads`; pass the decoded value directly to `GoalProposal` for validation. Do not add aliases or normalization helpers.

- [ ] **Step 3: Run the two focused tests and verify green**

Run the command from Task 1, Step 3.

Expected: both tests pass; the error contains `expected_outcome` and the schema contains named shallow models.

- [ ] **Step 4: Run all planning-tool tests**

Run:

```bash
venv/bin/python -m pytest tests/unit/agents/tools/test_planning.py -q
```

Expected: all tests pass.

### Task 3: Make the Goal Mode prompt self-sufficient

**Files:**
- Modify: `src/swe/agents/react_agent.py:187-192`
- Test: `tests/unit/app/test_task_progress_switch.py`

- [ ] **Step 1: Write the failing prompt-contract test**

Add this method to `TestReactAgentTaskProgressPrompt`; it builds the system
prompt in Goal Proposal mode and asserts it contains all six canonical nested
field names:

```python
def test_build_sys_prompt_adds_goal_proposal_contract_shape(
    self,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        react_agent_module,
        "build_system_prompt_from_working_dir",
        lambda **_: "base prompt",
    )
    monkeypatch.setattr(react_agent_module, "build_multimodal_hint", lambda: "")
    agent = self._build_agent()
    agent._request_context = {"goal_mode_enabled": True}

    with bind_source_system_config(_build_effective_config(False)):
        prompt = SWEAgent._build_sys_prompt(agent)

    for field in (
        "requirement",
        "observable_assertion",
        "verification_method",
        "expected_outcome",
        "must_preserve",
        "must_not_do",
    ):
        assert field in prompt
```

- [ ] **Step 2: Run the prompt test and verify red**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/app/test_task_progress_switch.py::TestReactAgentTaskProgressPrompt::test_build_sys_prompt_adds_goal_proposal_contract_shape -q
```

Expected: it fails because `_GOAL_PROPOSAL_INSTRUCTION` only names top-level arguments.

- [ ] **Step 3: Add the compact contract template to `_GOAL_PROPOSAL_INSTRUCTION`**

Append concise instructions equivalent to:

```text
Each completion criterion must contain exactly: requirement,
observable_assertion, verification_method, expected_outcome (all non-empty
strings). constraints must contain exactly must_preserve and must_not_do
(string arrays). Do not use criterion, verification, verification_command, or
arrays for any criterion field.
```

Do not embed a long JSON payload or introduce additional fields.

- [ ] **Step 4: Run the prompt test and focused planning tests**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/app/test_task_progress_switch.py \
  tests/unit/agents/tools/test_planning.py -q
```

Expected: all selected tests pass.

### Task 4: Verify the end-to-end shallow contract

**Files:**
- Test: `tests/unit/agents/tools/test_planning.py`

- [ ] **Step 1: Add a JSON-text compatibility regression test**

Add `import json` and this test:

```python
@pytest.mark.asyncio
async def test_submit_proposed_plan_accepts_canonical_json_text_inputs(
    tmp_path: Path,
) -> None:
    tool = create_submit_proposed_plan_tool(request_context={}, workspace_dir=tmp_path)
    criteria = [{
        "requirement": "Tests pass",
        "observable_assertion": "The focused suite succeeds",
        "verification_method": "Run pytest",
        "expected_outcome": "exit 0",
    }]
    constraints = {"must_preserve": ["Existing behavior"], "must_not_do": []}

    response = await tool(
        objective="Ship a verified change",
        completion_criteria=json.dumps(criteria),
        constraints=json.dumps(constraints),
        autonomy_boundary="No deployment",
    )

    assert response.metadata["plan_interaction_card"]["completion_criteria"] == criteria
    assert response.metadata["plan_interaction_card"]["constraints"] == constraints
```

- [ ] **Step 2: Run the JSON-text regression test**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/agents/tools/test_planning.py::test_submit_proposed_plan_accepts_canonical_json_text_inputs -q
```

Expected: PASS; the existing JSON decoding path is a required compatibility
behavior, so this test may pass without a production change.

- [ ] **Step 3: Run the full focused verification set**

Run:

```bash
venv/bin/python -m pytest \
  tests/unit/agents/tools/test_planning.py \
  tests/unit/app/test_task_progress_switch.py -q
```

Expected: exit code 0 with no failures.

- [ ] **Step 4: Inspect the final diff scope**

Run:

```bash
git diff --check -- src/swe/app/plans/models.py src/swe/agents/tools/planning.py src/swe/agents/react_agent.py tests/unit/agents/tools/test_planning.py tests/unit/app/test_task_progress_switch.py
```

Expected: no whitespace errors and no modifications outside the planned files.
