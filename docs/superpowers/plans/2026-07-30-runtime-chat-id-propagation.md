# Runtime Chat ID Propagation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Propagate each query's persistent chat UUID to shell commands and MCP servers without changing the existing session ID contract.

**Architecture:** Extend the runtime invocation-claims value object with an optional `chat_id` and map it to runtime-owned environment and header keys. Resolve or create the chat before connecting query MCP clients, pass its UUID explicitly to initial and rebuilt clients, and nest the claim context around the agent execution so later shell commands read the same UUID.

**Tech Stack:** Python 3, Pydantic, `contextvars`, pytest, MCP HTTP/stdio clients.

---

### Task 1: Extend Runtime Claim Serialization

**Files:**
- Modify: `src/swe/runtime_invocation_claims.py:25-245`
- Test: `tests/unit/test_runtime_invocation_claims.py`

- [ ] **Step 1: Write the failing claim-serialization tests**

```python
def test_runtime_claim_env_includes_chat_id_and_replaces_static_value():
    env = apply_runtime_claim_env(
        {"SWE_CHAT_ID": "untrusted"},
        chat_id="chat-uuid-1",
    )
    assert env["SWE_CHAT_ID"] == "chat-uuid-1"


def test_runtime_claim_headers_include_chat_id_and_alias():
    headers = build_runtime_claim_headers(
        {"X-Swe-Chat-Id": "untrusted", "chatid": "untrusted"},
        chat_id="chat-uuid-1",
        include_aliases=True,
    )
    assert headers["x-swe-chat-id"] == "chat-uuid-1"
    assert headers["chatid"] == "chat-uuid-1"
```

- [ ] **Step 2: Run the claim tests and verify the expected missing-argument failure**

Run: `venv/bin/python -m pytest tests/unit/test_runtime_invocation_claims.py -q`

Expected: FAIL because the public claim builders do not yet accept or serialize `chat_id`.

- [ ] **Step 3: Add `chat_id` to the runtime claim contract**

```python
RUNTIME_CLAIM_ENV_KEYS = frozenset({
    "SWE_TENANT_ID", "SWE_SOURCE_ID", "SWE_RUNTIME_SCOPE_ID",
    "SWE_SESSION_ID", "SWE_CHAT_ID", "SWE_TRACE_ID",
})

_CANONICAL_HEADER_NAMES["chat_id"] = "x-swe-chat-id"
_ALIAS_HEADER_NAMES["chat_id"] = "chatid"

@dataclass(frozen=True)
class RuntimeInvocationClaims:
    chat_id: str | None = None
```

Thread `chat_id` through `build_runtime_invocation_claims`,
`runtime_invocation_claims_context`, `apply_runtime_claim_env`, and
`build_runtime_claim_headers`. Preserve the existing precedence: explicit
value, then current context, then no value. Runtime-owned keys must still be
removed before the generated value is inserted.

- [ ] **Step 4: Run the claim tests and verify they pass**

Run: `venv/bin/python -m pytest tests/unit/test_runtime_invocation_claims.py -q`

Expected: PASS.

### Task 2: Cover Environment and HTTP MCP Boundaries

**Files:**
- Modify: `tests/unit/test_shell_tenant_boundary.py:1451-1484`
- Modify: `tests/unit/app/test_mcp_stdio_process_limits.py:325-352`
- Modify: `tests/unit/app/test_runner_mcp_http_timeouts.py:137-250`
- Modify: `src/swe/app/mcp/stdio_launcher.py:39-81`
- Modify: `src/swe/app/mcp/http_headers.py:31-50`
- Modify: `src/swe/app/runner/runner.py:960-1110`
- Modify: `src/swe/agents/react_agent.py:1011-1085`

- [ ] **Step 1: Write failing boundary assertions**

```python
# Shell command JSON assertion
"'chat': os.environ.get('SWE_CHAT_ID'), "
assert '"chat": "chat-uuid-1"' in text

# stdio launch assertion
assert launch_config.env["SWE_CHAT_ID"] == "chat-uuid-1"

# HTTP MCP client assertion
assert headers["x-swe-chat-id"] == "chat-uuid-1"
assert headers["chatid"] == "chat-uuid-1"
```

