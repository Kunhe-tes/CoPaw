# Hidden Context-Reference Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put Console-selected skill, MCP-tool, and workspace-file directives after the active user input, preserve the full prompt in persisted history, and exclude the internal suffix from the Console history API.

**Architecture:** Add a runner-owned helper that composes a delimited suffix and saves its exact value in message metadata. `AgentRunner._build_turn_plan` will replace only the active user `Msg` supplied to the model. The chat API will generate display-safe message copies before serializing them, leaving persisted memory unchanged.

**Tech Stack:** Python 3, AgentScope `Msg`, FastAPI/Pydantic, pytest.

---

## File structure

- Create: `src/swe/app/runner/hidden_context_injection.py` — compose, mark, and redact model-facing hidden user-message suffixes.
- Modify: `src/swe/app/runner/runner.py` — retain selected directives outside the system-prompt injection list, then append them to the active turn.
- Modify: `src/swe/app/runner/api.py` — sanitize marked messages in the Chat-history response.
- Create: `tests/unit/app/runner/test_hidden_context_injection.py` — composition/redaction unit coverage.
- Modify: `tests/unit/app/test_runner_system_prompt_injections.py` — runner integration coverage.
- Modify: `tests/unit/app/test_chat_api_message_timestamp.py` — history API redaction coverage.

### Task 1: Compose and mark hidden user-message context

**Files:**
- Create: `tests/unit/app/runner/test_hidden_context_injection.py`
- Create: `src/swe/app/runner/hidden_context_injection.py`

- [ ] **Step 1: Write the failing helper tests**

```python
from agentscope.message import Msg
from swe.app.runner.hidden_context_injection import (
    HIDDEN_CONTEXT_METADATA_KEY,
    append_hidden_context_to_user_message,
    redact_hidden_context_for_display,
)

def test_append_hidden_context_marks_the_model_facing_suffix():
    composed = append_hidden_context_to_user_message(
        Msg(name="alice", role="user", content="summarize this"),
        ["<TOOL-PREFERENCE>tool</TOOL-PREFERENCE>"],
    )
    assert composed.get_text_content() == (
        "summarize this\n\n<CONSOLE-HIDDEN-CONTEXT>\n"
        "<TOOL-PREFERENCE>tool</TOOL-PREFERENCE>\n"
        "</CONSOLE-HIDDEN-CONTEXT>"
    )
    assert composed.metadata[HIDDEN_CONTEXT_METADATA_KEY]["visible_text"] == "summarize this"

def test_redact_hidden_context_returns_a_display_safe_copy():
    composed = append_hidden_context_to_user_message(
        Msg(name="alice", role="user", content="summarize this"),
        ["<SKILL-USE>skill</SKILL-USE>"],
    )
    redacted = redact_hidden_context_for_display(composed)
    assert redacted.get_text_content() == "summarize this"
    assert HIDDEN_CONTEXT_METADATA_KEY not in redacted.metadata
    assert "<SKILL-USE>" in composed.get_text_content()

def test_redact_hidden_context_fails_closed_when_stored_suffix_is_inconsistent():
    message = Msg(
        name="alice", role="user",
        content="visible\n\n<CONSOLE-HIDDEN-CONTEXT>unexpected",
        metadata={HIDDEN_CONTEXT_METADATA_KEY: {
            "visible_text": "visible",
            "suffix": "\n\n<CONSOLE-HIDDEN-CONTEXT>expected",
        }},
    )
    assert redact_hidden_context_for_display(message).get_text_content() == "visible"
```

- [ ] **Step 2: Verify the test fails**

Run: `venv/bin/python -m pytest tests/unit/app/runner/test_hidden_context_injection.py -q`

Expected: collection fails because `swe.app.runner.hidden_context_injection` does not exist.

- [ ] **Step 3: Implement the minimal helper**

