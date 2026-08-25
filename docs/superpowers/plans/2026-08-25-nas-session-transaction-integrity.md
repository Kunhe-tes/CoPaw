# NAS Session Transaction Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop duplicate scheduled-session history by isolating request memory, serializing each NAS-backed session across its whole execution, and committing cron output as an idempotent delta.

**Architecture:** `SafeJSONSession` gains a long-lived `SessionExecution` guarded by the existing stable NAS lock file. Query attempts own one transaction and one fresh ReMe memory lease through retries; regular requests replace their state once, while cron requests append a delta guarded by a stable execution key. History APIs expose the original message identity.

**Tech Stack:** Python 3.12, asyncio, `fcntl.flock` on NAS, JSON with atomic replacement, AgentScope/ReMe, FastAPI, React/TypeScript, pytest, Vitest.

---

## File map

- Modify `src/swe/app/runner/session_lock.py`: permit a lock instance to be held by the transaction and add NAS-focused lock test support.
- Modify `src/swe/app/runner/session.py`: add the versioned envelope, `SessionExecution`, unlocked helpers, and parent-directory sync.
- Modify `src/swe/app/runner/query_attempt.py`, `query_cleanup.py`, `query_runtime.py`, and `session_lifecycle.py`: create, pass, use, and finally close one transaction per query; remove retry disk writes.
- Modify `src/swe/app/runner/runner.py`: replace cron full-memory merge with an idempotent append patch; route ordinary saves through the transaction.
- Modify `src/swe/app/crons/executor.py`: propagate a stable scheduler-provided execution key.
- Modify `src/swe/agents/memory/reme_light_memory_manager.py`, `src/swe/agents/react_agent.py`, `src/swe/agents/hooks/memory_compaction.py`, and `src/swe/agents/command_handler.py`: use request-owned memory and pass active memory explicitly to checkpoint operations.
- Modify `src/swe/app/runner/utils.py` and the Console history mapper: preserve raw message IDs.
- Add or extend focused tests under `tests/unit/app/`, `tests/unit/agents/`, and the existing Console session API tests.

### Task 1: Define and test the JSON execution transaction — completed (`05b11d8a6`)

**Files:**

- Modify: `src/swe/app/runner/session.py:77-140, 205-545`
- Modify: `src/swe/app/runner/session_lock.py:26-129`
- Modify: `tests/unit/app/test_runner_session.py`

- [ ] **Step 1: Write failing transaction tests.**

```python
@pytest.mark.asyncio
async def test_execution_holds_one_file_lock_and_commits_revision(tmp_path: Path) -> None:
    session = SafeJSONSession(save_dir=str(tmp_path))
    async with session.execution("session-1") as tx:
        assert await tx.read_state() == {}
        await tx.commit_state({"agent": {"memory": {"content": []}}})
    saved = await session.get_session_state_dict("session-1")
    assert saved["schema_version"] == 2
    assert saved["revision"] == 1


@pytest.mark.asyncio
async def test_second_execution_times_out_until_first_exits(tmp_path: Path) -> None:
    session = SafeJSONSession(save_dir=str(tmp_path))
    entered = asyncio.Event()
    release = asyncio.Event()

    async def hold_lock() -> None:
        async with session.execution("shared"):
            entered.set()
            await release.wait()

    holder = asyncio.create_task(hold_lock())
    await entered.wait()
    with pytest.raises(TimeoutError):
        async with session.execution("shared", timeout_seconds=0.01):
            pass
    release.set()
    await holder
```

