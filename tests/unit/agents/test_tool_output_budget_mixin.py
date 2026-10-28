# -*- coding: utf-8 -*-
"""Regression coverage for bounded AgentScope tool-result messages."""

from __future__ import annotations

import asyncio
import json
import inspect
import threading
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from agentscope.message import TextBlock
from agentscope.agent import ReActAgent
from agentscope.message import Msg
from agentscope.tool import ToolResponse
from unittest.mock import AsyncMock

from swe.agents.tool_output_budget_mixin import ToolOutputBudgetMixin
from swe.agents.tool_guard_mixin import ToolGuardMixin
from swe.agents.react_agent import SWEAgent
from swe.app.channels.console.channel import ConsoleChannel
from swe.app.runner.sse_replay import ReplayStream
from swe.app.source_system_config.models import (
    EffectiveSourceSystemConfig,
    SourceSystemConfig,
)
from swe.app.source_system_config.runtime import bind_source_system_config
from swe.config.config import ToolResultCompactConfig


class _Memory:
    def __init__(self) -> None:
        self.messages = []

    async def add(self, msg) -> None:
        self.messages.append(msg)


@pytest.mark.asyncio
async def test_tool_artifact_write_runs_outside_event_loop(
    tmp_path,
    monkeypatch,
):
    from swe.agents.utils import tool_output_compaction

    observed_threads = []
    original = tool_output_compaction._persist_artifact

    def recording_write(*args):
        observed_threads.append(threading.get_ident())
        return original(*args)

    monkeypatch.setattr(
        tool_output_compaction,
        "_persist_artifact",
        recording_write,
    )
    agent = _AgentScopeLikeAgent(
        config=ToolResultCompactConfig(recent_max_bytes=1000),
        workspace_dir=tmp_path,
        chunks=[_chunk("x" * 4096)],
    )
    await agent._acting({"id": "tool-1", "name": "read_file", "input": {}})
    assert observed_threads
    assert threading.get_ident() not in observed_threads


class _Toolkit:
    def __init__(self, chunks: list[ToolResponse]) -> None:
        self._chunks = chunks

    async def call_tool_function(self, _tool_call):
        async def _stream():
            for chunk in self._chunks:
                yield chunk

        return _stream()


class _AgentScopeLikeAgent(ToolOutputBudgetMixin):
    """Minimal AgentScope boundary with a real toolkit response stream."""

    def __init__(
        self,
        *,
        config: ToolResultCompactConfig,
        workspace_dir: Path | None,
        chunks: list[ToolResponse],
    ) -> None:
        self._agent_config = SimpleNamespace(
            running=SimpleNamespace(tool_result_compact=config),
        )
        self._workspace_dir = workspace_dir
        self.toolkit = _Toolkit(chunks)
        self.memory = _Memory()
        self.printed = []
        self.finish_function_name = "finish"

    async def print(self, msg, is_last) -> None:
        self.printed.append((msg, is_last))


def _chunk(
    text: str,
    *,
    metadata: dict | None = None,
    is_interrupted: bool = False,
) -> ToolResponse:
    return ToolResponse(
        content=[TextBlock(type="text", text=text)],
        metadata=metadata,
        is_interrupted=is_interrupted,
    )


def _source_config(raw_config: dict) -> EffectiveSourceSystemConfig:
    source_config = SourceSystemConfig.model_validate(raw_config)
    return EffectiveSourceSystemConfig(
        source_id="portal",
        config=source_config.merged_with_defaults(),
        raw_config=source_config,
        version=1,
    )


