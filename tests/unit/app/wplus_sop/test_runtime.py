import asyncio
import json
from types import SimpleNamespace

import pytest

from swe.app.wplus_sop.models import StageProposalPayload
from swe.app.wplus_sop.runtime import (
    WPlusChatRunBusyError,
    WPlusSafeStreamTraceRegistry,
    build_wplus_command_text,
    get_wplus_safe_stream_trace_registry,
    start_wplus_chat_turn,
)
from swe.app.wplus_sop.runtime_context import get_current_wplus_runtime


class FakeTracker:
    def __init__(self, *, is_new=True):
        self.is_new = is_new
        self.call = None
        self.detached = None

    async def attach_or_start(
        self,
        chat_id,
        payload,
        stream_fn,
        *,
        before_start=None,
    ):
        if before_start is not None:
            before_start()
        self.call = (
            chat_id,
            payload,
            stream_fn,
            get_current_wplus_runtime(),
        )
        return object(), self.is_new

    async def detach_subscriber(self, chat_id, queue):
        self.detached = (chat_id, queue)


class FakeChannelManager:
    def __init__(self, channel):
        self.channel = channel

    async def get_channel(self, name):
        assert name == "console"
        return self.channel


def _sse(payload):
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def test_safe_stream_trace_summarizes_frames_without_storing_text_bodies():
    registry = WPlusSafeStreamTraceRegistry(max_chars=1_000, max_lines=20)
    registry.start_run("sop-1", "run-1")

    frames = [
        {
            "object": "response",
            "status": "in_progress",
        },
        {
            "object": "message",
            "id": "msg-safe",
            "type": "message",
            "role": "assistant",
            "status": "in_progress",
            "content": None,
        },
        {
            "object": "content",
            "msg_id": "msg-safe",
            "type": "text",
            "delta": True,
            "status": "in_progress",
            "text": "account=6222020202020202 password=hunter2",
        },
        {
            "object": "tool_output_frame",
            "source": "stdout",
            "text": "balance=999999 token=sk-secret",
        },
    ]

    for frame in frames:
        registry.ingest("sop-1", "run-1", _sse(frame))

    snapshot = registry.snapshot("sop-1", "run-1")
    assert snapshot is not None
    assert snapshot.summary_text.splitlines() == [
        "response status=in_progress",
        (
            "message role=assistant type=message status=in_progress "
            "content_types=none content_chars=0 hidden=true"
        ),
        "content type=text status=in_progress chars=41 hidden=true",
        "tool_output_frame source=stdout chars=30 hidden=true",
    ]
    for sentinel in (
        "6222020202020202",
        "hunter2",
        "999999",
        "sk-secret",
    ):
        assert sentinel not in snapshot.summary_text
    assert snapshot.truncated is False


def test_safe_stream_trace_maps_untrusted_labels_to_fixed_whitelists():
    registry = WPlusSafeStreamTraceRegistry(max_chars=1_000, max_lines=20)
    registry.start_run("sop-1", "run-1")

    frames = [
        {
            "object": "message",
            "id": "msg-reasoning",
            "type": "reasoning",
            "role": "assistant",
            "status": "canceled",
            "content": None,
        },
        {
            "object": "message",
            "id": "msg-tool",
            "type": "function_call",
            "role": "assistant",
            "status": "failed",
            "content": None,
        },
        {
            "object": "message",
            "id": "msg-mcp",
            "type": "mcp_call",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "data", "data": {"secret": "MCP_SENTINEL"}}],
        },
        {
            "object": "tool_output_frame",
            "source": "tenant/acme?credential=SOURCE_SENTINEL",
            "text": "TOOL_SENTINEL",
        },
        {
            "object": "message",
            "id": "msg-unknown",
            "type": "PII_TYPE_SENTINEL",
            "role": "ROLE_SENTINEL",
            "status": "STATUS_SENTINEL",
            "content": [{"type": "PII_CONTENT_SENTINEL", "text": "BODY_SENTINEL"}],
        },
        {"object": "OBJECT_SENTINEL", "payload": "UNKNOWN_SENTINEL"},
    ]

    for frame in frames:
        registry.ingest("sop-1", "run-1", _sse(frame))
    registry.ingest("sop-1", "run-1", "data: not-json\n\n")

    snapshot = registry.snapshot("sop-1", "run-1")
    assert snapshot is not None
    assert snapshot.summary_text.splitlines() == [
        (
            "message role=assistant type=reasoning status=canceled "
            "content_types=none content_chars=0 hidden=true"
        ),
        (
            "message role=assistant type=function_call status=failed "
            "content_types=none content_chars=0 hidden=true"
        ),
        (
            "message role=assistant type=mcp_call status=completed "
            "content_types=data content_chars=0 hidden=true"
        ),
        "tool_output_frame source=unknown chars=13 hidden=true",
        (
            "message role=unknown type=unknown status=unknown "
            "content_types=unknown content_chars=13 hidden=true"
        ),
        "frame object=unknown hidden=true",
        "frame object=unknown hidden=true",
    ]
    for sentinel in (
        "SENTINEL",
        "private reasoning",
        "tool arguments",
        "raw customer data",
    ):
        assert sentinel not in snapshot.summary_text