- [ ] **Step 2: Run the boundary tests and verify they fail for absent chat propagation**

Run: `venv/bin/python -m pytest tests/unit/test_shell_tenant_boundary.py tests/unit/app/test_mcp_stdio_process_limits.py tests/unit/app/test_runner_mcp_http_timeouts.py -q`

Expected: FAIL only at the new `SWE_CHAT_ID`, `x-swe-chat-id`, or `chatid` assertions.

- [ ] **Step 3: Thread `chat_id` through MCP construction**

```python
async def _build_and_connect_mcp_clients(
    mcp_config: MCPConfig | None,
    passthrough_headers: dict[str, str] | None = None,
    session_id: str | None = None,
    chat_id: str | None = None,
    trace_id: str | None = None,
) -> list[Any]:
    client = await _create_mcp_client_with_headers(
        client_config, passthrough_headers, session_id, chat_id, trace_id,
    )

merged_headers = build_mcp_http_headers(
    client_config.headers,
    passthrough_headers=passthrough_headers,
    session_id=session_id,
    chat_id=chat_id,
    trace_id=trace_id,
)
```

Add the optional keyword to `build_mcp_http_headers` and forward it to
`build_runtime_claim_headers`. Add the same keyword-only argument to
`build_tenant_aware_stdio_launch_config` and pass it to
`apply_runtime_claim_env`. Thread `chat_id` through the two runner MCP builder
functions, save it in `_swe_rebuild_info`, and pass it to both the stdio and
HTTP reconstruction calls in `SWEAgent._rebuild_mcp_client`. Keep callers that
do not have a chat ID valid; they simply omit the new environment variable and
headers.

- [ ] **Step 4: Run the boundary tests and verify they pass**

Run: `venv/bin/python -m pytest tests/unit/test_shell_tenant_boundary.py tests/unit/app/test_mcp_stdio_process_limits.py tests/unit/app/test_runner_mcp_http_timeouts.py -q`

Expected: PASS.

### Task 3: Bind the Chat UUID for the Query Lifetime

**Files:**
- Modify: `src/swe/app/runner/runner.py:3116-3160,4320-4400`
- Test: `tests/unit/app/test_runner_hook_runtime.py`

- [ ] **Step 1: Write a failing query-lifecycle test**

```python
async def test_query_resolves_chat_before_connecting_mcp(monkeypatch):
    events = []

    async def fake_get_or_create_chat(*args, **kwargs):
        events.append("chat")
        return SimpleNamespace(id="chat-uuid-1")

    async def fake_connect(*args, **kwargs):
        events.append(("mcp", kwargs["chat_id"]))
        return []

    # Configure an AgentRunner with the fakes and execute one query attempt.
    assert events == ["chat", ("mcp", "chat-uuid-1")]
```

- [ ] **Step 2: Run the lifecycle test and verify it fails on current ordering**

Run: `venv/bin/python -m pytest tests/unit/app/test_runner_hook_runtime.py -q`

Expected: FAIL because MCP clients are currently connected before chat creation
and no chat ID exists in the active runtime claims.

- [ ] **Step 3: Reorder startup and scope the chat claim around agent execution**

```python
turn_id = f"turn-{uuid4().hex}"
chat = await self._get_or_create_chat(
    session_id=inputs.session_id,
    user_id=inputs.user_id,
    channel=inputs.channel,
    name=_chat_name_from_messages(msgs),
    request=request,
    turn_id=turn_id,
)
mcp_clients.extend(
    await _build_and_connect_mcp_clients(
        inputs.agent_config.mcp,
        passthrough_headers=inputs.passthrough_headers or None,
        session_id=inputs.session_id,
        chat_id=chat.id if chat is not None else None,
        trace_id=getattr(request, "trace_id", None),
    )
)

runtime = attempt_state.runtime_start.runtime
with runtime_invocation_claims_context(
    chat_id=runtime.chat.id if runtime.chat is not None else None,
):
    await self.get_state_loaded(
        runtime.agent, runtime.session_id, False,
        runtime.skip_history, runtime.user_id,
    )
    async for msg, last in self._stream_completion_lifecycle(
        request=attempt_input.request,
        runtime=runtime,
        plan=plan,
        outcome=outcome,
    ):
        yield msg, last
```