```python
HIDDEN_CONTEXT_METADATA_KEY = "console_hidden_context_v1"
_OPEN = "<CONSOLE-HIDDEN-CONTEXT>"
_CLOSE = "</CONSOLE-HIDDEN-CONTEXT>"

def append_hidden_context_to_user_message(message: Msg, directives: list[str]) -> Msg:
    rendered = [item.strip() for item in directives if item.strip()]
    if not rendered:
        return message
    visible_text = message.get_text_content()
    suffix = f"\n\n{_OPEN}\n{'\n\n'.join(rendered)}\n{_CLOSE}"
    return _copy_msg(
        message,
        content=visible_text + suffix,
        metadata={
            **(getattr(message, "metadata", None) or {}),
            HIDDEN_CONTEXT_METADATA_KEY: {
                "visible_text": visible_text,
                "suffix": suffix,
            },
        },
    )

def _copy_msg(message: Msg, *, content: str, metadata: dict) -> Msg:
    payload = message.model_dump(mode="json")
    payload["content"] = content
    payload["metadata"] = metadata
    return Msg.model_validate(payload)

def redact_hidden_context_for_display(message: Msg) -> Msg:
    marker = (getattr(message, "metadata", None) or {}).get(HIDDEN_CONTEXT_METADATA_KEY)
    if not isinstance(marker, dict):
        return message
    visible_text, suffix = marker.get("visible_text"), marker.get("suffix")
    if not isinstance(visible_text, str) or not isinstance(suffix, str):
        return message
    return _copy_msg(
        message,
        content=visible_text,
        metadata={
            key: value
            for key, value in (getattr(message, "metadata", None) or {}).items()
            if key != HIDDEN_CONTEXT_METADATA_KEY
        },
    )
```

Treat a mismatched suffix as redacted (fail closed).

- [ ] **Step 4: Verify the helper tests pass**

Run: `venv/bin/python -m pytest tests/unit/app/runner/test_hidden_context_injection.py -q`

Expected: PASS with 3 tests.

- [ ] **Step 5: Commit**

```bash
git add src/swe/app/runner/hidden_context_injection.py tests/unit/app/runner/test_hidden_context_injection.py
git commit -m "feat(chat): compose hidden context references"
```

### Task 2: Put selected directives on the active user turn

**Files:**
- Modify: `tests/unit/app/test_runner_system_prompt_injections.py:106-166`
- Modify: `src/swe/app/runner/runner.py:1674-1681, 2999-3020, 3127-3141`

- [ ] **Step 1: Write the failing runner integration test**

```python
@pytest.mark.asyncio
async def test_selected_context_directives_are_appended_to_user_turn_not_system_prompt(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "swe.app.runner.runner.build_context_reference_directives",
        AsyncMock(return_value=[
            MCPToolPreferenceDirective(server="docs", name="search"),
        ]),
    )
    env_context = await _run_query(monkeypatch, _request(context_references=[{
        "type": "mcp_tool", "id": "mcp_tool:docs:search",
        "server": "docs", "name": "search",
    }]), captured=captured)
    assert "<TOOL-PREFERENCE>" not in env_context
    assert "<TOOL-PREFERENCE>" in captured["messages"][-1].get_text_content()
```

Extend the module’s existing fake agent/stream helper so the test captures the actual list passed to `runtime.agent(turn_msgs)`.

- [ ] **Step 2: Verify the test fails**

Run: `venv/bin/python -m pytest tests/unit/app/test_runner_system_prompt_injections.py::test_selected_context_directives_are_appended_to_user_turn_not_system_prompt -q`

Expected: FAIL because the directive is still in `env_context`.

- [ ] **Step 3: Implement turn-local injection**

Keep `get_system_prompt_injections()` and `_request_system_prompt_injections(request)` in `_with_system_prompt_injections`. Remove the selected skill/context directive renders from that merge. Store their ordered renders on the runtime or turn-plan input, then use:

```python
original_user_message = query or _get_last_user_text(msgs) or ""
turn_msgs = list(msgs)
if turn_msgs and selected_context_directives and turn_msgs[-1].role == "user":
    turn_msgs[-1] = append_hidden_context_to_user_message(
        turn_msgs[-1], selected_context_directives,
    )
return _TurnPlan(
    original_user_message=original_user_message,
    turn_msgs=turn_msgs,
)
```

