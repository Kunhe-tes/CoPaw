# ReMe Structured Chat Checkpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ReMe's Markdown-only compacted summary with a Chat-scoped structured checkpoint, event journal, recoverable evidence, and proactive precompaction candidates while preserving the existing memory message interface.

**Architecture:** A pure checkpoint domain module owns JSON data, validation, rendering, and budget decisions. The existing Chat archive persists records, journals, candidates, and source messages under its existing per-Chat lock; attached ReMe memory exposes the rendered record through `compressed_summary`. The hook schedules candidates at 65% plus each 5% increment, then installs a valid candidate at 80% or 90% before requesting a new ReMe compaction.

**Tech Stack:** Python 3.12, asyncio, dataclasses, AgentScope/ReMe, Pydantic v2, React/TypeScript, pytest, Vitest.

---

## File map

- Create `src/swe/agents/memory/chat_checkpoint.py`: immutable record, event, candidate, validator, Markdown projection, and stage decision types.
- Modify `src/swe/agents/memory/conversation_archive.py`: store `checkpoint.json`, `events.jsonl`, `candidates/*.json`, and epoch metadata beneath each existing validated Chat archive directory.
- Modify `src/swe/agents/memory/base_memory_manager.py`, `src/swe/agents/memory/reme_light_memory_manager.py`, and `src/swe/agents/hooks/memory_compaction.py`: expose record operations and drive scheduling/installation.
- Modify `tests/unit/agents/test_memory_manager_async_summary.py`, `tests/unit/agents/test_memory_manager_tenant_scope.py`, and `tests/unit/agents/test_memory_compaction_archive.py`: retain manager-protocol and archive compatibility coverage.
- Create `src/swe/agents/tools/recover_evidence.py`; modify `src/swe/agents/tools/__init__.py` and `src/swe/agents/react_agent.py`: register a Chat-bound recovery tool.
- Modify `src/swe/agents/command_handler.py` and `src/swe/app/runner/manager.py`: reset epochs and delete checkpoint data with Chats.
- Modify `src/swe/config/config.py`, `console/src/api/types/agent.ts`, `console/src/pages/Agent/Config/components/ContextCompactCard.tsx`, and `console/src/locales/zh.json`: configure 65/5/80/90 stages.
- Create focused pytest modules under `tests/unit/agents/` and a Vitest module beside `ContextCompactCard.tsx`.

### Task 1: Add staged configuration and Console controls

**Files:**

- Modify: `src/swe/config/config.py:372-465`
- Modify: `console/src/api/types/agent.ts:23-31`
- Modify: `console/src/pages/Agent/Config/components/ContextCompactCard.tsx`
- Modify: `console/src/locales/zh.json:1078-1088,1125-1140`
- Create: `tests/unit/config/test_context_compact_config.py`
- Create: `console/src/pages/Agent/Config/components/ContextCompactCard.test.tsx`

- [ ] **Step 1: Write failing configuration tests.**

```python
def test_context_compact_defaults_define_confirmed_stages() -> None:
    cfg = ContextCompactConfig()
    assert (cfg.lightweight_governance_ratio, cfg.precompaction_step_ratio) == (0.65, 0.05)
    assert (cfg.memory_compact_ratio, cfg.emergency_compact_ratio) == (0.80, 0.90)


def test_context_compact_rejects_non_monotonic_stage_ratios() -> None:
    with pytest.raises(ValidationError, match="lightweight.*active.*emergency"):
        ContextCompactConfig(
            lightweight_governance_ratio=0.80,
            memory_compact_ratio=0.75,
            emergency_compact_ratio=0.90,
        )
```

- [ ] **Step 2: Run the test to verify failure.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/config/test_context_compact_config.py -q`
Expected: FAIL because the staged fields and ordering validator do not exist.

- [ ] **Step 3: Add Pydantic fields and validation.**

```python
lightweight_governance_ratio: float = Field(default=0.65, ge=0.30, le=0.79)
precompaction_step_ratio: float = Field(default=0.05, ge=0.01, le=0.20)
memory_compact_ratio: float = Field(default=0.80, ge=0.31, le=0.89)
emergency_compact_ratio: float = Field(default=0.90, ge=0.32, le=0.95)

@model_validator(mode="after")
def validate_context_compact_stages(self) -> "ContextCompactConfig":
    if not self.lightweight_governance_ratio < self.memory_compact_ratio < self.emergency_compact_ratio:
        raise ValueError("lightweight, active, and emergency ratios must increase")
    return self