def test_safe_stream_trace_has_fixed_capacity_and_evicts_old_runs():
    registry = WPlusSafeStreamTraceRegistry(
        max_chars=130,
        max_lines=2,
        max_active_runs=2,
    )
    registry.start_run("sop-1", "run-1")
    for index in range(4):
        registry.ingest(
            "sop-1",
            "run-1",
            _sse(
                {
                    "object": "content",
                    "type": "text",
                    "status": "in_progress",
                    "text": f"BODY_SENTINEL_{index}" * 100,
                },
            ),
        )

    first = registry.snapshot("sop-1", "run-1")
    assert first is not None
    assert len(first.summary_text) <= 130
    assert len(first.summary_text.splitlines()) <= 2
    assert all(len(line) <= 160 for line in first.summary_text.splitlines())
    assert "BODY_SENTINEL" not in first.summary_text
    assert first.truncated is True

    registry.start_run("sop-2", "run-2")
    registry.start_run("sop-3", "run-3")

    assert registry.snapshot("sop-1", "run-1") is None
    assert registry.snapshot("sop-2", "run-2") is not None
    assert registry.snapshot("sop-3", "run-3") is not None

    registry.start_run("sop-2", "run-4")
    assert registry.snapshot("sop-2", "run-2") is None
    assert registry.snapshot("sop-2", "run-4") is not None

    registry.finish_run("sop-2", "run-4")
    assert registry.snapshot("sop-2", "run-4") is None


def test_safe_stream_trace_sequence_increases_for_each_safe_summary():
    registry = WPlusSafeStreamTraceRegistry(max_chars=1_000, max_lines=20)
    registry.start_run("sop-1", "run-1")
    registry.ingest(
        "sop-1",
        "run-1",
        _sse(
            {
                "object": "message",
                "id": "msg-1",
                "type": "message",
                "role": "assistant",
                "status": "in_progress",
                "content": None,
            },
        ),
    )
    first = registry.snapshot("sop-1", "run-1")
    assert first is not None
    assert first.sequence == 1

    registry.ingest(
        "sop-1",
        "run-1",
        _sse(
            {
                "object": "content",
                "type": "text",
                "status": "completed",
                "text": "BODY_SENTINEL",
            },
        ),
    )
    second = registry.snapshot("sop-1", "run-1")
    assert second is not None
    assert second.sequence == 2
    assert "BODY_SENTINEL" not in second.summary_text


def test_command_text_contains_machine_readable_command():
    text = build_wplus_command_text(
        command="confirm_stage_queue",
        sop_session_id="sop-1",
        run_id="run-1",
        attempt_id="attempt-1",
        payload={"stages": [{"stage_id": "stage-1", "title": "筛选"}]},
    )

    body = json.loads(text.splitlines()[-1])
    assert body["command"] == "confirm_stage_queue"
    assert body["payload"]["stages"][0]["stage_id"] == "stage-1"
    assert "emit_wplus_sop_event" in text