class _SelectedExpertAgent(ToolGuardMixin, _AgentScopeLikeAgent):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._request_context = {
            "selected_expert_execution": True,
            "selected_expert_run_id": "expert-run-1",
        }
        self._tool_guard_forced_replay_active = True
        self.memory.content = self.memory.messages

    def _resolve_mcp_server(self, _tool_name):
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize("max_iters", [1, 2])
@pytest.mark.parametrize("status", ["completed", "partial"])
@pytest.mark.parametrize("model_outcome", ["reply", "error", "cancel"])
async def test_tool_free_summary_receives_complete_selected_expert_evidence(
    tmp_path,
    monkeypatch,
    max_iters,
    status,
    model_outcome,
):
    conclusion = "MIDDLE_FINDING: rotate the compromised credential"
    payload = {
        "run_id": "expert-run-1",
        "status": status,
        "result": {"summary": "x" * 600000 + conclusion + "y" * 600000},
    }
    prompts = []

    async def model(prompt):
        prompts.append(deepcopy(prompt))
        if model_outcome == "error":
            raise RuntimeError("summary rejected")
        if model_outcome == "cancel":
            raise asyncio.CancelledError()
        text = json.dumps([msg.content for msg in prompt])
        answer = (
            conclusion if conclusion in text else "expert evidence missing"
        )
        return SimpleNamespace(id="summary", content=answer)

    class Agent(SWEAgent):
        def __init__(self):
            ReActAgent.__init__(
                self,
                name="Main",
                sys_prompt="Summarize expert findings",
                model=model,
                formatter=SimpleNamespace(
                    format=AsyncMock(side_effect=lambda msgs: msgs),
                ),
                max_iters=max_iters,
                enable_rewrite_query=False,
            )
            self._request_context = {
                "selected_expert_execution": True,
                "forced_tool_call_json": json.dumps(
                    {
                        "id": "start-1",
                        "name": "start_subagent",
                        "input": {},
                    },
                ),
            }
            self._workspace_dir = tmp_path
            self._agent_config = SimpleNamespace(
                running=SimpleNamespace(
                    tool_result_compact=ToolResultCompactConfig(
                        recent_max_bytes=1000,
                    ),
                ),
            )
            self._init_agent_phase_state()
            self.printed = []

        async def print(self, msg, last=True, **kwargs):
            self.printed.append(deepcopy(msg))

        async def _reasoning(self, tool_choice=None):
            return await ToolGuardMixin._reasoning(self, tool_choice)

        async def _acting(self, tool_call):
            call = tool_call
            await self._run_tool_call_with_hard_timeout_impl(
                call,
                call["name"],
                call["input"],
            )
            self._complete_forced_tool_replay(
                call,
                call["name"],
                call["input"],
            )

    agent = Agent()

    async def start_subagent():
        return _chunk(json.dumps({"accepted": True, "run_id": "expert-run-1"}))

    async def wait_selected_expert():
        return _chunk(json.dumps(payload))

    agent.toolkit.register_tool_function(start_subagent)
    agent.toolkit.register_tool_function(wait_selected_expert)
    monkeypatch.setattr(
        "swe.agents.react_agent.get_active_model_supports_multimodal",
        lambda: True,
    )
    reply = inspect.unwrap(ReActAgent.reply)(
        agent,
        Msg("user", "inspect", "user"),
    )
    if model_outcome == "reply":
        answer = await reply
        assert conclusion in answer.get_text_content()
    else:
        error = (
            RuntimeError
            if model_outcome == "error"
            else asyncio.CancelledError
        )
        with pytest.raises(error):
            await reply
    assert len(prompts) == 1
    assert payload["result"]["summary"] in json.dumps(
        [msg.content for msg in prompts[0]],
    )
    assert agent._request_context["selected_expert_execution"] is False
    assert agent._selected_expert_summary_evidence is None
    memories = await agent.memory.get_memory()
    assert payload["result"]["summary"] not in json.dumps(
        [msg.content for msg in memories],
    )
    assert not any(
        "selected_expert_summary_evidence" in marks
        for _msg, marks in agent.memory.content
    )
    for msg in agent.printed:
        for block in msg.get_content_blocks("tool_result"):
            if block["name"] == "wait_selected_expert":
                preview = block["output"][0]["text"]
                assert len(preview.encode()) <= 1000
                assert conclusion not in preview