- [ ] **Step 2: Run the focused tests and confirm they fail.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/app/test_runner_session.py -q`

Expected: FAIL because `SafeJSONSession.execution` does not exist.

- [ ] **Step 3: Add `SessionExecution` and envelope helpers.**

Create a small transaction class in `session.py` with `read_state()`, `commit_state(state)`, `revision`, and
async context-manager methods. Acquire one existing `AsyncSessionFileLock` for the full context. Normalize old files to
`schema_version=1`, `revision=0`; write `schema_version=2`, incremented `revision` on commit. Keep existing public
short-lock methods working for non-query callers.

Use a transaction-owned unlocked reader/writer so `commit_state()` never reacquires `.lock`. After `os.replace`, open
the parent directory read-only and `fsync` it when supported by the platform.

- [ ] **Step 4: Add process-level contention coverage.**

Extend the existing multiprocessing helper test so process A holds `session.execution("shared")` until an event is set;
assert process B cannot enter before that event and can enter after A exits. Keep this test local-filesystem only; the
two-Pod NAS test is an environment acceptance test, not a unit test.

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/app/test_runner_session.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the isolated transaction foundation.**

```bash
git add src/swe/app/runner/session.py src/swe/app/runner/session_lock.py tests/unit/app/test_runner_session.py
git commit -m "feat(session): add NAS-backed execution transaction"
```

### Task 2: Keep one transaction through query attempts and cleanup — completed (`0c1b2a4d2`)

**Files:**

- Modify: `src/swe/app/runner/query_attempt.py:229-567`
- Modify: `src/swe/app/runner/query_runtime.py:1-344`
- Modify: `src/swe/app/runner/query_cleanup.py:84-270`
- Modify: `src/swe/app/runner/session_lifecycle.py:80-155`
- Modify: `tests/unit/app/test_runner_session.py`
- Create: `tests/unit/app/test_query_session_execution.py`

- [ ] **Step 1: Write a failing retry regression test.**

```python
@pytest.mark.asyncio
async def test_retry_uses_one_transaction_and_writes_only_final_state() -> None:
    session = RecordingSession()
    runner = build_runner(session=session, agent_results=[RetryableError(), "done"])
    await collect(runner.stream_query(request_for("session-1")))
    assert session.execution_entries == 1
    assert session.commit_count == 1
    assert session.short_mutation_count == 0
```

- [ ] **Step 2: Run the regression test and confirm failure.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/app/test_query_session_execution.py -q`

Expected: FAIL because retry currently persists state before retry and cleanup uses a separate save path.

- [ ] **Step 3: Carry `session_tx` through runtime and retry state.**

Open `session.execution()` once in `stream_query_after_preflight()` before the retry loop. Add `session_tx` to the
runtime/retry state. Change `get_state_loaded()` to restore ordinary requests from `session_tx.read_state()` and to use
an empty request memory for `skip_history=True` requests.

Replace `save_state_before_retry()` disk persistence with an in-request `agent.state_dict()` snapshot. On the next retry,
load that snapshot into the new request-scoped Agent before continuing. Do not write JSON between attempts.

- [ ] **Step 4: Commit session state before unrelated cleanup.**

Make `cleanup_query_resources()` call the transaction-backed session commit serially first. Release the transaction
before running MCP cleanup, chat metadata updates, and QA storage concurrently. Route model failure detail and session
skill snapshot mutations through `session_tx.state` while it is active; prohibit calls to public short-lock mutation APIs
from the query path.

- [ ] **Step 5: Run focused query tests.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/app/test_query_session_execution.py tests/unit/app/test_runner_session.py tests/unit/app/test_runner_goal_lifecycle.py -q`

Expected: PASS.

- [ ] **Step 6: Commit query transaction integration.**

```bash
git add src/swe/app/runner/query_attempt.py src/swe/app/runner/query_runtime.py src/swe/app/runner/query_cleanup.py src/swe/app/runner/session_lifecycle.py tests/unit/app/test_query_session_execution.py tests/unit/app/test_runner_session.py
git commit -m "fix(runner): keep session state in one query transaction"
```

### Task 3: Make online ReMe memory request-owned — completed (`dc7c5eaff`)

**Files:**

- Modify: `src/swe/agents/memory/reme_light_memory_manager.py:53-104, 633-813`
- Modify: `src/swe/agents/react_agent.py:1441-1505`
- Modify: `src/swe/agents/hooks/memory_compaction.py:160-270`
- Modify: `src/swe/agents/command_handler.py:124-250`
- Modify: `tests/unit/agents/test_memory_compaction_archive.py`
- Create: `tests/unit/agents/test_request_memory_lease.py`

- [ ] **Step 1: Write failing memory-isolation tests.**

```python
def test_same_chat_gets_distinct_request_memories(manager) -> None:
    first = manager.create_request_memory(chat_id="chat-1")
    second = manager.create_request_memory(chat_id="chat-1")
    assert first is not second
    assert first.content == second.content == []