Move chat creation ahead of MCP connection in
`_start_query_runtime_resources`; pass `chat.id` to the MCP builder, or `None`
when the existing no-chat-manager fallback applies. In
`_stream_single_query_attempt`, enter the existing claim context with this chat
ID immediately after the runtime is available, then keep all state loading and
completion streaming inside that context. Its exit restores the outer context
on success, cancellation, or failure, without adding mutable global state.

Do not create a second `ContextVar` API. Task 1 already makes the existing
context manager merge `chat_id` with the active session and trace claims.

- [ ] **Step 4: Run the lifecycle test and verify it passes**

Run: `venv/bin/python -m pytest tests/unit/app/test_runner_hook_runtime.py -q`

Expected: PASS.

### Task 4: Verify Reconnect Preservation

**Files:**
- Modify: `tests/unit/app/mcp/test_http_header_resolution.py:178-275`

- [ ] **Step 1: Write failing reconnection assertions**

```python
assert captured[0]["headers"]["x-swe-chat-id"] == "chat-uuid-1"
assert captured[0]["headers"]["chatid"] == "chat-uuid-1"
assert captured[1]["headers"]["x-swe-chat-id"] == "chat-uuid-1"
assert captured[1]["headers"]["chatid"] == "chat-uuid-1"
```

- [ ] **Step 2: Run the reconnection test and verify it fails when metadata is absent**

Run: `venv/bin/python -m pytest tests/unit/app/mcp/test_http_header_resolution.py -q`

Expected: FAIL at the new chat-header assertions until `_swe_rebuild_info`
persists `chat_id` and `SWEAgent._rebuild_mcp_client` replays it.

- [ ] **Step 3: Preserve the chat ID in rebuild metadata**

```python
rebuild_info["chat_id"] = chat_id

headers = build_mcp_http_headers(
    rebuild_info.get("headers"),
    passthrough_headers=rebuild_info.get("passthrough_headers"),
    session_id=rebuild_info.get("session_id"),
    chat_id=rebuild_info.get("chat_id"),
    trace_id=rebuild_info.get("trace_id"),
)
```

For stdio reconstruction, pass
`chat_id=rebuild_info.get("chat_id")` to
`build_tenant_aware_stdio_launch_config`. This keeps an MCP server's identity
stable across recovery.

- [ ] **Step 4: Run the reconnection test and verify it passes**

Run: `venv/bin/python -m pytest tests/unit/app/mcp/test_http_header_resolution.py -q`

Expected: PASS.

### Task 5: Run Regression Checks and Review Change Scope

**Files:**
- Verify: `src/swe/runtime_invocation_claims.py`
- Verify: `src/swe/app/mcp/http_headers.py`
- Verify: `src/swe/app/runner/runner.py`
- Verify: affected tests from Tasks 1-4

- [ ] **Step 1: Run focused regression coverage**

Run: `venv/bin/python -m pytest tests/unit/test_runtime_invocation_claims.py tests/unit/test_shell_tenant_boundary.py tests/unit/app/test_mcp_stdio_process_limits.py tests/unit/app/test_runner_mcp_http_timeouts.py tests/unit/app/mcp/test_http_header_resolution.py tests/unit/app/test_runner_hook_runtime.py -q`

Expected: PASS.

- [ ] **Step 2: Inspect the changed execution scope**

Run: `git diff --check && git diff -- src/swe/runtime_invocation_claims.py src/swe/app/mcp/http_headers.py src/swe/app/runner/runner.py tests/unit/test_runtime_invocation_claims.py tests/unit/test_shell_tenant_boundary.py tests/unit/app/test_mcp_stdio_process_limits.py tests/unit/app/test_runner_mcp_http_timeouts.py tests/unit/app/test_runner_hook_runtime.py`

Expected: no whitespace errors; only runtime claim propagation, startup order,
and tests differ.

- [ ] **Step 3: Run GitNexus changed-scope analysis before committing**

Run: `detect_changes({repo: "CoPaw", scope: "all"})`

Expected: affected symbols are limited to the runtime claim and MCP/runner
startup paths; review any HIGH or CRITICAL finding before committing.