```

Preserve `memory_compact_ratio` as the active threshold for source-system compatibility. Do not add any new tool-output size field.

- [ ] **Step 4: Extend the public TypeScript type and card.**

Add the three properties to `ContextCompactConfig`, sliders and calculated token displays for “轻量治理阈值比例”, “预压缩增量比例”, and “紧急降级阈值比例”; retain `memory_compact_ratio` as “主动压缩阈值比例”. Explain in Chinese that candidate work is asynchronous and that 80%/90% prefer a valid candidate.

- [ ] **Step 5: Add and run UI coverage.**

```tsx
it("shows the staged 65/5/80/90 controls", () => {
  render(<ContextCompactCard maxInputLength={128_000} />);
  expect(screen.getByText("轻量治理阈值比例")).toBeInTheDocument();
  expect(screen.getByText("预压缩增量比例")).toBeInTheDocument();
  expect(screen.getByText("紧急降级阈值比例")).toBeInTheDocument();
});
```

Run: `pnpm --dir console exec vitest run src/pages/Agent/Config/components/ContextCompactCard.test.tsx --reporter=dot`
Expected: PASS.

- [ ] **Step 6: Verify and commit.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/config/test_context_compact_config.py -q`
Expected: PASS.

```bash
git add src/swe/config/config.py console/src/api/types/agent.ts console/src/pages/Agent/Config/components/ContextCompactCard.tsx console/src/locales/zh.json tests/unit/config/test_context_compact_config.py console/src/pages/Agent/Config/components/ContextCompactCard.test.tsx
git commit -m "feat(config): add staged context compaction thresholds"
```

### Task 2: Implement pure checkpoint state, event, candidate, and rendering logic

**Files:**

- Create: `src/swe/agents/memory/chat_checkpoint.py`
- Create: `tests/unit/agents/test_chat_checkpoint.py`

- [ ] **Step 1: Write failing model and projection tests.**

```python
def test_projection_keeps_six_reme_sections_and_recent_delta() -> None:
    record = CheckpointRecord.new(chat_id=CHAT_ID, epoch=1).with_current_task("Refactor compaction", ["tests pass"])
    text = render_checkpoint_projection(record, [event("tool_completed", exit_code=1)])
    for heading in ("## 目标", "## 约束和偏好", "## 进展", "## 关键决策", "## 下一步", "## 关键上下文"):
        assert heading in text
    assert "## Recent Event Delta" in text


def test_validator_rejects_done_progress_without_evidence() -> None:
    invalid = CheckpointRecord.new(chat_id=CHAT_ID, epoch=1).with_progress("done", "changed config", ())
    assert validate_checkpoint_record(invalid).errors == ["progress.done[0] requires evidence"]
```

- [ ] **Step 2: Run the test to verify failure.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_chat_checkpoint.py -q`
Expected: FAIL because `chat_checkpoint` does not exist.

- [ ] **Step 3: Add immutable types and pure functions.**

```python
@dataclass(frozen=True)
class CheckpointEvent:
    id: str
    sequence: int
    epoch: int
    occurred_at: str
    type: str
    facts: dict[str, JSONValue]
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class CheckpointRecord:
    schema_version: int
    checkpoint_id: str
    chat_id: str
    epoch: int
    revision: int
    applied_event_sequence: int
    confidence: Literal["verified", "degraded"]
    current_task: TaskState
    constraints_and_preferences: tuple[EvidenceItem, ...]
    progress: ProgressState
    key_decisions: tuple[Decision, ...]
    next_steps: tuple[NextStep, ...]
    critical_context: tuple[EvidenceItem, ...]
    risks_and_unverified: tuple[EvidenceItem, ...]
    completed_task_index: tuple[CompletedTask, ...]
```

Implement canonical JSON serialization, evidence-reference validation, candidate validation, the six-section Markdown renderer, a bounded event-delta renderer, and selection of whole interaction units. Raw tool output must be represented only by references.

- [ ] **Step 4: Add transition and candidate tests, then verify.**

```python
def test_candidate_cannot_mark_work_done_without_new_evidence() -> None:
    previous = record_with_in_progress("run regression", "message:1")
    candidate = replace_progress_status(previous, "run regression", "done", ())
    assert "unsupported progress transition" in validate_checkpoint_update(previous, candidate).errors