@pytest.mark.asyncio
async def test_checkpoint_install_uses_callers_active_memory(manager, memory) -> None:
    await manager.install_ready_precompaction(
        chat_id="chat-1", memory=memory, messages=[message("m1")]
    )
    assert memory.content == []
```

- [ ] **Step 2: Run the tests and confirm failure.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_request_memory_lease.py -q`

Expected: FAIL because `get_in_memory_memory(chat_id)` returns cached mutable memory and checkpoint APIs fetch it again.

- [ ] **Step 3: Replace mutable cache retrieval with memory creation.**

Add `create_request_memory(chat_id)` that obtains or clones an unbound ReMe object, clears content and summary, then
attaches the Chat archive. Do not retain the returned object in `_chat_memory_cache`; remove that cache's use for online
memory. Preserve manager access to archive/checkpoint stores without retaining request memory.

Pass `agent.memory` explicitly to precompaction/install/degraded checkpoint methods. Update `SWEAgent` construction to
receive the request memory lease. Update command handling to reset checkpoint epochs and clear content on its current
memory rather than fetching by chat ID.

- [ ] **Step 4: Add missing-session resurrection coverage.**

Create a memory with old content, simulate a missing session file, build a new request, and assert its memory contains
only the new request messages after save. Assert the old in-memory object is never reused.

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/agents/test_request_memory_lease.py tests/unit/agents/test_memory_compaction_archive.py -q`

Expected: PASS.

- [ ] **Step 5: Commit request memory isolation.**

```bash
git add src/swe/agents/memory/reme_light_memory_manager.py src/swe/agents/react_agent.py src/swe/agents/hooks/memory_compaction.py src/swe/agents/command_handler.py tests/unit/agents/test_request_memory_lease.py tests/unit/agents/test_memory_compaction_archive.py
git commit -m "fix(memory): isolate chat memory per request"
```

### Task 4: Replace cron full merge with an idempotent append patch — completed (`e81f3f6e9`)

**Files:**

- Modify: `src/swe/app/crons/executor.py:1045-1140, 1440-1475`
- Modify: `src/swe/app/runner/runner.py:488-530, 2589-2644, 5269-5406`
- Modify: `src/swe/app/runner/session_lifecycle.py:115-155`
- Modify: `tests/unit/app/test_runner_session.py`
- Create: `tests/unit/app/test_cron_session_append.py`

- [ ] **Step 1: Write failing append and idempotency tests.**

```python
@pytest.mark.asyncio
async def test_cron_appends_only_request_delta() -> None:
    tx = transaction_with_content([entry("u1"), entry("a1")])
    await commit_cron(tx, execution_key="job:fire:session", entries=[entry("u2"), entry("a2")])
    assert ids(tx.state["agent"]["memory"]["content"]) == ["u1", "a1", "u2", "a2"]


@pytest.mark.asyncio
async def test_same_execution_key_does_not_append_twice() -> None:
    tx = transaction_with_content([])
    await commit_cron(tx, execution_key="job:fire:session", entries=[entry("u1"), entry("a1")])
    await commit_cron(tx, execution_key="job:fire:session", entries=[entry("u1"), entry("a1")])
    assert len(tx.state["task_runs"]) == 1
    assert ids(tx.state["agent"]["memory"]["content"]) == ["u1", "a1"]
