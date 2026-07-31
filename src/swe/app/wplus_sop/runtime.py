# -*- coding: utf-8 -*-
"""Bridge W+ commands into the owning Chat's existing Agent runtime."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..channels.base import ContentType, TextContent
from .runtime_context import WPlusRuntimeContext, bind_wplus_runtime

WPLUS_SOP_SKILL_NAME = "wplus-sop-miner"
logger = logging.getLogger(__name__)

_SAFE_TRACE_ROLE_LABELS = frozenset(
    {"assistant", "user", "system", "developer", "tool"},
)
_SAFE_TRACE_MESSAGE_TYPE_LABELS = frozenset(
    {
        "message",
        "reasoning",
        "plugin_call",
        "plugin_call_output",
        "function_call",
        "function_call_output",
        "component_call",
        "component_call_output",
        "mcp_list_tools",
        "mcp_approval_request",
        "mcp_approval_response",
        "mcp_call",
        "mcp_call_output",
        "heartbeat",
        "error",
    },
)
_SAFE_TRACE_STATUS_LABELS = frozenset(
    {
        "created",
        "queued",
        "in_progress",
        "completed",
        "failed",
        "canceled",
        "cancelled",
        "incomplete",
        "rejected",
        "unknown",
    },
)
_SAFE_TRACE_CONTENT_TYPE_LABELS = frozenset(
    {"text", "data", "image", "audio", "video", "file", "refusal"},
)
_SAFE_TRACE_TOOL_SOURCE_LABELS = frozenset(
    {"stdout", "stderr", "message"},
)
_SAFE_TRACE_LINE_MAX_CHARS = 160

_STAGE_PROPOSAL_EXAMPLE = {
    "stages": [
        {
            "stage_id": "stage-1",
            "name": "确认需求范围",
            "description": "确认流程入口、对象范围与目标。",
            "status": "pending",
        },
        {
            "stage_id": "stage-2",
            "name": "验证交付结果",
            "description": "预跑已确认流程并核对输出。",
            "status": "pending",
        },
    ],
}


class WPlusChatRunBusyError(RuntimeError):
    """Raised when the owning Chat already has an unrelated active run."""


@dataclass(frozen=True)
class WPlusTurnStart:
    """Trusted identifiers for a newly claimed owning-Chat turn."""

    chat_id: str
    logical_chat_session_id: str
    message_id: str
    run_id: str
    attempt_id: str


@dataclass(frozen=True)
class WPlusSafeStreamTraceSnapshot:
    """Bounded, non-persisted safe frame summaries for one W+ Agent run."""

    sequence: int
    summary_text: str
    truncated: bool


@dataclass
class _WPlusSafeStreamTraceRun:
    sequence: int = 0
    lines: deque[str] = field(default_factory=deque)
    char_count: int = 0
    truncated: bool = False


class WPlusSafeStreamTraceRegistry:
    """Collect only bounded, allowlisted metadata about Agent stream frames."""

    def __init__(
        self,
        *,
        max_chars: int = 4_000,
        max_lines: int = 80,
        max_active_runs: int = 32,
    ):
        if max_chars < 1 or max_lines < 1 or max_active_runs < 1:
            raise ValueError("debug stream limits must be positive")
        self._max_chars = max_chars
        self._max_lines = max_lines
        self._max_active_runs = max_active_runs
        self._runs: OrderedDict[
            tuple[str, str],
            _WPlusSafeStreamTraceRun,
        ] = OrderedDict()

    def start_run(self, session_id: str, run_id: str) -> None:
        """Start one trace, discard this Session's old run, and cap entries."""
        for key in tuple(self._runs):
            if key[0] == session_id:
                del self._runs[key]
        self._runs[(session_id, run_id)] = _WPlusSafeStreamTraceRun()
        while len(self._runs) > self._max_active_runs:
            self._runs.popitem(last=False)

    def finish_run(self, session_id: str, run_id: str) -> None:
        """Remove a completed trace so process memory cannot accumulate."""
        self._runs.pop((session_id, run_id), None)

    def ingest(self, session_id: str, run_id: str, sse_chunk: str) -> None:
        """Replace raw frames with fixed-label, numeric-only trace lines."""
        run = self._runs.get((session_id, run_id))
        if run is None or not isinstance(sse_chunk, str):
            return
        for line in sse_chunk.splitlines():
            if not line.startswith("data:"):
                continue
            try:
                frame = json.loads(line.removeprefix("data:").strip())
            except (json.JSONDecodeError, TypeError):
                self._append_line(run, "frame object=unknown hidden=true")
                continue
            self._append_line(run, self._summarize_frame(frame))

    def snapshot(
        self,
        session_id: str,
        run_id: str,
    ) -> WPlusSafeStreamTraceSnapshot | None:
        run = self._runs.get((session_id, run_id))
        if run is None:
            return None
        return WPlusSafeStreamTraceSnapshot(
            sequence=run.sequence,
            summary_text="\n".join(run.lines),
            truncated=run.truncated,
        )

    def _summarize_frame(self, frame: Any) -> str:
        if not isinstance(frame, dict):
            return "frame object=unknown hidden=true"
        obj = frame.get("object")
        if obj == "response":
            return (
                "response status="
                f"{self._safe_label(frame.get('status'), _SAFE_TRACE_STATUS_LABELS)}"
            )
        if obj == "message":
            content_types, content_chars = self._content_summary(
                frame.get("content"),
            )
            return (
                "message "
                "role="
                f"{self._safe_label(frame.get('role'), _SAFE_TRACE_ROLE_LABELS)} "
                "type="
                f"{self._safe_label(frame.get('type'), _SAFE_TRACE_MESSAGE_TYPE_LABELS)} "
                "status="
                f"{self._safe_label(frame.get('status'), _SAFE_TRACE_STATUS_LABELS)} "
                f"content_types={content_types} "
                f"content_chars={content_chars} hidden=true"
            )
        if obj == "content":
            text = frame.get("text")
            chars = len(text) if isinstance(text, str) else 0
            return (
                "content "
                "type="
                f"{self._safe_label(frame.get('type'), _SAFE_TRACE_CONTENT_TYPE_LABELS)} "
                "status="
                f"{self._safe_label(frame.get('status'), _SAFE_TRACE_STATUS_LABELS)} "
                f"chars={chars} hidden=true"
            )
        if obj == "tool_output_frame":
            text = frame.get("text")
            chars = len(text) if isinstance(text, str) else 0
            return (
                "tool_output_frame "
                "source="
                f"{self._safe_label(frame.get('source'), _SAFE_TRACE_TOOL_SOURCE_LABELS)} "
                f"chars={chars} hidden=true"
            )
        return "frame object=unknown hidden=true"

    def _content_summary(self, content: Any) -> tuple[str, int]:
        if not isinstance(content, list):
            return "none", 0
        labels: list[str] = []
        chars = 0
        for item in content:
            if not isinstance(item, dict):
                label = "unknown"
            else:
                label = self._safe_label(
                    item.get("type"),
                    _SAFE_TRACE_CONTENT_TYPE_LABELS,
                )
                text = item.get("text")
                if isinstance(text, str):
                    chars += len(text)
            if label not in labels:
                labels.append(label)
        return "+".join(labels) if labels else "none", chars

    @staticmethod
    def _safe_label(value: Any, allowed: frozenset[str]) -> str:
        if isinstance(value, str) and value in allowed:
            return value
        return "unknown"

    def _append_line(self, run: _WPlusSafeStreamTraceRun, line: str) -> None:
        line = line[:_SAFE_TRACE_LINE_MAX_CHARS]
        if len(line) > self._max_chars:
            line = line[: self._max_chars]
            run.truncated = True
        separator_chars = 1 if run.lines else 0
        while run.lines and (
            len(run.lines) >= self._max_lines
            or run.char_count + separator_chars + len(line) > self._max_chars
        ):
            removed = run.lines.popleft()
            run.char_count -= len(removed)
            if run.lines:
                run.char_count -= 1
            run.truncated = True
            separator_chars = 1 if run.lines else 0
        run.lines.append(line)
        run.char_count += separator_chars + len(line)
        run.sequence += 1