```

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_chat_checkpoint.py -q`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/swe/agents/memory/chat_checkpoint.py tests/unit/agents/test_chat_checkpoint.py
git commit -m "feat(memory): add structured chat checkpoint model"
```

### Task 3: Persist records, journals, candidates, and epochs with the archive

**Files:**

- Modify: `src/swe/agents/memory/conversation_archive.py:1-685`
- Modify: `tests/unit/agents/test_conversation_archive.py`
- Create: `tests/unit/agents/test_chat_checkpoint_store.py`

- [ ] **Step 1: Write failing transaction and stale-candidate tests.**

```python
@pytest.mark.asyncio
async def test_commit_checkpoint_archives_messages_and_activates_candidate(tmp_path) -> None:
    store = ConversationArchiveStore(tmp_path / "dialog")
    candidate = candidate_for(CHAT_ID, base_revision=0, applied_event_sequence=2)
    await store.write_pending_candidate(CHAT_ID, candidate)
    result = await store.commit_checkpoint(CHAT_ID, [_message(1)], candidate.id)
    assert result.record.revision == 1
    assert (tmp_path / "dialog" / CHAT_ID / "checkpoint.json").is_file()


@pytest.mark.asyncio
async def test_old_revision_candidate_is_not_activated(tmp_path) -> None:
    store = ConversationArchiveStore(tmp_path / "dialog")
    await store.write_active_checkpoint(CHAT_ID, checkpoint(revision=2))
    await store.write_pending_candidate(CHAT_ID, candidate_for(CHAT_ID, base_revision=1))
    assert await store.install_ready_candidate(CHAT_ID) is None
```

- [ ] **Step 2: Run the store test to verify failure.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_chat_checkpoint_store.py -q`
Expected: FAIL because checkpoint persistence APIs do not exist.

- [ ] **Step 3: Extend the archive behind its existing `_chat_lock`.**

Persist `checkpoint.json`, `events.jsonl`, `candidates/<candidate-id>.json`, and `epochs.json` inside the existing validated Chat directory. Add `append_checkpoint_event`, `read_checkpoint_state`, `write_pending_candidate`, `install_ready_candidate`, `commit_checkpoint`, `reset_checkpoint_epoch`, and `recover_evidence`. `commit_checkpoint` must atomically write the source archive batch and active record before exposing the manifest state; retain pending candidate data after activation failure for idempotent recovery.

- [ ] **Step 4: Test reset, deletion, and cross-epoch denial.**

```python
@pytest.mark.asyncio
async def test_reset_blocks_default_recovery_and_delete_removes_checkpoint_files(tmp_path) -> None:
    store = ConversationArchiveStore(tmp_path / "dialog")
    await store.append_checkpoint_event(CHAT_ID, event("message", epoch=1))
    await store.reset_checkpoint_epoch(CHAT_ID, reason="clear")
    assert await store.recover_evidence(CHAT_ID, epoch=2, refs=["message:1"]) == []
    await store.delete_chat(CHAT_ID)
    assert not store.path_for(CHAT_ID).exists()
```

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_chat_checkpoint_store.py tests/unit/agents/test_conversation_archive.py -q`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/swe/agents/memory/conversation_archive.py tests/unit/agents/test_chat_checkpoint_store.py tests/unit/agents/test_conversation_archive.py
git commit -m "feat(memory): persist chat checkpoints with archives"
```

### Task 4: Attach event journaling and checkpoint projection to ReMe memory

**Files:**

- Modify: `src/swe/agents/memory/conversation_archive.py`
- Modify: `src/swe/agents/memory/base_memory_manager.py`
- Modify: `src/swe/agents/memory/reme_light_memory_manager.py:429-584`
- Modify: `tests/unit/agents/test_memory_compaction_archive.py`
- Create: `tests/unit/agents/test_checkpoint_memory_attachment.py`

- [ ] **Step 1: Write failing attachment tests.**

```python
@pytest.mark.asyncio
async def test_attached_memory_appends_event_after_message_storage(tmp_path) -> None:
    memory = real_reme_memory()
    attach_conversation_archive(memory, tmp_path / "dialog", CHAT_ID)
    message = _message(1)
    await memory.add(message)
    state = await memory.chat_checkpoint_store.read_checkpoint_state(CHAT_ID)
    assert state.events[-1].source_refs == (f"message:{message.id}",)


@pytest.mark.asyncio
async def test_projection_exposes_markdown_not_checkpoint_json(tmp_path) -> None:
    memory = real_reme_memory()
    attach_conversation_archive(memory, tmp_path / "dialog", CHAT_ID)
    await memory.install_checkpoint_projection(checkpoint_with_goal("keep API stable"))
    assert "## 目标" in (await memory.get_memory())[0].get_text_content()
```