def test_stage_proposal_command_requires_one_schema_valid_event():
    text = build_wplus_command_text(
        command="propose_stage_queue",
        sop_session_id="sop-1",
        run_id="run-1",
        attempt_id="attempt-1",
        payload={"original_request": "梳理客户筛选流程"},
    )

    assert "只调用一次 emit_wplus_sop_event" in text
    assert "kind='stage_proposal'" in text
    assert "不得把命令输入中的 payload 原样提交" in text
    assert "不得只输出 Markdown" in text
    example_marker = "stage_proposal payload 示例：\n"
    example = json.loads(text.split(example_marker, maxsplit=1)[1].splitlines()[0])
    validated = StageProposalPayload.model_validate(example)

    assert len(validated.stages) == 2
    assert set(example) == {"stages"}
    assert all(
        set(stage) == {
            "stage_id",
            "name",
            "description",
            "status",
        }
        for stage in example["stages"]
    )


def test_retrying_stage_proposal_keeps_the_exact_event_contract():
    text = build_wplus_command_text(
        command="retry_current_turn",
        sop_session_id="sop-1",
        run_id="run-2",
        attempt_id="attempt-2",
        payload={
            "target_state": "GeneratingStageProposal",
            "retry_of_run_id": "run-1",
        },
    )

    assert "只调用一次 emit_wplus_sop_event" in text
    assert "kind='stage_proposal'" in text
    assert "stage_proposal payload 示例：" in text


@pytest.mark.asyncio
async def test_starts_one_turn_on_owning_chat_and_detaches_internal_queue():
    channel = SimpleNamespace(stream_one=object())
    tracker = FakeTracker()
    workspace = SimpleNamespace(
        channel_manager=FakeChannelManager(channel),
        task_tracker=tracker,
    )
    chat = SimpleNamespace(id="chat-1", session_id="logical-1")
    before_start_calls = 0

    def before_start():
        nonlocal before_start_calls
        before_start_calls += 1

    result = await start_wplus_chat_turn(
        workspace=workspace,
        chat=chat,
        user_id="user-1",
        source_id="console",
        sop_session_id="sop-1",
        command="submit_answers",
        payload={"answers": []},
        run_id="run-1",
        attempt_id="attempt-1",
        before_start=before_start,
    )

    chat_id, native_payload, stream_fn, trusted_runtime = tracker.call
    assert chat_id == "chat-1"
    assert stream_fn is channel.stream_one
    assert native_payload["meta"]["session_id"] == "logical-1"
    assert native_payload["meta"]["selected_skill_names"] == [
        "wplus-sop-miner",
    ]
    assert native_payload["meta"]["wplus_sop_session_id"] == "sop-1"
    assert trusted_runtime.run_id == "run-1"
    assert tracker.detached[0] == "chat-1"
    assert before_start_calls == 1
    assert result.run_id == "run-1"


@pytest.mark.asyncio
async def test_running_turn_feeds_process_local_safe_trace_and_cleans_up():
    stream_ready = asyncio.Event()
    release_stream = asyncio.Event()
    completed = asyncio.Event()

    class StreamingTracker(FakeTracker):
        async def stream_from_queue(self, _queue, _chat_id):
            yield _sse(
                {
                    "object": "message",
                    "id": "msg-1",
                    "type": "message",
                    "role": "assistant",
                    "content": None,
                },
            )
            yield _sse(
                {
                    "object": "content",
                    "msg_id": "msg-1",
                    "type": "text",
                    "delta": True,
                    "status": "in_progress",
                    "text": "ACCOUNT_SENTINEL",
                },
            )
            stream_ready.set()
            await release_stream.wait()

    async def on_complete():
        completed.set()

    channel = SimpleNamespace(stream_one=object())
    workspace = SimpleNamespace(
        channel_manager=FakeChannelManager(channel),
        task_tracker=StreamingTracker(),
    )

    await start_wplus_chat_turn(
        workspace=workspace,
        chat=SimpleNamespace(id="chat-1", session_id="logical-1"),
        user_id="user-1",
        source_id="console",
        sop_session_id="sop-1",
        command="submit_answers",
        payload={},
        run_id="run-1",
        attempt_id="attempt-1",
        on_complete=on_complete,
    )

    await asyncio.wait_for(stream_ready.wait(), timeout=1)
    snapshot = get_wplus_safe_stream_trace_registry(workspace).snapshot(
        "sop-1",
        "run-1",
    )
    assert snapshot is not None
    assert "content type=text status=in_progress chars=16 hidden=true" in (
        snapshot.summary_text
    )
    assert "ACCOUNT_SENTINEL" not in snapshot.summary_text

    release_stream.set()
    await asyncio.wait_for(completed.wait(), timeout=1)
    await asyncio.sleep(0)
    assert (
        get_wplus_safe_stream_trace_registry(workspace).snapshot(
            "sop-1",
            "run-1",
        )
        is None
    )