def get_wplus_safe_stream_trace_registry(
    workspace: Any,
) -> WPlusSafeStreamTraceRegistry:
    """Return the process-local safe trace registry scoped to one workspace."""
    attribute = "_wplus_sop_safe_stream_trace_registry"
    registry = getattr(workspace, attribute, None)
    if registry is None:
        registry = WPlusSafeStreamTraceRegistry()
        setattr(workspace, attribute, registry)
    return registry


def build_wplus_command_text(
    *,
    command: str,
    sop_session_id: str,
    run_id: str,
    attempt_id: str,
    payload: dict[str, Any],
) -> str:
    """Build a deterministic instruction without putting ownership in user data."""
    body = {
        "protocol": "wplus-sop-command-v1",
        "command": command,
        "sop_session_id": sop_session_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "payload": payload,
    }
    command_contract = ""
    requires_stage_proposal = command == "propose_stage_queue" or (
        command == "retry_current_turn"
        and payload.get("target_state") == "GeneratingStageProposal"
    )
    if requires_stage_proposal:
        command_contract = (
            "\n本回合只调用一次 emit_wplus_sop_event，不得调用其他 W+ SOP "
            "事件。调用参数必须满足 kind='stage_proposal'、"
            "event_key='stage-proposal-v1'，payload 必须是按下方 schema "
            "新生成的候选环节对象，不得把命令输入中的 payload 原样提交。"
            "不得只输出 Markdown；Markdown "
            "只能作为工具提交成功后的可读摘要。payload 顶层只能包含 stages "
            "数组，每个环节必须且只能包含 stage_id、name、description、"
            "status；status 使用 pending。\n"
            "stage_proposal payload 示例：\n"
            + json.dumps(
                _STAGE_PROPOSAL_EXAMPLE,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    return (
        "执行下面由 CoPaw W+ SOP 工作台提交的结构化命令。"
        "严格遵守 wplus-sop-miner，并在每个业务边界调用 "
        "emit_wplus_sop_event；不要从 Markdown 生成交互状态。\n"
        + json.dumps(body, ensure_ascii=False, sort_keys=True)
        + command_contract
    )


async def start_wplus_chat_turn(
    *,
    workspace: Any,
    chat: Any,
    user_id: str,
    source_id: str,
    sop_session_id: str,
    command: str,
    payload: dict[str, Any],
    run_id: str,
    attempt_id: str,
    on_complete: Callable[[], Awaitable[None]] | None = None,
    before_start: Callable[[], None] | None = None,
) -> WPlusTurnStart:
    """Start one background Agent turn on the persisted owning Chat."""
    console_channel = await workspace.channel_manager.get_channel("console")
    if console_channel is None:
        raise RuntimeError("Console channel is unavailable")

    message_id = str(uuid.uuid4())
    native_payload = {
        "channel_id": "console",
        "sender_id": user_id,
        "content_parts": [
            TextContent(
                type=ContentType.TEXT,
                text=build_wplus_command_text(
                    command=command,
                    sop_session_id=sop_session_id,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    payload=payload,
                ),
            ),
        ],
        "meta": {
            "session_id": chat.session_id,
            "user_id": user_id,
            "source_id": source_id,
            "msgid": message_id,
            "selected_skill_names": [WPLUS_SOP_SKILL_NAME],
            "wplus_sop_session_id": sop_session_id,
            "wplus_sop_run_id": run_id,
            "wplus_sop_attempt_id": attempt_id,
            "wplus_sop_command": command,
        },
    }

    trusted_runtime = WPlusRuntimeContext(
        sop_session_id=sop_session_id,
        run_id=run_id,
        attempt_id=attempt_id,
        command=command,
    )
    with bind_wplus_runtime(trusted_runtime):
        queue, is_new_run = await workspace.task_tracker.attach_or_start(
            chat.id,
            native_payload,
            console_channel.stream_one,
            before_start=before_start,
        )
    if not is_new_run:
        await workspace.task_tracker.detach_subscriber(chat.id, queue)
        raise WPlusChatRunBusyError(
            "The owning Chat already has an active Agent run",
        )

    if on_complete is None:
        await workspace.task_tracker.detach_subscriber(chat.id, queue)
    else:
        safe_traces = get_wplus_safe_stream_trace_registry(workspace)
        safe_traces.start_run(sop_session_id, run_id)

        async def _watch_completion() -> None:
            try:
                async for chunk in workspace.task_tracker.stream_from_queue(
                    queue,
                    chat.id,
                ):
                    safe_traces.ingest(sop_session_id, run_id, chunk)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "W+ Agent stream watcher failed for run %s",
                    run_id,
                )
            finally:
                try:
                    await on_complete()
                finally:
                    safe_traces.finish_run(sop_session_id, run_id)

        asyncio.create_task(_watch_completion())

    return WPlusTurnStart(
        chat_id=chat.id,
        logical_chat_session_id=chat.session_id,
        message_id=message_id,
        run_id=run_id,
        attempt_id=attempt_id,
    )