- [ ] **Step 2: Run the test to verify failure.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_checkpoint_memory_attachment.py -q`
Expected: FAIL because attached memory does not journal events or install projections.

- [ ] **Step 3: Wrap compatible memory operations and expose the manager protocol.**

Preserve original `add`, `get_memory`, `clear_content`, and `clear_compressed_summary` callables in `attach_conversation_archive`. Wrap `add` to append a deterministic event only after successful memory insertion. Install the renderer output in `_compressed_summary`, never raw JSON. Expose `archive_checkpoint_messages`, `schedule_precompaction`, `install_ready_precompaction`, `recover_evidence`, and `reset_context_epoch` through `ReMeLightMemoryManager`; update abstract methods and every fake manager in `test_memory_manager_async_summary.py` and `test_memory_manager_tenant_scope.py`.

- [ ] **Step 4: Verify ordering and compatibility.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_checkpoint_memory_attachment.py tests/unit/agents/test_memory_compaction_archive.py tests/unit/agents/test_memory_manager_async_summary.py tests/unit/agents/test_memory_manager_tenant_scope.py -q`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/swe/agents/memory/conversation_archive.py src/swe/agents/memory/base_memory_manager.py src/swe/agents/memory/reme_light_memory_manager.py tests/unit/agents/test_checkpoint_memory_attachment.py tests/unit/agents/test_memory_compaction_archive.py tests/unit/agents/test_memory_manager_async_summary.py tests/unit/agents/test_memory_manager_tenant_scope.py
git commit -m "feat(memory): journal events for chat checkpoints"
```

### Task 5: Add a request-bound evidence recovery tool

**Files:**

- Create: `src/swe/agents/tools/recover_evidence.py`
- Modify: `src/swe/agents/tools/__init__.py`
- Modify: `src/swe/agents/react_agent.py:712-775`
- Modify: `src/swe/agents/memory/base_memory_manager.py`
- Modify: `src/swe/agents/memory/reme_light_memory_manager.py`
- Create: `tests/unit/agents/test_recover_evidence_tool.py`

- [ ] **Step 1: Write failing binding and budget tests.**

```python
@pytest.mark.asyncio
async def test_recovery_uses_bound_chat_and_epoch() -> None:
    tool = create_recover_evidence_tool(manager, chat_id=CHAT_ID, epoch=2)
    await tool(refs=["archive:known"], query="stack trace", limit=1)
    manager.recover_evidence.assert_awaited_once_with(
        chat_id=CHAT_ID, epoch=2, refs=["archive:known"], query="stack trace",
        kinds=None, time_range=None, limit=1,
    )
```

- [ ] **Step 2: Run the test to verify failure.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_recover_evidence_tool.py -q`
Expected: FAIL because the tool factory does not exist.

- [ ] **Step 3: Implement the bound factory and register it beside memory search.**

```python
def create_recover_evidence_tool(memory_manager, *, chat_id: str, epoch: int):
    async def recover_evidence(refs=None, query=None, kinds=None, time_range=None, limit: int = 3) -> ToolResponse:
        return await memory_manager.recover_evidence(
            chat_id=chat_id, epoch=epoch, refs=refs, query=query,
            kinds=kinds, time_range=time_range, limit=min(limit, 10),
        )
    return recover_evidence
```

Register only for canonical request Chat IDs. Reject caller-supplied Chat IDs and raw paths in the store. Use exact checkpoint refs before semantic lookup, apply existing hidden-context redaction, and rely on `ToolOutputBudgetMixin`/`tool_result_compact` for response bounding.