@pytest.mark.asyncio
@pytest.mark.parametrize("recent_max_bytes", [1000, 50000])
@pytest.mark.parametrize("status", ["completed", "partial"])
async def test_selected_expert_terminal_payload_survives_output_budget(
    tmp_path,
    recent_max_bytes,
    status,
):
    payload = {
        "run_id": "expert-run-1",
        "status": status,
        "result": {"summary": "expert result " * 5000},
    }
    agent = _SelectedExpertAgent(
        config=ToolResultCompactConfig(recent_max_bytes=recent_max_bytes),
        workspace_dir=tmp_path,
        chunks=[_chunk(json.dumps(payload))],
    )
    call = {"id": "wait-1", "name": "wait_selected_expert", "input": {}}
    await agent._run_tool_call_with_hard_timeout_impl(
        call,
        call["name"],
        call["input"],
    )
    replay = {"tool_call_id": call["id"], "tool_name": call["name"]}
    assert agent._selected_expert_tool_response(replay) == payload
    assert await agent._selected_expert_follow_up(replay) is None
    assert agent._request_context["selected_expert_execution"] is False
    assert not agent._request_context.get("selected_expert_execution_error")
    assert agent._selected_expert_control_response is None
    output = agent.printed[-1][0].content[0]["output"][0]["text"]
    assert len(output.encode()) <= recent_max_bytes
    assert "<<<TRUNCATED>>>" in output
    artifacts = list((tmp_path / "tool_result").glob("*.txt"))
    assert len(artifacts) == 1
    assert json.loads(artifacts[0].read_text()) == payload
    assert agent.memory.messages[-1] is agent.printed[-1][0]