```

- [ ] **Step 2: Run the tests and confirm failure.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/app/test_cron_session_append.py -q`

Expected: FAIL because cron currently concatenates persisted content and the full Agent memory and uses a random run ID only.

- [ ] **Step 3: Propagate a stable execution key.**

Add a request field such as `cron_execution_key`. Populate it in `_build_agent_request()` from the scheduler's fixed
execution identity, job id, and target session id. Reuse the identical key for a scheduler retry. Do not derive it from
worker wall-clock time.

- [ ] **Step 4: Implement `commit_cron_append`.**

Make `_build_task_run_record()` accept `execution_key` while keeping its random display `run_id`. Remove
`_merge_cron_agent_memory()` and `_build_cron_merged_state()`. Build a `CronAppendPatch` from the request memory delta,
strip internal follow-ups, check existing `task_runs` for the execution key, append only once, calculate start/end from
the persisted baseline, and commit through `session_tx`.

- [ ] **Step 5: Add handoff and retry regression coverage.**

Test a manual regular request followed by a cron request on the same task session, then a cron retry; assert no old
user or assistant entries reappear and the task-history slicing remains valid.

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/app/test_cron_session_append.py tests/unit/app/test_cron_task_session_cleanup.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the cron append protocol.**

```bash
git add src/swe/app/crons/executor.py src/swe/app/runner/runner.py src/swe/app/runner/session_lifecycle.py tests/unit/app/test_cron_session_append.py tests/unit/app/test_runner_session.py
git commit -m "fix(cron): append idempotent session deltas"
```

### Task 5: Preserve persisted message identity through history and Console — completed (`af96d8c55`)

**Files:**

- Modify: `src/swe/app/runner/utils.py:332-366`
- Modify: `src/swe/app/runner/api.py:237-247, 590-603, 653-659`
- Modify: `console/src/pages/Chat/sessionApi/index.ts`
- Modify: `tests/unit/app/test_runner_tool_status.py`
- Create: `tests/unit/app/test_chat_history_message_identity.py`
- Create: `console/src/pages/Chat/sessionApi/messageIdentity.test.ts`

- [ ] **Step 1: Write failing stable-ID tests.**

```python
def test_history_conversion_keeps_raw_message_id() -> None:
    raw = Msg(name="user", role="user", content="question")
    raw.id = "raw-user-1"
    first, second = agentscope_msg_to_message([raw]), agentscope_msg_to_message([raw])
    assert [message.id for message in first] == ["raw-user-1"]
    assert [message.id for message in second] == ["raw-user-1"]


def test_missing_raw_id_uses_deterministic_legacy_identity() -> None:
    assert legacy_message_id("s1", 2, "t", "user", "q") == legacy_message_id("s1", 2, "t", "user", "q")
```

- [ ] **Step 2: Run the tests and confirm failure.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/app/test_chat_history_message_identity.py -q`

Expected: FAIL because the converter creates a new `ChatMessage` ID on every call.

- [ ] **Step 3: Preserve raw IDs and reconcile frontend history.**

Pass raw `Msg.id` into `ChatMessage`; retain it in `metadata.original_id`. For legacy missing IDs, derive the documented
deterministic hash from session id, position, timestamp, role, and normalized content. Update Console history mapping so
an incoming persisted ID replaces an equivalent temporary streaming card instead of appending another card.

- [ ] **Step 4: Add a task-history regression.**

Test task-run annotation twice against the same JSON and assert identical outer IDs, original IDs, task run IDs, and
message count. Add a Vitest case that loads the same history twice and asserts one card per persisted ID.

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/app/test_chat_history_message_identity.py tests/unit/app/test_runner_tool_status.py -q`

Run: `pnpm --dir console exec vitest run src/pages/Chat/sessionApi/messageIdentity.test.ts --reporter=dot`

Expected: PASS.

- [ ] **Step 5: Commit stable history identity.**