Do not recompute directives or accept rendered directive text from the browser. Preserve the existing deterministic ordering: selected skills first, then typed context references.

- [ ] **Step 4: Verify the runner tests pass**

Run: `venv/bin/python -m pytest tests/unit/app/test_runner_system_prompt_injections.py -q`

Expected: PASS, including source/request system-prompt injection regressions.

- [ ] **Step 5: Commit**

```bash
git add src/swe/app/runner/runner.py tests/unit/app/test_runner_system_prompt_injections.py
git commit -m "feat(chat): inject selected context after user input"
```

### Task 3: Redact internal suffixes from chat history responses

**Files:**
- Modify: `tests/unit/app/test_chat_api_message_timestamp.py:12-105`
- Modify: `src/swe/app/runner/api.py:123-143`

- [ ] **Step 1: Write the failing API regression test**

Add a `HiddenContextMemory` test double that returns:

```python
append_hidden_context_to_user_message(
    Msg(name="tester", role="user", content="hello"),
    ["<FILE-REFERENCE>/workspace/static/report.csv</FILE-REFERENCE>"],
)
```

Call the existing `/chats/chat-1` test app and assert:

```python
message = response.json()["messages"][0]
assert message["content"][0]["text"] == "hello"
assert "<FILE-REFERENCE>" not in str(response.json())
```

Extract the current FastAPI/dependency setup into `_build_test_client(memory_class)` so the timestamp regression uses the same fixture.

- [ ] **Step 2: Verify the API test fails**

Run: `venv/bin/python -m pytest tests/unit/app/test_chat_api_message_timestamp.py::test_get_chat_hides_marked_context_suffix_from_response -q`

Expected: FAIL because the raw persisted text is returned.

- [ ] **Step 3: Implement response-only redaction**

After `_messages_from_memory_state` and the existing task/approval annotations in `_build_chat_history`, adapt each user `ChatMessage` through `redact_hidden_context_for_display` and reconstruct a `ChatMessage` from its JSON model dump. Leave `memory_state`, the session file, and non-user messages untouched.

- [ ] **Step 4: Verify API tests pass**

Run: `venv/bin/python -m pytest tests/unit/app/test_chat_api_message_timestamp.py -q`

Expected: PASS, preserving the timestamp assertion and hiding internal directives.

- [ ] **Step 5: Commit**

```bash
git add src/swe/app/runner/api.py tests/unit/app/test_chat_api_message_timestamp.py
git commit -m "fix(chat): hide injected context from history API"
```

### Task 4: Verify the integrated change

**Files:**
- Modify: none

- [ ] **Step 1: Run focused regression tests**

Run: `venv/bin/python -m pytest tests/unit/app/runner/test_hidden_context_injection.py tests/unit/app/test_runner_system_prompt_injections.py tests/unit/app/test_chat_api_message_timestamp.py tests/unit/app/test_console_chat_system_prompt_injections.py -q`

Expected: PASS.

- [ ] **Step 2: Run formatting verification**

Run: `venv/bin/python -m black --check src/swe/app/runner/hidden_context_injection.py src/swe/app/runner/runner.py src/swe/app/runner/api.py tests/unit/app/runner/test_hidden_context_injection.py tests/unit/app/test_runner_system_prompt_injections.py tests/unit/app/test_chat_api_message_timestamp.py`

Expected: exit code 0.

- [ ] **Step 3: Run GitNexus change detection**

Run `detect_changes({ scope: "compare", base_ref: "main", repo: "CoPaw" })`. Review every changed symbol and execution flow; stop for explicit approval if the analysis reports HIGH or CRITICAL risk or an unexpected file.

- [ ] **Step 4: Confirm the working tree contains only expected files**

Run: `git status --short && git diff --check`

Expected: only the six implementation/test files listed in this plan are new or modified; no whitespace errors. Do not create an additional commit when the prior task commits already contain all changes.
