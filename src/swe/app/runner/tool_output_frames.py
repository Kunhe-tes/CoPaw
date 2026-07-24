# -*- coding: utf-8 -*-
"""Live presentation frames for running tool output."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterator, Literal

ToolOutputSource = Literal["stdout", "stderr", "message"]
ToolOutputFrame = dict[str, Any]
ToolOutputEmitter = Callable[[ToolOutputFrame], Awaitable[None]]

LIVE_TOOL_OUTPUT_MAX_BYTES = 64 * 1024
LIVE_TOOL_OUTPUT_MAX_LINES = 2000
LIVE_TOOL_OUTPUT_OMISSION_TEXT = "\n[早期实时输出已省略]\n"
TOOL_OUTPUT_TRUNCATION_PREFIX = "\n[工具输出已截断："

_LIVE_OUTPUT_TOOL_ALLOWLIST = frozenset({"execute_shell_command"})


@dataclass
class _ToolOutputInvocation:
    tool_call_id: str
    tool_name: str
    sequence: int = 0
    emitted_bytes: int = 0
    emitted_lines: int = 0
    truncated: bool = False


_emitter_var: ContextVar[ToolOutputEmitter | None] = ContextVar(
    "tool_output_frame_emitter",
    default=None,
)
_invocation_var: ContextVar[_ToolOutputInvocation | None] = ContextVar(
    "tool_output_frame_invocation",
    default=None,
)


@contextmanager
def bind_tool_output_emitter(
    emitter: ToolOutputEmitter,
) -> Iterator[None]:
    """Bind the live output frame emitter for the current execution context."""
    token = _emitter_var.set(emitter)
    try:
        yield
    finally:
        _emitter_var.reset(token)


@contextmanager
def tool_output_invocation(
    *,
    tool_call_id: str,
    tool_name: str,
) -> Iterator[None]:
    """Bind the currently executing tool invocation for live output frames."""
    token = _invocation_var.set(
        _ToolOutputInvocation(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        ),
    )
    try:
        yield
    finally:
        _invocation_var.reset(token)


def _line_count(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + int(not text.endswith("\n"))


def _text_bytes(text: str) -> int:
    return len(text.encode("utf-8", errors="replace"))


def _take_prefix_lines(
    lines: list[str],
    *,
    max_bytes: int,
    max_lines: int,
) -> list[str]:
    selected: list[str] = []
    used_bytes = 0
    for line in lines:
        line_bytes = _text_bytes(line)
        if len(selected) >= max_lines or used_bytes + line_bytes > max_bytes:
            break
        selected.append(line)
        used_bytes += line_bytes
    return selected


def _take_suffix_lines(
    lines: list[str],
    *,
    max_bytes: int,
    max_lines: int,
) -> list[str]:
    selected: list[str] = []
    used_bytes = 0
    for line in reversed(lines):
        line_bytes = _text_bytes(line)
        if len(selected) >= max_lines or used_bytes + line_bytes > max_bytes:
            break
        selected.append(line)
        used_bytes += line_bytes
    return list(reversed(selected))


def normalize_tool_output(
    text: str,
    *,
    max_bytes: int = LIVE_TOOL_OUTPUT_MAX_BYTES,
    max_lines: int = LIVE_TOOL_OUTPUT_MAX_LINES,
) -> str:
    """Return a bounded UTF-8-safe head-and-tail tool result."""
    if not text or max_bytes <= 0 or max_lines <= 0:
        return text
    if _text_bytes(text) <= max_bytes and _line_count(text) <= max_lines:
        return text

    original_bytes = _text_bytes(text)
    marker = (
        f"{TOOL_OUTPUT_TRUNCATION_PREFIX}原始 {original_bytes} bytes，"
        f"省略 {original_bytes} bytes]\n"
    )
    marker_bytes = _text_bytes(marker)
    marker_lines = _line_count(marker)
    if marker_bytes > max_bytes or marker_lines > max_lines:
        return marker.encode("utf-8", errors="replace")[:max_bytes].decode(
            "utf-8",
            errors="ignore",
        )

    available_bytes = max_bytes - marker_bytes
    available_lines = max_lines - marker_lines
    lines = text.splitlines(keepends=True)
    head = _take_prefix_lines(
        lines,
        max_bytes=available_bytes // 2,
        max_lines=available_lines // 2,
    )
    tail = _take_suffix_lines(
        lines[len(head) :],
        max_bytes=available_bytes - _text_bytes("".join(head)),
        max_lines=available_lines - len(head),
    )
    retained = "".join(head) + "".join(tail)
    omitted_bytes = original_bytes - _text_bytes(retained)
    marker = (
        f"{TOOL_OUTPUT_TRUNCATION_PREFIX}原始 {original_bytes} bytes，"
        f"省略 {omitted_bytes} bytes]\n"
    )
    return "".join(head) + marker + "".join(tail)


def _bounded_text(
    state: _ToolOutputInvocation,
    text: str,
) -> tuple[str, bool]:
    if state.truncated:
        return "", False

    remaining_bytes = LIVE_TOOL_OUTPUT_MAX_BYTES - state.emitted_bytes
    remaining_lines = LIVE_TOOL_OUTPUT_MAX_LINES - state.emitted_lines
    if remaining_bytes <= 0 or remaining_lines <= 0:
        state.truncated = True
        return LIVE_TOOL_OUTPUT_OMISSION_TEXT, True

    encoded = text.encode("utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    truncated = len(encoded) > remaining_bytes or len(lines) > remaining_lines
    if truncated:
        omission_bytes = _text_bytes(LIVE_TOOL_OUTPUT_OMISSION_TEXT)
        omission_lines = _line_count(LIVE_TOOL_OUTPUT_OMISSION_TEXT)
        content_bytes = max(0, remaining_bytes - omission_bytes)
        content_lines = max(0, remaining_lines - omission_lines)
        encoded = encoded[:content_bytes]
        text = encoded.decode("utf-8", errors="replace")
        text = "".join(text.splitlines(keepends=True)[:content_lines])

    if truncated:
        state.truncated = True
        text += LIVE_TOOL_OUTPUT_OMISSION_TEXT

    return text, truncated


async def emit_tool_output_text(
    source: ToolOutputSource,
    text: str,
) -> None:
    """Emit a guarded live output frame when the current context supports it."""
    if not text:
        return

    emitter = _emitter_var.get()
    state = _invocation_var.get()
    if emitter is None or state is None:
        return
    if state.tool_name not in _LIVE_OUTPUT_TOOL_ALLOWLIST:
        return

    frame_text, truncated = _bounded_text(state, text)
    if not frame_text:
        return

    state.sequence += 1
    state.emitted_bytes += len(frame_text.encode("utf-8", errors="replace"))
    state.emitted_lines += _line_count(frame_text)

    await emitter(
        {
            "object": "tool_output_frame",
            "tool_call_id": state.tool_call_id,
            "tool_name": state.tool_name,
            "sequence": state.sequence,
            "source": source,
            "text": frame_text,
            "truncated": truncated,
        },
    )