```bash
git add src/swe/app/runner/utils.py src/swe/app/runner/api.py console/src/pages/Chat/sessionApi/index.ts tests/unit/app/test_chat_history_message_identity.py tests/unit/app/test_runner_tool_status.py console/src/pages/Chat/sessionApi/messageIdentity.test.ts
git commit -m "fix(chat): preserve persisted history message ids"
```

### Task 6: Verify release readiness on NAS and perform the cutover — pending production validation

**Files:**

- Create: `scripts/verify_session_nas_lock.py`
- Create: `deploy/session-nas-lock-verification-job.yaml`
- Modify: `analysis/playbook/location-paths.md`

- [ ] **Step 1: Write the two-worker NAS verification script.**

The script accepts one shared session directory. Worker A takes `LOCK_EX` on `.verification.json.lock`, records entry,
and waits; worker B attempts `LOCK_EX | LOCK_NB` and must receive `EACCES` or `EWOULDBLOCK`. After A exits, B must
acquire the same lock. A second mode performs 1,000 serialized JSON commits and verifies `revision == 1000` and
successful JSON parsing after every commit.

- [ ] **Step 2: Package it as a two-Pod Kubernetes Job.**

Mount the production-equivalent session PVC into both Pods at the same path. The Job fails if lock contention,
post-owner-exit acquisition, JSON parsing, or revision continuity fails. Do not emit production application logs or
change application runtime configuration.

- [ ] **Step 3: Record the operational precondition.**

Add the verification command and the required pause/drain/full-replacement rollout sequence to
`analysis/playbook/location-paths.md`. State explicitly that old and new Runner versions must not overlap.

- [ ] **Step 4: Run all focused automated tests.**

Run: `PYTHONPATH=src venv/bin/python -m pytest tests/unit/app/test_runner_session.py tests/unit/app/test_query_session_execution.py tests/unit/app/test_cron_session_append.py tests/unit/app/test_chat_history_message_identity.py tests/unit/app/test_cron_task_session_cleanup.py tests/unit/agents/test_request_memory_lease.py tests/unit/agents/test_memory_compaction_archive.py -q`

Expected: PASS.

- [ ] **Step 5: Run the NAS Job and cut over without mixed versions.**

Run the two-Pod Job against the target StorageClass. If it passes: pause cron dispatch, drain running session requests,
scale old Pods to zero, deploy the new version to all Pods, run one ordinary and one cron smoke test against the same
task session, then resume cron dispatch. If the Job fails, do not deploy this design; retain the prior version and
evaluate a distributed lock backend.

- [ ] **Step 6: Commit release verification artifacts.**

```bash
git add scripts/verify_session_nas_lock.py deploy/session-nas-lock-verification-job.yaml analysis/playbook/location-paths.md
git commit -m "test(session): verify NAS lock contract"
```

## Plan self-review

- Scope coverage: Tasks 1-2 implement transaction and retry ownership; Task 3 isolates memory and preserves checkpoint
  behavior; Task 4 implements cron delta/idempotency; Task 5 fixes history identity; Task 6 validates the NAS precondition
  and non-overlap deployment.
- Intentional exclusions: no Redis, MySQL migration, deletion flow, archive deletion, automatic historical dedupe, or
  new runtime logging appear in any task.
- Consistency: `SessionExecution`, `create_request_memory`, `cron_execution_key`, `execution_key`, `commit_regular`, and
  `commit_cron_append` are defined before use and retain the same spelling across tasks.

## Current execution note

Tasks 1-5 are implemented and independently reviewed. Remaining work is operational: create/run the NAS verification
Job, record the result in the playbook, and perform a stop-the-world rollout so old and new writers never overlap.
Task 6 does not add Redis locking, deletion, automatic historical deduplication, or runtime logging.

The step checkboxes in Tasks 1-5 document the original TDD sequence; the completion state is recorded in each task
heading and by the commit IDs above.