- [ ] **Step 4: Test registration and denial paths.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_recover_evidence_tool.py tests/unit/agents/test_tool_output_budget_mixin.py -q`
Expected: PASS, including cross-Chat and prior-epoch rejection.

- [ ] **Step 5: Commit.**

```bash
git add src/swe/agents/tools/recover_evidence.py src/swe/agents/tools/__init__.py src/swe/agents/react_agent.py src/swe/agents/memory/base_memory_manager.py src/swe/agents/memory/reme_light_memory_manager.py tests/unit/agents/test_recover_evidence_tool.py
git commit -m "feat(agents): recover checkpoint evidence by chat"
```

### Task 6: Drive budget stages, proactive candidates, and safe installation

**Files:**

- Modify: `src/swe/agents/hooks/memory_compaction.py:28-314`
- Modify: `src/swe/agents/memory/reme_light_memory_manager.py:429-500`
- Create: `tests/unit/agents/test_memory_compaction_checkpoint.py`
- Modify: `tests/unit/agents/test_memory_compaction_archive.py`

- [ ] **Step 1: Write failing stage tests.**

```python
@pytest.mark.asyncio
async def test_governance_at_65_queues_one_candidate_per_five_percent_watermark() -> None:
    hook, memory = make_hook(projected_usage=0.65)
    await hook(agent_for(memory), {})
    memory.schedule_precompaction.assert_awaited_once()
    hook.projected_usage = 0.69
    await hook(agent_for(memory), {})
    assert memory.schedule_precompaction.await_count == 1
    hook.projected_usage = 0.70
    await hook(agent_for(memory), {})
    assert memory.schedule_precompaction.await_count == 2


@pytest.mark.asyncio
async def test_active_stage_installs_ready_candidate_before_new_reme_call() -> None:
    hook, memory = make_hook(projected_usage=0.80, candidate_installed=True)
    await hook(agent_for(memory), {})
    memory.install_ready_precompaction.assert_awaited_once()
    memory.compact_memory.assert_not_awaited()
```

- [ ] **Step 2: Run the test to verify failure.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_memory_compaction_checkpoint.py -q`
Expected: FAIL because the hook has a single synchronous threshold.

- [ ] **Step 3: Replace threshold orchestration with a pure decision object.**

```python
@dataclass(frozen=True)
class ContextBudgetDecision:
    projected_tokens: int
    ratio: float
    stage: Literal["normal", "governance", "active", "emergency"]
    precompaction_watermark: int | None


def decide_context_budget(projected_tokens: int, max_input_length: int, config: ContextCompactConfig) -> ContextBudgetDecision:
    ratio = projected_tokens / max_input_length
    if ratio >= config.emergency_compact_ratio:
        return ContextBudgetDecision(projected_tokens, ratio, "emergency", None)
    if ratio >= config.memory_compact_ratio:
        return ContextBudgetDecision(projected_tokens, ratio, "active", None)
    if ratio >= config.lightweight_governance_ratio:
        watermark = floor((ratio - config.lightweight_governance_ratio) / config.precompaction_step_ratio)
        return ContextBudgetDecision(projected_tokens, ratio, "governance", watermark)
    return ContextBudgetDecision(projected_tokens, ratio, "normal", None)
```

Count permanent prompt, checkpoint projection, event delta, online history, current input, model-output reserve, and recovered evidence. Governance compacts tool/retrieval material and schedules only an advanced watermark. Active/emergency first install a valid candidate, recompute, then invoke ReMe only if still needed. Emergency builds one deterministic degraded record and retries exactly once; it preserves current input and unpaired tool transactions.

- [ ] **Step 4: Add stale-candidate and concurrent-event tests.**

```python
@pytest.mark.asyncio
async def test_prefix_candidate_retains_later_events() -> None:
    memory = checkpoint_memory(base_revision=4, current_event_sequence=12)
    await memory.store_ready_candidate(candidate(base_revision=4, applied_event_sequence=10))
    assert await memory.install_ready_precompaction() is True
    assert await memory.pending_event_sequences() == [11, 12]
```

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_memory_compaction_checkpoint.py tests/unit/agents/test_memory_compaction_archive.py -q`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/swe/agents/hooks/memory_compaction.py src/swe/agents/memory/reme_light_memory_manager.py tests/unit/agents/test_memory_compaction_checkpoint.py tests/unit/agents/test_memory_compaction_archive.py
git commit -m "feat(memory): precompute checkpoint compaction candidates"
```

### Task 7: Enforce `/new`, `/clear`, and Chat deletion lifecycle

**Files:**

- Modify: `src/swe/agents/command_handler.py:132-245`
- Modify: `src/swe/app/runner/manager.py:330-350`
- Create: `tests/unit/agents/test_checkpoint_commands.py`
- Modify: `tests/unit/agents/test_memory_compaction_archive.py`

