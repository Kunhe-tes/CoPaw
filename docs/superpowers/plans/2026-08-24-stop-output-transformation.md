# Stop Output Transformation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Let explicitly declared Stop Hooks serially replace final assistant text before concurrent completion validation and delivery.

**Architecture:** Add an opt-in outputTransform handler mode and a typed Stop-finalization result. The resolver identifies potential transformers before streaming, executes actual transformers serially against evolving text, then executes ordinary Stop validators concurrently against the final text. The runner buffers text only for an attempt with a potential transformer, replaces terminal Agent memory before validation, and releases only approved final text.

**Tech Stack:** Python 3.11, Pydantic v2, asyncio, FastAPI, pytest, React/TypeScript console.

---

## File map and non-negotiable boundaries

| Files | Responsibility |
| --- | --- |
| src/swe/agents/hook_runtime/{models,output,executor,resolver,runtime}.py | Schema, handler-output contract, source resolution, serial transformation and concurrent validation. |
| src/swe/config/config.py | Agent-owned total transformation budget. |
| src/swe/app/runner/{runner,turn_lifecycle}.py | Pre-stream buffer decision, memory replacement and delayed final delivery. |
| src/swe/app/hook_management.py and Console HookManagement files | One-handler manual test and configuration opt-in. |
| tests/unit/agents/hook_runtime/* and tests/unit/app/* | Regression and new end-to-end behavior. |
| wiki/hook/hook-runtime.md | Operator-facing contract. |

- Ordinary hooks and ordinary Stop handlers retain current concurrency and behavior.
- A transformer can only return allow; only a normal Stop validator can block completion.
- Potential means event + group matcher + scope + overlay match; its if is deliberately not evaluated until complete candidate text exists.
- Transformer order is tenant, Agent Profile, then activated Skills sorted by skill_name; declaration order remains within each source.
- Snapshots remain unchanged and may contain the original candidate. Telemetry contains only metadata, never candidate or replacement plaintext.
- No commit is included: the worktree has unrelated user changes and no commit authorization exists.

### Task 1: Define and test the opt-in configuration/output contract

**Files:**
- Modify: src/swe/agents/hook_runtime/models.py
- Modify: src/swe/agents/hook_runtime/output.py
- Modify: src/swe/agents/hook_runtime/executor.py
- Test: tests/unit/agents/hook_runtime/test_models_resolver.py
- Test: tests/unit/agents/hook_runtime/test_handlers_and_merge.py

- [ ] **Step 1: Write failing schema and normalizer tests.**

~~~python
def test_output_transform_is_valid_only_for_non_once_stop_handlers() -> None:
    parsed = HookConfig.model_validate({"enabled": True, "events": {
        "Stop": [{"hooks": [{"id": "format", "type": "command",
        "command": "echo", "outputTransform": True}]}],
    }})
    assert parsed.events[HookEventName.STOP][0].hooks[0].output_transform

    with pytest.raises(ValidationError, match="outputTransform"):
        HookConfig.model_validate({"enabled": True, "events": {
            "PreToolUse": [{"hooks": [{"id": "bad", "type": "command",
            "command": "echo", "outputTransform": True}]}],
        }})
    with pytest.raises(ValidationError, match="once"):
        HookConfig.model_validate({"enabled": True, "events": {
            "Stop": [{"hooks": [{"id": "bad", "type": "command",
            "command": "echo", "outputTransform": True, "once": True}]}],
        }})

def test_stop_transformer_accepts_only_allow_and_optional_replacement() -> None:
    result = normalize_hook_output(
        handler_id="format", order=0,
        raw_output={"decision": "allow", "hookSpecificOutput": {
            "replacementText": "final"}},
        event_name=HookEventName.STOP, output_transform=True,
    )
    assert result.replacement_text == "final"
~~~

Add cases for pass-through, block, whitespace/non-string replacement, unknown nested keys, and an undeclared normal Stop handler returning replacementText. Add equivalent prompt tests: transformer prompt output accepts decision, reason, and optional hookSpecificOutput; non-transformer prompt output remains exactly decision and reason.

- [ ] **Step 2: Run the focused tests to prove the red state.**

Run: venv/bin/python -m pytest tests/unit/agents/hook_runtime/test_models_resolver.py tests/unit/agents/hook_runtime/test_handlers_and_merge.py -q

Expected: FAIL because the flag, transformer result field and mode-aware output validators do not exist.

- [ ] **Step 3: Add the configuration field and validate it with the event available.**

In BaseHookHandlerConfig, add:

~~~python
output_transform: bool = Field(default=False, alias="outputTransform")
~~~

In HookConfig.validate_prompt_handler_events(), iterate every handler and reject outputTransform outside HookEventName.STOP, and outputTransform with once=True. Extract the event-aware handler check into a small helper so Hook Management can reuse it for an unsaved manual-test handler.

- [ ] **Step 4: Implement the narrow transformer output contract.**

Add replacement_text: str | None = None to HookHandlerResult. Change both normalizers to take output_transform: bool = False. Keep normal Stop validation unchanged. For a transformer, validate this policy:

~~~python
if output.decision != "allow":
    raise ValueError("Stop outputTransform has unsupported decision")
specific = output.hook_specific_output or {}
if set(specific) - {"replacementText"}:
    raise ValueError("Stop outputTransform has unsupported hookSpecificOutput")
replacement = specific.get("replacementText")
if replacement is not None and (
    not isinstance(replacement, str) or not replacement.strip()
):
    raise ValueError("Stop outputTransform replacementText must be non-empty")
~~~

Preserve a supplied replacement byte-for-byte; only use strip() for the non-empty check.

- [ ] **Step 5: Thread transformer mode through all handler families.**

Pass handler.output_transform to every command/HTTP normalizer call and the prompt normalizer. For prompt transformers, require exactly decision, reason, and optional hookSpecificOutput; decision must be allow; hookSpecificOutput may contain only non-empty replacementText. Preserve the existing ordinary prompt contract unchanged.

- [ ] **Step 6: Re-run contract coverage.**

Run: venv/bin/python -m pytest tests/unit/agents/hook_runtime/test_models_resolver.py tests/unit/agents/hook_runtime/test_handlers_and_merge.py -q

Expected: PASS, including existing ordinary Stop-output tests.

### Task 2: Resolve potential and actual transformer plans separately

**Files:**
- Modify: src/swe/agents/hook_runtime/models.py
- Modify: src/swe/agents/hook_runtime/resolver.py
- Test: tests/unit/agents/hook_runtime/test_models_resolver.py

- [ ] **Step 1: Write failing ordering and condition tests.**

Set loaded Skill activation order to zebra, alpha, and assert transformation order is tenant, Agent, skill:alpha, skill:zebra. Assert a transformer with if='assistant_response == "candidate"' makes requires_stop_output_buffer() true before text exists, but only enters the actual plan when evaluated with the matching current response.

~~~python
assert [item.source for item in plan.handlers] == [
    "tenant", "agent", "skill:alpha", "skill:zebra",
]
assert resolver.requires_stop_output_buffer(stop_context_without_text)
~~~

- [ ] **Step 2: Run the resolver test and verify it fails.**

Run: venv/bin/python -m pytest tests/unit/agents/hook_runtime/test_models_resolver.py -q

Expected: FAIL because resolution currently loses source identity, uses activation order and always evaluates if.

- [ ] **Step 3: Preserve source identity and add two resolver paths.**

Extend EffectiveHookHandler with source: str. Make _enabled_configs() yield source/config pairs: tenant, agent, then enabled activated Skills sorted by skill_name. Existing resolve_event_plan() keeps ordinary behavior. Add:

~~~python
def requires_stop_output_buffer(self, context: HookContext) -> bool:
    return bool(
        self.resolve_stop_transformer_plan(
            context,
            evaluate_if=False,
        ).handlers
    )
~~~

The predicate applies event/matcher/overlay/deduplication and filters output_transform, but skips _matches_if. The actual transformation plan uses the current context and evaluates if immediately before each handler runs. Add a normal-Stop-plan mode that excludes transformers so validators cannot execute twice.

- [ ] **Step 4: Re-run resolver tests.**

Run: venv/bin/python -m pytest tests/unit/agents/hook_runtime/test_models_resolver.py -q

Expected: PASS, including lexical Skill ordering and dynamic if coverage.

### Task 3: Implement serial transformation and concurrent validation in Hook Runtime

**Files:**
- Modify: src/swe/agents/hook_runtime/models.py
- Modify: src/swe/agents/hook_runtime/runtime.py
- Modify: src/swe/config/config.py
- Test: tests/unit/agents/hook_runtime/test_handlers_and_merge.py

- [ ] **Step 1: Write failing phase, failure and telemetry tests.**

Monkeypatch execute_handler() to record (handler.id, context.assistant_response) and return staged results. Assert the next transformer receives the prior replacement, validators receive only final text and overlap in execution, an allow-policy failure passes through, a block-policy failure stops unstarted handlers and validators, and time-budget exhaustion returns incomplete. Capture logger.info and assert telemetry includes metadata but neither candidate nor replacement text.

~~~python
assert seen == [("tenant-format", "candidate"), ("agent-format", "tenant text")]
assert validator_inputs == ["agent text", "agent text"]
assert validator_started_before_first_validator_finished
~~~

- [ ] **Step 2: Run the test to verify it fails.**

Run: venv/bin/python -m pytest tests/unit/agents/hook_runtime/test_handlers_and_merge.py -q

Expected: FAIL because HookRuntime.emit() currently uses one plan and asyncio.gather() for all handlers.

- [ ] **Step 3: Add a dedicated finalization result and runtime entry point.**

Define StopHookExecutionResult with final_response, validation_result, transformation_failed, and transformation_failure_reason. Leave HookRuntime.emit() unchanged for non-Stop callers; add:

~~~python
async def emit_stop_finalization(
    self, context: HookContext, *, workspace_dir: Path,
    max_transform_seconds: float,
    conversation_snapshot_provider: SnapshotProvider | None = None,
) -> StopHookExecutionResult:
    return await self._run_stop_transformers_then_validators(
        context=context,
        workspace_dir=workspace_dir,
        max_transform_seconds=max_transform_seconds,
        conversation_snapshot_provider=conversation_snapshot_provider,
    )
~~~

Capture one snapshot only when a transformer or later validator needs it; reuse that unmodified raw snapshot in both phases.

- [ ] **Step 4: Execute transformers serially under a single deadline.**

Set deadline = time.monotonic() + max_transform_seconds. Before each handler, compute remaining time; if non-positive, return a transformation failure. Clone the handler with timeout=min(handler.timeout, remaining) and execute it against context.model_copy(update={"assistant_response": current_text}). Apply only a non-None replacement_text. An allow-policy failure continues; a block-policy failure aborts and never starts later transformers or validators.

Write best-effort HOOK_TELEMETRY records with handler/source ID, replacement flag, old/new length and SHA-256, duration and failure/budget state. Catch telemetry exceptions and warn only.

- [ ] **Step 5: Run validators as the second, unchanged concurrent phase.**

Resolve only non-transforming Stop handlers after final text is known, execute them through existing asyncio.gather(), mark once only for validators, then merge with existing merge_hook_results(). A validator block must retain the existing automatic-follow-up semantics.

- [ ] **Step 6: Add the Agent-owned budget.**

Extend HookRuntimeRunningConfig with:

~~~python
max_stop_transform_seconds: float = Field(
    default=30.0, gt=0,
    description="Stop 输出变换流水线的总时限（秒）",
)
~~~

Read it exclusively from agent_config.running.hook_runtime; no tenant or Skill value may increase it.

- [ ] **Step 7: Re-run runtime regression tests.**

Run: venv/bin/python -m pytest tests/unit/agents/hook_runtime/test_handlers_and_merge.py tests/unit/agents/hook_runtime/test_models_resolver.py -q

Expected: PASS, including ordinary concurrent and snapshot tests.

### Task 4: Buffer candidate delivery and replace final Agent memory

**Files:**
- Modify: src/swe/app/runner/runner.py
- Modify: src/swe/app/runner/turn_lifecycle.py
- Test: tests/unit/app/test_runner_hook_runtime.py

- [ ] **Step 1: Write failing runner lifecycle tests.**

Cover a false text-dependent if (candidate withheld and emitted unchanged after finalization), two replacements (only final text reaches output and memory), validator block/follow-up (follow-up sees final text, never raw), transform block failure/time budget exhaustion (only incomplete notice; no follow-up), final-only monitor/suggestion input, unchanged snapshot candidate, and tool/progress/non-text frames remaining live.

~~~python
assert output_texts == ["tenant formatted"]
assert _extract_assistant_response(agent) == "tenant formatted"
assert indexed_response == "tenant formatted"
~~~

- [ ] **Step 2: Run runner tests and verify they fail.**

Run: venv/bin/python -m pytest tests/unit/app/test_runner_hook_runtime.py -q

Expected: FAIL because stream_agent_turns() yields candidate messages before _emit_stop_hook_if_needed().

- [ ] **Step 3: Decide buffering before stream output.**

Construct the Stop HookContext before stream_printing_messages() and use the matcher-only predicate. Store stop_output_buffer_required and retained text-bearing assistant Msg references in _QueryTurnOutcome. Do not run if at this point. Extend TurnLifecycleOwner with the narrow methods needed for buffer detection, strict Stop finalization, and final-memory replacement.

- [ ] **Step 4: Hold only text-bearing assistant output, retain live non-text events.**

When the flag is true, stream_agent_turns() retains assistant Msg objects with string content or `text` blocks rather than yielding them. It continues yielding tool progress, approvals, structured/media output, and non-assistant messages. If no text response is extractable, retain the existing no-transform/no-Stop path; do not coerce media or tool cards to text.

- [ ] **Step 5: Replace terminal memory before validation and emit only final text.**

Add a helper that finds the terminal current-turn assistant message with string content or text blocks and changes its text to final_response. Do not create a second assistant message or mutate snapshot data. _emit_stop_hook_if_needed() calls emit_stop_finalization(), applies the replacement before validation result handling, and turns transform failure into the existing blocking-failure shape.

After an allowed validator result, _stream_standard_completion_lifecycle() yields retained messages from final memory. On validator follow-up/block or transform failure, discard retained candidate messages. Keep immediate streaming untouched when no potential transformer exists.

- [ ] **Step 6: Run runner regression coverage.**

Run: venv/bin/python -m pytest tests/unit/app/test_runner_hook_runtime.py -q

Expected: PASS, including current Stop follow-up, persistence, trace, terminal-stop and snapshot tests.

### Task 5: Support isolated manual testing and Console opt-in

**Files:**
- Modify: src/swe/app/hook_management.py
- Modify: tests/unit/app/test_hook_management.py
- Modify: console/src/pages/Control/HookManagement/draft.ts
- Modify: console/src/pages/Control/HookManagement/index.tsx

- [ ] **Step 1: Write failing manual-test coverage.**

~~~python
async def test_manual_test_runs_single_stop_transformer_with_sample_response(
    service, actor, hook_script: Path,
) -> None:
    result = await service.manual_test(
        handler={"id": "format", "type": "command",
                 "argv": ["python", str(hook_script)], "outputTransform": True},
        context=_stop_context(assistant_response="sample candidate"), actor=actor,
    )
    assert result.handler_result.replacement_text == "sample final"
~~~

Also assert a non-Stop manual context rejects outputTransform before invoking the handler.

- [ ] **Step 2: Run the test and verify it fails.**

Run: venv/bin/python -m pytest tests/unit/app/test_hook_management.py -q

Expected: FAIL because manual parsing is not event-aware and summary lacks transformer metadata.

- [ ] **Step 3: Implement the isolated behavior.**

Validate the unsaved handler against context.hook_event_name, then execute only that one handler with supplied assistant_response. Add safe summary fields: output_transform, replacement_applied, and replacement length. Do not load other scopes, build a session, persist memory, invoke a pipeline, or deliver a response.

- [ ] **Step 4: Add the Console control.**

Default outputTransform to false. Show an “输出变换器” switch only for a Stop handler. Enabling it forces once: false, disables the once switch, and states that text is held until Stop finalization. Do not add a pipeline preview.

- [ ] **Step 5: Verify backend and Console.**

Run: venv/bin/python -m pytest tests/unit/app/test_hook_management.py -q

Expected: PASS.

Run: cd console && pnpm test:run

Expected: PASS; if this project has no configured matching test suite, run its documented type/lint command and report that substitution.

### Task 6: Update operations documentation and run the final gate

**Files:**
- Modify: wiki/hook/hook-runtime.md
- Verify: CONTEXT.md
- Verify: docs/adr/0029-stop-output-transformations-use-strict-two-phase-finalization.md
- Verify: docs/superpowers/specs/2026-08-24-stop-output-transformation-design.md

- [ ] **Step 1: Document the two-phase Stop contract.**

Replace the blanket statement that Stop runs after candidate output flows with conditional behavior: ordinary Stop remains post-stream, but a potential outputTransform: true buffers scalar text before if evaluation. Include this configuration and response contract:

~~~json
{"events":{"Stop":[{"hooks":[
  {"id":"format","type":"http","url":"https://policy.example/rewrite",
   "outputTransform":true,"timeout":5,"failPolicy":"block"},
  {"id":"audit","type":"command","argv":["python","hooks/scripts/audit_final.py"]}
]}]}}
~~~

~~~json
{"decision":"allow","reason":"formatted","hookSpecificOutput":{"replacementText":"final text"}}
~~~

Document order, 30-second Agent-owned total budget, failure policy, text-only scope, snapshot continuity, and serial transformers versus concurrent validators.

- [ ] **Step 2: Reconcile terminology without changing retention policy.**

Confirm CONTEXT.md, ADR 0029 and the approved design spec consistently use potential transformer, strict finalization, transformation pipeline, and validation phase. Do not alter snapshot logic or strip raw candidate content.

- [ ] **Step 3: Run the full relevant regression gate.**

Run: venv/bin/python -m pytest tests/unit/agents/hook_runtime tests/unit/app/test_runner_hook_runtime.py tests/unit/app/test_hook_management.py -q

Expected: PASS.

Run: venv/bin/python -m pre_commit run --files src/swe/agents/hook_runtime/models.py src/swe/agents/hook_runtime/output.py src/swe/agents/hook_runtime/resolver.py src/swe/agents/hook_runtime/runtime.py src/swe/agents/hook_runtime/executor.py src/swe/app/runner/runner.py src/swe/app/runner/turn_lifecycle.py src/swe/app/hook_management.py src/swe/config/config.py tests/unit/agents/hook_runtime/test_models_resolver.py tests/unit/agents/hook_runtime/test_handlers_and_merge.py tests/unit/app/test_runner_hook_runtime.py tests/unit/app/test_hook_management.py

Expected: PASS.

- [ ] **Step 4: Inspect changed scope before any optional commit.**

Run GitNexus detect_changes() and git diff --check; confirm changed symbols are confined to Hook Runtime, Stop lifecycle, Hook management and documentation. Report the result. Do not commit unless separately authorized.