@pytest.mark.asyncio
async def test_selected_expert_display_stays_below_replay_frame_limit(
    tmp_path,
):
    payload = {
        "run_id": "expert-run-1",
        "status": "completed",
        "result": {"summary": "expert result " * 100000},
    }
    agent = _SelectedExpertAgent(
        config=ToolResultCompactConfig(recent_max_bytes=50000),
        workspace_dir=tmp_path,
        chunks=[_chunk(json.dumps(payload))],
    )
    call = {
        "id": "wait-oversized",
        "name": "wait_selected_expert",
        "input": {},
    }

    await agent._run_tool_call_with_hard_timeout_impl(
        call,
        call["name"],
        call["input"],
    )

    output = agent.printed[-1][0].content[0]["output"][0]["text"]
    assert len(output.encode()) <= 50000
    assert "<<<TRUNCATED>>>" in output
    replay = {"tool_call_id": call["id"], "tool_name": call["name"]}
    assert agent._selected_expert_tool_response(replay) == payload

    def event(content):
        return SimpleNamespace(
            object="message",
            status=None,
            type="message",
            model_dump_json=lambda: json.dumps(
                {"object": "message", "content": content},
            ),
        )

    async def process(_request):
        yield event(agent.printed[-1][0].content)
        yield event("final expert answer")

    channel = ConsoleChannel(process=process, enabled=True, bot_prefix="SWE")
    request = SimpleNamespace(input=None, channel_meta={})
    events = [item async for item in channel.stream_one(request)]
    stream = ReplayStream()
    subscriber = stream.subscribe()
    try:
        for item in events:
            await stream.append(item)
        assert stream.error is None
        assert stream.committed == 2
        assert await subscriber.get() == events[0]
        assert "final expert answer" in await subscriber.get()
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_selected_expert_control_cache_is_bound_to_current_call(
    tmp_path,
):
    payload = {"run_id": "expert-run-1", "status": "completed"}
    agent = _SelectedExpertAgent(
        config=ToolResultCompactConfig(recent_max_bytes=1000),
        workspace_dir=tmp_path,
        chunks=[_chunk(json.dumps(payload))],
    )
    call = {"id": "wait-1", "name": "wait_selected_expert", "input": {}}
    await agent._run_tool_call_with_hard_timeout_impl(call, call["name"], {})
    assert (
        agent._selected_expert_tool_response(
            {"tool_call_id": "different-call", "tool_name": call["name"]},
        )
        == {}
    )
    agent.toolkit = _Toolkit([])
    call["id"] = "wait-2"
    await agent._run_tool_call_with_hard_timeout_impl(call, call["name"], {})
    assert (
        agent._selected_expert_tool_response(
            {"tool_call_id": call["id"], "tool_name": call["name"]},
        )
        == {}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("run_id", "status"),
    [("other-run", "completed"), ("expert-run-1", "running")],
)
async def test_unconfirmed_selected_expert_has_no_summary_evidence(
    tmp_path,
    run_id,
    status,
):
    agent = _SelectedExpertAgent(
        config=ToolResultCompactConfig(recent_max_bytes=1000),
        workspace_dir=tmp_path,
        chunks=[
            _chunk(
                json.dumps(
                    {
                        "run_id": run_id,
                        "status": status,
                        "result": {
                            "summary": "do not summarize this evidence",
                        },
                    },
                ),
            ),
        ],
    )
    call = {"id": "wait-1", "name": "wait_selected_expert", "input": {}}
    await agent._run_tool_call_with_hard_timeout_impl(call, call["name"], {})
    await agent._selected_expert_follow_up(
        {
            "tool_call_id": call["id"],
            "tool_name": call["name"],
        },
    )
    assert agent._selected_expert_summary_evidence is None
    assert agent._request_context["selected_expert_execution_error"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("forced_replay", "selected_execution"),
    [(False, True), (True, False), (False, False)],
)
async def test_unforced_selected_expert_wait_keeps_output_budget(
    tmp_path,
    forced_replay,
    selected_execution,
):
    agent = _SelectedExpertAgent(
        config=ToolResultCompactConfig(recent_max_bytes=1000),
        workspace_dir=tmp_path,
        chunks=[_chunk("x" * 60000)],
    )
    agent._tool_guard_forced_replay_active = forced_replay
    agent._request_context["selected_expert_execution"] = selected_execution
    call = {"id": "wait-1", "name": "wait_selected_expert", "input": {}}
    await agent._run_tool_call_with_hard_timeout_impl(call, call["name"], {})
    output = agent.memory.messages[-1].content[0]["output"][0]["text"]
    assert len(output.encode()) <= 1000
    assert "<<<TRUNCATED>>>" in output
    assert getattr(agent, "_selected_expert_control_response", None) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_shell_spool_context_wraps_tool_creation_and_iteration(
    tmp_path,
    enabled,
):
    from swe.agents.tools.shell_output_spool import create_shell_output_spool
    from swe.agents.tools.shell import smart_decode, _format_shell_response

    observed = []

    def capture():
        spool = create_shell_output_spool(smart_decode, _format_shell_response)
        observed.append(
            None if spool is None else (spool.workspace, spool.max_bytes),
        )

    class Toolkit:
        async def call_tool_function(self, _call):
            capture()

            async def stream():
                capture()
                yield _chunk("hello")

            return stream()

    agent = _AgentScopeLikeAgent(
        config=ToolResultCompactConfig(enabled=enabled, recent_max_bytes=1000),
        workspace_dir=tmp_path,
        chunks=[],
    )
    agent.toolkit = Toolkit()
    await agent._acting(
        {"id": "tool-1", "name": "execute_shell_command", "input": {}},
    )
    assert observed == (
        [(tmp_path.resolve(), 1000)] * 2 if enabled else [None, None]
    )
    assert (
        create_shell_output_spool(smart_decode, _format_shell_response) is None
    )