- [ ] **Step 1: Write failing command tests.**

```python
@pytest.mark.asyncio
async def test_new_closes_task_and_starts_new_epoch() -> None:
    handler, memory = make_handler_with_checkpoint(epoch=3)
    await handler._process_new([_message(1)])
    memory.reset_context_epoch.assert_awaited_once_with(reason="new")


@pytest.mark.asyncio
async def test_clear_blocks_automatic_recovery_of_prior_epoch() -> None:
    handler, memory = make_handler_with_checkpoint(epoch=3)
    await handler._process_clear([])
    memory.reset_context_epoch.assert_awaited_once_with(reason="clear")
```

- [ ] **Step 2: Run the test to verify failure.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_checkpoint_commands.py -q`
Expected: FAIL because commands clear only ReMe memory fields.

- [ ] **Step 3: Reset the epoch without changing physical deletion semantics.**

Call `reset_context_epoch(reason="new")` after closing the task into `completed_task_index` and before accepting the next message. Call `reset_context_epoch(reason="clear")` before clearing online content; do not call `delete_chat`. Keep `ChatManager.delete_chats` delegating to `ConversationArchiveStore.delete_chat`, whose Chat directory now contains all checkpoint files.

- [ ] **Step 4: Verify lifecycle behavior and commit.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_checkpoint_commands.py tests/unit/agents/test_memory_compaction_archive.py tests/unit/agents/test_conversation_archive.py -q`
Expected: PASS.

```bash
git add src/swe/agents/command_handler.py src/swe/app/runner/manager.py tests/unit/agents/test_checkpoint_commands.py tests/unit/agents/test_memory_compaction_archive.py
git commit -m "feat(memory): reset checkpoint epochs with chat commands"
```

### Task 8: Run end-to-end regressions and review final scope

**Files:**

- Test: `tests/unit/agents/test_chat_checkpoint.py`
- Test: `tests/unit/agents/test_chat_checkpoint_store.py`
- Test: `tests/unit/agents/test_checkpoint_memory_attachment.py`
- Test: `tests/unit/agents/test_recover_evidence_tool.py`
- Test: `tests/unit/agents/test_memory_compaction_checkpoint.py`

- [ ] **Step 1: Add a full candidate-to-recovery lifecycle test.**

```python
@pytest.mark.asyncio
async def test_checkpoint_survives_precompactions_then_active_install_and_recovery(tmp_path) -> None:
    runtime = make_checkpoint_runtime(tmp_path, max_input_length=100)
    await runtime.append_complete_turn(tokens=65)
    await runtime.await_candidate()
    await runtime.append_complete_turn(tokens=10)
    await runtime.await_candidate()
    await runtime.append_complete_turn(tokens=5)
    await runtime.pre_reasoning()
    assert runtime.active_record.revision == 1
    assert "initial hard constraint" in runtime.active_projection
    assert (await runtime.recover("archive:failure-output")).content
```

- [ ] **Step 2: Run focused backend regressions.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/config/test_context_compact_config.py tests/unit/agents/test_chat_checkpoint.py tests/unit/agents/test_chat_checkpoint_store.py tests/unit/agents/test_checkpoint_memory_attachment.py tests/unit/agents/test_recover_evidence_tool.py tests/unit/agents/test_memory_compaction_checkpoint.py tests/unit/agents/test_memory_compaction_archive.py tests/unit/agents/test_conversation_archive.py tests/unit/agents/test_tool_output_budget_mixin.py -q`
Expected: PASS; no cross-Chat recovery, no dropped unpaired transactions, and no unbounded tool output.

- [ ] **Step 3: Run frontend checks.**

Run: `pnpm --dir console exec vitest run src/pages/Agent/Config/components/ContextCompactCard.test.tsx --reporter=dot && pnpm --dir console exec tsc -b --noEmit`
Expected: both commands exit 0.

- [ ] **Step 4: Run compatibility and scope checks.**

Run: `git diff --check && PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_memory_manager_async_summary.py tests/unit/agents/test_memory_manager_tenant_scope.py -q`
Expected: no whitespace errors and all legacy manager tests pass.

- [ ] **Step 5: Run GitNexus review, commit, and report.**

Run GitNexus `detect_changes({scope: "all"})`. Inspect every high-risk changed process before committing. Commit any final documented contract change separately, then report staged thresholds, candidate-install behavior, recovery boundary, focused test output, and intentionally deferred migration work.