@pytest.mark.asyncio
async def test_failed_stream_calls_on_complete_then_cleans_up():
    completed = asyncio.Event()

    class FailingTracker(FakeTracker):
        async def stream_from_queue(self, _queue, _chat_id):
            yield _sse(
                {
                    "object": "tool_output_frame",
                    "source": "stderr",
                    "text": "TOOL_SECRET",
                },
            )
            raise RuntimeError("stream failed")

    async def on_complete():
        registry = get_wplus_safe_stream_trace_registry(workspace)
        snapshot = registry.snapshot("sop-1", "run-1")
        assert snapshot is not None
        assert "TOOL_SECRET" not in snapshot.summary_text
        completed.set()

    workspace = SimpleNamespace(
        channel_manager=FakeChannelManager(
            SimpleNamespace(stream_one=object()),
        ),
        task_tracker=FailingTracker(),
    )

    await start_wplus_chat_turn(
        workspace=workspace,
        chat=SimpleNamespace(id="chat-1", session_id="logical-1"),
        user_id="user-1",
        source_id="console",
        sop_session_id="sop-1",
        command="submit_answers",
        payload={},
        run_id="run-1",
        attempt_id="attempt-1",
        on_complete=on_complete,
    )

    await asyncio.wait_for(completed.wait(), timeout=1)
    await asyncio.sleep(0)
    assert (
        get_wplus_safe_stream_trace_registry(workspace).snapshot(
            "sop-1",
            "run-1",
        )
        is None
    )


@pytest.mark.asyncio
async def test_cancelled_stream_calls_on_complete_then_cleans_up(monkeypatch):
    stream_ready = asyncio.Event()
    never_release = asyncio.Event()
    completed = asyncio.Event()
    created_tasks: list[asyncio.Task[None]] = []
    original_create_task = asyncio.create_task

    class BlockingTracker(FakeTracker):
        async def stream_from_queue(self, _queue, _chat_id):
            yield _sse(
                {
                    "object": "content",
                    "type": "text",
                    "status": "in_progress",
                    "text": "CANCELLED_BODY_SENTINEL",
                },
            )
            stream_ready.set()
            await never_release.wait()

    def capture_task(coro):
        task = original_create_task(coro)
        created_tasks.append(task)
        return task

    async def on_complete():
        completed.set()

    monkeypatch.setattr(asyncio, "create_task", capture_task)
    workspace = SimpleNamespace(
        channel_manager=FakeChannelManager(
            SimpleNamespace(stream_one=object()),
        ),
        task_tracker=BlockingTracker(),
    )

    await start_wplus_chat_turn(
        workspace=workspace,
        chat=SimpleNamespace(id="chat-1", session_id="logical-1"),
        user_id="user-1",
        source_id="console",
        sop_session_id="sop-1",
        command="submit_answers",
        payload={},
        run_id="run-1",
        attempt_id="attempt-1",
        on_complete=on_complete,
    )

    await asyncio.wait_for(stream_ready.wait(), timeout=1)
    assert len(created_tasks) == 1
    created_tasks[0].cancel()
    with pytest.raises(asyncio.CancelledError):
        await created_tasks[0]

    assert completed.is_set()
    assert (
        get_wplus_safe_stream_trace_registry(workspace).snapshot(
            "sop-1",
            "run-1",
        )
        is None
    )


@pytest.mark.asyncio
async def test_refuses_to_attach_to_an_unrelated_existing_chat_run():
    channel = SimpleNamespace(stream_one=object())
    tracker = FakeTracker(is_new=False)
    workspace = SimpleNamespace(
        channel_manager=FakeChannelManager(channel),
        task_tracker=tracker,
    )

    with pytest.raises(WPlusChatRunBusyError):
        await start_wplus_chat_turn(
            workspace=workspace,
            chat=SimpleNamespace(id="chat-1", session_id="logical-1"),
            user_id="user-1",
            source_id="console",
            sop_session_id="sop-1",
            command="submit_answers",
            payload={},
            run_id="run-1",
            attempt_id="attempt-1",
        )

    assert tracker.detached[0] == "chat-1"