@pytest.mark.asyncio
async def test_real_shell_toolkit_reuses_canonical_spool_artifact(
    tmp_path,
    monkeypatch,
):
    import os
    import shlex
    import sys
    from contextlib import nullcontext
    from agentscope.tool import Toolkit
    from swe.agents.tools import shell

    monkeypatch.setattr(
        shell,
        "prepare_shell_command",
        lambda command, cwd: SimpleNamespace(
            command=command,
            working_dir=tmp_path,
            env=os.environ.copy(),
            python_runtime_guard=nullcontext(),
        ),
    )
    monkeypatch.setattr(
        shell,
        "resolve_current_process_limit_policy",
        lambda _: SimpleNamespace(
            build_preexec_fn=lambda: None,
            enabled=False,
            shell_max_concurrent=None,
            diagnostic=None,
            should_enforce=False,
            should_enforce_memory_limit=False,
        ),
    )
    agent = _AgentScopeLikeAgent(
        config=ToolResultCompactConfig(recent_max_bytes=1000),
        workspace_dir=tmp_path,
        chunks=[],
    )
    agent.toolkit = Toolkit()
    agent.toolkit.register_tool_function(shell.execute_shell_command)
    code = "import sys; print('x' * 20000); sys.stderr.write('warning\\n')"
    await agent._acting(
        {
            "id": "shell-1",
            "name": "execute_shell_command",
            "input": {
                "command": f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}",
            },
        },
    )
    artifacts = list((tmp_path / "tool_result").glob("*.txt"))
    assert len(artifacts) == 1
    assert artifacts[0].read_text() == "x" * 20000 + "\n[stderr]\nwarning"
    output = agent.memory.messages[0].content[0]["output"][0]["text"]
    assert len(output.encode()) <= 1000
    assert f"tool_result/{artifacts[0].name}" in output
    assert agent.printed[0][0] is agent.memory.messages[0]


@pytest.mark.asyncio
async def test_compacts_source_resolved_tool_result_before_print_and_memory(
    tmp_path: Path,
) -> None:
    agent = _AgentScopeLikeAgent(
        config=ToolResultCompactConfig(
            enabled=True,
            old_max_bytes=128,
            recent_max_bytes=1024,
            recent_n=1,
            retention_days=1,
        ),
        workspace_dir=tmp_path,
        chunks=[_chunk("x" * 4096)],
    )

    with bind_source_system_config(
        _source_config({"tool_result_compact": {"recent_max_bytes": 1000}}),
    ):
        result = await agent._acting(
            {"id": "tool-1", "name": "read_file", "input": {}},
        )

    assert result is None
    printed, is_last = agent.printed[0]
    stored = agent.memory.messages[0]
    assert is_last is True
    assert printed is stored
    output = stored.content[0]["output"][0]["text"]
    assert len(output.encode("utf-8")) <= 1000
    assert "<<<TRUNCATED>>>" in output
    artifacts = list((tmp_path / "tool_result").glob("*.txt"))
    assert len(artifacts) == 1
    assert artifacts[0].read_text(encoding="utf-8") == "x" * 4096


@pytest.mark.asyncio
async def test_compacts_with_fallback_workspace_when_workspace_is_none(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "swe.agents.tool_output_budget_mixin.WORKING_DIR",
        tmp_path,
    )
    agent = _AgentScopeLikeAgent(
        config=ToolResultCompactConfig(
            enabled=True,
            old_max_bytes=128,
            recent_max_bytes=1000,
            recent_n=1,
            retention_days=1,
        ),
        workspace_dir=None,
        chunks=[_chunk("x" * 4096)],
    )

    await agent._acting(
        {"id": "tool-1", "name": "read_file", "input": {}},
    )

    output = agent.memory.messages[0].content[0]["output"][0]["text"]
    assert len(output.encode("utf-8")) <= 1000
    assert "<<<TRUNCATED>>>" in output
    artifacts = list((tmp_path / "tool_result").glob("*.txt"))
    assert len(artifacts) == 1
    assert artifacts[0].read_text(encoding="utf-8") == "x" * 4096


