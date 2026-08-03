# -*- coding: utf-8 -*-
"""Bridge W+ commands into the owning Chat's existing Agent runtime."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..channels.base import ContentType, TextContent
from .runtime_context import WPlusRuntimeContext, bind_wplus_runtime

WPLUS_SOP_SKILL_NAME = "wplus-sop-miner"
logger = logging.getLogger(__name__)

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

_QUESTION_BATCH_EXAMPLE = {
    "batch_id": "question-batch-stage-1-v1",
    "stage_id": "stage-1",
    "questions": [
        {
            "question_id": "confirm-scope",
            "prompt": "请确认当前环节的适用范围。",
            "type": "single_select",
            "required": True,
            "options": [
                {
                    "option_id": "confirmed",
                    "label": "范围正确",
                    "requires_custom_input": False,
                },
                {
                    "option_id": "custom",
                    "label": "需要调整",
                    "requires_custom_input": True,
                },
            ],
            "help_text": "选择“需要调整”时请补充具体范围。",
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
class _WPlusSafeTextPart:
    text: str
    delta: bool


@dataclass
class _WPlusSafeAssistantMessage:
    parts: list[_WPlusSafeTextPart] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(part.text for part in self.parts)


@dataclass
class _WPlusSafeStreamTraceRun:
    sequence: int = 0
    messages: OrderedDict[str, _WPlusSafeAssistantMessage] = field(
        default_factory=OrderedDict,
    )
    truncated: bool = False


class WPlusSafeStreamTraceRegistry:
    """Collect bounded plain text from ordinary assistant messages only."""

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
        """Apply allowlisted text frames with Chat Builder merge semantics."""
        run = self._runs.get((session_id, run_id))
        if run is None or not isinstance(sse_chunk, str):
            return
        for line in sse_chunk.splitlines():
            if not line.startswith("data:"):
                continue
            try:
                frame = json.loads(line.removeprefix("data:").strip())
            except (json.JSONDecodeError, TypeError):
                continue
            self._ingest_frame(run, frame)

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
            summary_text=self._render(run),
            truncated=run.truncated,
        )

    def _ingest_frame(
        self,
        run: _WPlusSafeStreamTraceRun,
        frame: Any,
    ) -> None:
        if not isinstance(frame, dict):
            return
        if frame.get("object") == "message":
            self._ingest_message(run, frame)
        elif frame.get("object") == "content":
            self._ingest_content(run, frame)

    def _ingest_message(
        self,
        run: _WPlusSafeStreamTraceRun,
        frame: dict[str, Any],
    ) -> None:
        if frame.get("role") != "assistant" or frame.get("type") != "message":
            return
        message_id = frame.get("id")
        if not isinstance(message_id, str) or not message_id:
            return
        message = run.messages.setdefault(
            message_id,
            _WPlusSafeAssistantMessage(),
        )
        content = frame.get("content")
        if isinstance(content, list) and content:
            parts = [
                _WPlusSafeTextPart(
                    text=item["text"],
                    delta=item.get("delta") is True,
                )
                for item in content
                if isinstance(item, dict)
                and item.get("type") == "text"
                and isinstance(item.get("text"), str)
            ]
            message.parts = parts
            if parts:
                run.sequence += 1
        self._enforce_limits(run)

    def _ingest_content(
        self,
        run: _WPlusSafeStreamTraceRun,
        frame: dict[str, Any],
    ) -> None:
        if frame.get("type") != "text" or not isinstance(
            frame.get("text"),
            str,
        ):
            return
        message_id = frame.get("msg_id")
        if not isinstance(message_id, str):
            return
        message = run.messages.get(message_id)
        if message is None:
            return
        text = frame["text"]
        is_delta = frame.get("delta") is True
        if is_delta:
            if message.parts and message.parts[-1].delta:
                message.parts[-1].text += text
            else:
                message.parts.append(
                    _WPlusSafeTextPart(text=text, delta=True),
                )
        elif message.parts:
            message.parts[-1] = _WPlusSafeTextPart(
                text=text,
                delta=False,
            )
        else:
            message.parts.append(
                _WPlusSafeTextPart(text=text, delta=False),
            )
        run.sequence += 1
        self._enforce_limits(run)

    @staticmethod
    def _render(run: _WPlusSafeStreamTraceRun) -> str:
        return "\n".join(
            text
            for message in run.messages.values()
            if (text := message.text)
        )

    def _enforce_limits(self, run: _WPlusSafeStreamTraceRun) -> None:
        while len(run.messages) > self._max_lines:
            _, removed = run.messages.popitem(last=False)
            if removed.text:
                run.truncated = True

        while len(self._render(run).splitlines()) > self._max_lines:
            if len(run.messages) > 1:
                run.messages.popitem(last=False)
            else:
                message = next(iter(run.messages.values()))
                lines = message.text.splitlines()
                message.parts = [
                    _WPlusSafeTextPart(
                        text="\n".join(lines[-self._max_lines :]),
                        delta=(message.parts[-1].delta if message.parts else False),
                    ),
                ]
            run.truncated = True

        while len(self._render(run)) > self._max_chars:
            if len(run.messages) > 1:
                run.messages.popitem(last=False)
            else:
                message = next(iter(run.messages.values()))
                message.parts = [
                    _WPlusSafeTextPart(
                        text=message.text[-self._max_chars :],
                        delta=(message.parts[-1].delta if message.parts else False),
                    ),
                ]
            run.truncated = True


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


def _build_trial_command_contract(
    *,
    run_id: str,
    attempt_id: str,
    requires_plan: bool,
) -> str:
    plan_step = (
        "1. 先提交 trial_plan，冻结本轮步骤与脱敏输出契约；\n"
        if requires_plan
        else "1. 这是执行态重试，沿用已持久化的预跑计划，不要重复提交 trial_plan；\n"
    )
    return (
        "\n本命令必须在同一个后台 Agent 回合内完成预跑闭环，不得在提交 "
        "trial_plan 后停止或等待另一个后台任务。按以下顺序执行：\n"
        + plan_step
        + "2. 提交 trial_execution_started；\n"
        "3. 业务执行只能直接执行 references 中已确认的 opencli 命令，"
        "不得调用其他业务工具，也不得让用户自行执行；\n"
        "4. 可提交 trial_execution_progress；\n"
        "5. OpenCLI 成功后提交且只提交一个 trial_execution_completed；"
        "失败、拒绝、超时或权限不足时提交且只提交一个 "
        "trial_execution_failed。终态事件成功持久化前不得结束本回合。\n"
        "所有预跑事件的 run_id 必须严格等于命令中的 run_id="
        + json.dumps(run_id, ensure_ascii=False)
        + "；trial_execution_started 的 attempt_id 必须严格等于命令中的 "
        "attempt_id="
        + json.dumps(attempt_id, ensure_ascii=False)
        + "。结果只保留脱敏摘要、计数、schema 校验、警告和失败位置；"
        "不得把原始客户响应、账户值或自由文本备注写入事件。"
    )


def build_wplus_command_text(
    *,
    command: str,
    sop_session_id: str,
    run_id: str,
    attempt_id: str,
    payload: dict[str, Any],
    target_state: str | None = None,
) -> str:
    """Build a deterministic instruction without putting ownership in user data."""
    effective_target_state = target_state
    if effective_target_state is None and command == "propose_stage_queue":
        effective_target_state = "GeneratingStageProposal"
    elif effective_target_state is None and command == "retry_current_turn":
        retry_target = payload.get("target_state")
        if isinstance(retry_target, str):
            effective_target_state = retry_target
    expected_event_kind = {
        "GeneratingStageProposal": "stage_proposal",
        "GeneratingQuestions": "question_batch",
    }.get(effective_target_state)
    is_trial_turn = effective_target_state in {
        "GeneratingTrial",
        "ExecutingTrial",
    }
    body = {
        "protocol": "wplus-sop-command-v1",
        "command": command,
        "sop_session_id": sop_session_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "payload": payload,
    }
    if effective_target_state is not None:
        body["target_state"] = effective_target_state
    if expected_event_kind is not None:
        body["expected_event_kind"] = expected_event_kind
    if is_trial_turn:
        body["expected_event_sequence"] = [
            *(
                ["trial_plan"]
                if effective_target_state == "GeneratingTrial"
                else []
            ),
            "trial_execution_started",
            "trial_execution_progress?",
            "trial_execution_completed|trial_execution_failed",
        ]
    command_contract = ""
    if expected_event_kind == "stage_proposal":
        command_contract = (
            "\n本回合只允许成功持久化一个业务边界事件。若 "
            "emit_wplus_sop_event 工具返回 ok=false，可根据返回的 allowed "
            "agent events 与 current_stage_id 修正参数后重试；失败调用不计入"
            "已持久化事件。不得成功持久化其他 W+ SOP 事件。调用参数必须满足 "
            "kind='stage_proposal'、"
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
    elif expected_event_kind == "question_batch":
        current_stage_id = payload.get("current_stage_id")
        question_batch_example = {
            **_QUESTION_BATCH_EXAMPLE,
            **(
                {"stage_id": current_stage_id}
                if isinstance(current_stage_id, str) and current_stage_id
                else {}
            ),
        }
        command_contract = (
            "\n本回合只允许成功持久化一个业务边界事件。若 "
            "emit_wplus_sop_event 工具返回 ok=false，可根据返回的 allowed "
            "agent events 与 current_stage_id 修正参数后重试；失败调用不计入"
            "已持久化事件。不得成功持久化其他 W+ SOP 事件。调用参数必须满足 "
            "kind='question_batch'；"
            "不得提交 kind='stage_queue_confirmed'，该确认事件已由工作流服务端"
            "持久化。event_key 必须根据当前 stage_id 保持稳定。payload 必须根据"
            "已确认环节队列和当前环节新生成，不得把命令输入中的 payload 原样提交。"
            "question_batch.stage_id 必须严格等于命令 payload.current_stage_id="
            + json.dumps(current_stage_id, ensure_ascii=False)
            + "。"
            "不得只输出 Markdown；Markdown 只能作为工具提交成功后的可读摘要。"
            "payload 顶层必须且只能包含 batch_id、stage_id、questions；questions "
            "必须包含 1 到 3 个符合 schema 的问题。\n"
            "question_batch payload 示例：\n"
            + json.dumps(
                question_batch_example,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    elif is_trial_turn:
        command_contract = _build_trial_command_contract(
            run_id=run_id,
            attempt_id=attempt_id,
            requires_plan=effective_target_state == "GeneratingTrial",
        )
    return (
        "执行下面由专用 W+ SOP 工作流界面提交的结构化命令。"
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
    target_state: str | None = None,
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
                    target_state=target_state,
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
    if target_state is not None:
        native_payload["meta"]["wplus_sop_target_state"] = target_state

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