@pytest.mark.asyncio
async def test_disabled_source_configuration_leaves_tool_output_unchanged(
    tmp_path: Path,
) -> None:
    original = "x" * 4096
    agent = _AgentScopeLikeAgent(
        config=ToolResultCompactConfig(
            enabled=True,
            old_max_bytes=1000,
            recent_max_bytes=1000,
            recent_n=1,
            retention_days=1,
        ),
        workspace_dir=tmp_path,
        chunks=[_chunk(original)],
    )

    with bind_source_system_config(
        _source_config({"tool_result_compact": {"enabled": False}}),
    ):
        await agent._acting(
            {"id": "tool-1", "name": "read_file", "input": {}},
        )

    stored = agent.memory.messages[0]
    assert agent.printed[0][0] is stored
    assert stored.content[0]["output"][0]["text"] == original
    assert not (tmp_path / "tool_result").exists()


@pytest.mark.asyncio
async def test_finish_returns_structured_output_after_printing_and_storing(
    tmp_path: Path,
) -> None:
    structured_output = {"answer": "done"}
    agent = _AgentScopeLikeAgent(
        config=ToolResultCompactConfig(enabled=False),
        workspace_dir=tmp_path,
        chunks=[
            _chunk(
                "finished",
                metadata={
                    "success": True,
                    "structured_output": structured_output,
                },
            ),
        ],
    )

    result = await agent._acting(
        {"id": "tool-1", "name": "finish", "input": {}},
    )

    assert result == structured_output
    assert len(agent.printed) == len(agent.memory.messages) == 1
    assert agent.printed[0][0] is agent.memory.messages[0]


@pytest.mark.asyncio
async def test_interrupted_chunk_is_printed_and_stored_before_cancellation(
    tmp_path: Path,
) -> None:
    agent = _AgentScopeLikeAgent(
        config=ToolResultCompactConfig(enabled=False),
        workspace_dir=tmp_path,
        chunks=[_chunk("interrupted", is_interrupted=True)],
    )

    with pytest.raises(asyncio.CancelledError):
        await agent._acting(
            {"id": "tool-1", "name": "read_file", "input": {}},
        )

    assert len(agent.printed) == len(agent.memory.messages) == 1
    assert agent.printed[0][0] is agent.memory.messages[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_chunk", [False, True])
@pytest.mark.parametrize("worker_state", ["queued", "running"])
async def test_cancellation_preserves_received_chunk_during_compaction(
    tmp_path,
    monkeypatch,
    previous_chunk,
    worker_state,
):
    from swe import output_workers
    from swe.agents.utils import tool_output_compaction as compaction

    received = _chunk("x" * 4096)
    chunks = [_chunk("previous"), received] if previous_chunk else [received]
    agent = _AgentScopeLikeAgent(
        config=ToolResultCompactConfig(recent_max_bytes=1000),
        workspace_dir=tmp_path,
        chunks=chunks,
    )
    entered = asyncio.Event()
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    slots = threading.BoundedSemaphore(1)
    original_work = compaction.run_output_work
    original_write = compaction._persist_artifact
    calls = 0

    async def record_work(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == len(chunks):
            if worker_state == "queued":
                # Keep capacity occupied until the request is cancelled.
                slots.acquire()  # pylint: disable=consider-using-with
                monkeypatch.setattr(output_workers, "_SLOTS", slots)
            entered.set()
        return await original_work(*args, **kwargs)

    def blocked_write(*args):
        started.set()
        try:
            assert release.wait(5)
            return original_write(*args)
        finally:
            finished.set()

    monkeypatch.setattr(compaction, "run_output_work", record_work)
    monkeypatch.setattr(compaction, "_persist_artifact", blocked_write)
    task = asyncio.create_task(
        agent._acting({"id": "tool-1", "name": "read_file", "input": {}}),
    )
    try:
        await asyncio.wait_for(entered.wait(), 5)
        if worker_state == "running":
            while not started.is_set():
                await asyncio.sleep(0.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(agent.memory.messages) == 1
        stored = agent.memory.messages[0]
        assert stored.content[0]["output"] == received.content
    finally:
        release.set()
        if worker_state == "queued" and entered.is_set():
            slots.release()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if started.is_set():
            while not finished.is_set():
                await asyncio.sleep(0.001)
    assert agent.memory.messages[0].content[0]["output"] == received.content
