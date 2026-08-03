# -*- coding: utf-8 -*-
"""Recover oversized textual tool output without exceeding a byte budget."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from agentscope.message import Msg

_CANONICAL_NOTICE_RE = re.compile(
    r"\n<<<TRUNCATED>>> "
    r"(?:original_bytes=(?P<original_bytes>\d+); "
    r"retained_bytes=(?P<retained_bytes>\d+)|"
    r"bytes=(?P<compact_original_bytes>\d+)/"
    r"(?P<compact_retained_bytes>\d+)); "
    r"read_file (?P<reference>[^\s]+)\n\Z",
)
_ARTIFACT_FILENAME_RE = re.compile(r"[0-9a-f]{32}\.txt\Z")
_MEDIA_BLOCK_TYPES = frozenset({"audio", "file", "image", "video"})


@dataclass(frozen=True)
class CompactedText:
    """A text output together with its recoverable full-output artifact."""

    text: str
    artifact_path: Path | None
    original_bytes: int
    retained_bytes: int


def compact_text_output(
    text: str,
    *,
    max_bytes: int,
    artifact_dir: Path,
    workspace_dir: Path | None = None,
) -> CompactedText:
    """Return *text* within ``max_bytes``, retaining oversized originals on disk."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")

    encoded_text = text.encode("utf-8", errors="replace")
    original_bytes = len(encoded_text)
    if original_bytes <= max_bytes:
        return CompactedText(text, None, original_bytes, original_bytes)

    if workspace_dir is None:
        return CompactedText(text, None, original_bytes, original_bytes)

    artifact_path = artifact_dir / f"{uuid4().hex}.txt"
    reference = _artifact_reference(artifact_path, workspace_dir)
    if reference is None:
        return CompactedText(text, None, original_bytes, original_bytes)
    try:
        notice = _truncation_notice(
            original_bytes=original_bytes,
            retained_bytes=max_bytes,
            artifact_reference=reference,
            max_bytes=max_bytes,
        )
    except ValueError:
        return CompactedText(text, None, original_bytes, original_bytes)
    encoded_notice = notice.encode("utf-8", errors="replace")

    if not _persist_artifact(artifact_path, encoded_text):
        return CompactedText(text, None, original_bytes, original_bytes)

    compacted = _compacted_display(
        encoded_text,
        notice=encoded_notice,
        max_bytes=max_bytes,
    )
    return CompactedText(compacted, artifact_path, original_bytes, max_bytes)


def compact_tool_result_messages(
    messages: list[Msg],
    *,
    old_max_bytes: int,
    recent_max_bytes: int,
    recent_n: int,
    artifact_dir: Path,
    workspace_dir: Path,
) -> list[Msg]:
    """Compact text in tool-result messages while retaining media blocks.

    The latest contiguous run of tool-result messages uses the larger recent
    budget. Older tool results use the historical budget. Existing canonical
    displays are re-excerpted from their original artifact, never persisted
    as a second full-output artifact.
    """
    if old_max_bytes < 1 or recent_max_bytes < 1:
        raise ValueError("tool result byte budgets must be positive")
    if recent_n < 1:
        raise ValueError("recent_n must be positive")

    recent_indexes = _recent_tool_result_indexes(messages, recent_n)
    for index, message in enumerate(messages):
        tool_result_blocks = _tool_result_blocks(message)
        if not tool_result_blocks:
            continue
        max_bytes = (
            recent_max_bytes if index in recent_indexes else old_max_bytes
        )
        for block in tool_result_blocks:
            for key in ("content", "output"):
                if key in block:
                    block[key] = _compact_textual_value(
                        block[key],
                        max_bytes=max_bytes,
                        artifact_dir=artifact_dir,
                        workspace_dir=workspace_dir,
                    )
    return messages


def cleanup_expired_artifacts(
    artifact_dir: Path,
    *,
    retention_days: int,
) -> None:
    """Best-effort removal of expired tool-result artifacts."""
    if retention_days < 1:
        raise ValueError("retention_days must be positive")

    try:
        cutoff = time.time() - retention_days * 24 * 60 * 60
        for artifact_path in artifact_dir.glob("*.txt"):
            try:
                if (
                    artifact_path.is_file()
                    and artifact_path.stat().st_mtime < cutoff
                ):
                    artifact_path.unlink()
            except OSError:
                continue
    except OSError:
        return


def _persist_artifact(artifact_path: Path, content: bytes) -> bool:
    temporary_path = (
        artifact_path.parent / f".{artifact_path.name}.{uuid4().hex}.tmp"
    )
    try:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with temporary_path.open("xb") as artifact_file:
            artifact_file.write(content)
            artifact_file.flush()
            os.fsync(artifact_file.fileno())
        temporary_path.replace(artifact_path)
    except OSError:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    return True


def _truncation_notice(
    *,
    original_bytes: int,
    retained_bytes: int,
    artifact_reference: str,
    max_bytes: int,
) -> str:
    detailed_notice = (
        "\n<<<TRUNCATED>>> "
        f"original_bytes={original_bytes}; retained_bytes={retained_bytes}; "
        f"read_file {artifact_reference}\n"
    )
    compact_notice = (
        "\n<<<TRUNCATED>>> "
        f"bytes={original_bytes}/{retained_bytes}; read_file {artifact_reference}\n"
    )
    for notice in (detailed_notice, compact_notice):
        if len(notice.encode("utf-8", errors="replace")) <= max_bytes:
            return notice
    raise ValueError("max_bytes is too small for a usable artifact reference")


def _artifact_reference(
    artifact_path: Path,
    workspace_dir: Path,
) -> str | None:
    resolved_artifact = artifact_path.resolve()
    resolved_workspace = workspace_dir.resolve()
    try:
        return resolved_artifact.relative_to(resolved_workspace).as_posix()
    except ValueError:
        return None


def _compacted_display(
    content: bytes,
    *,
    notice: bytes,
    max_bytes: int,
) -> str:
    excerpt_budget = max_bytes - len(notice)
    excerpt = _line_aware_excerpt(content, excerpt_budget)
    return (_sanitize_excerpt(excerpt) + notice).decode(
        "utf-8",
        errors="replace",
    )


def _recent_tool_result_indexes(
    messages: list[Msg],
    recent_n: int,
) -> set[int]:
    """Select at least the N newest tool results and the trailing run."""
    recent_indexes: set[int] = set()
    for index in range(len(messages) - 1, -1, -1):
        if _tool_result_blocks(messages[index]):
            recent_indexes.add(index)
            if len(recent_indexes) == recent_n:
                break

    for index in range(len(messages) - 1, -1, -1):
        if not _tool_result_blocks(messages[index]):
            break
        recent_indexes.add(index)
    return recent_indexes


def _tool_result_blocks(message: Msg) -> list[dict[str, Any]]:
    content = getattr(message, "content", None)
    if not isinstance(content, list):
        return []
    return [
        block
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]


def _compact_textual_value(
    value: Any,
    *,
    max_bytes: int,
    artifact_dir: Path,
    workspace_dir: Path,
) -> Any:
    if isinstance(value, str):
        return _compact_display_text(
            value,
            max_bytes=max_bytes,
            artifact_dir=artifact_dir,
            workspace_dir=workspace_dir,
        )
    if isinstance(value, list):
        return [
            _compact_textual_value(
                item,
                max_bytes=max_bytes,
                artifact_dir=artifact_dir,
                workspace_dir=workspace_dir,
            )
            for item in value
        ]
    if not isinstance(value, dict):
        return value
    if value.get("type") in _MEDIA_BLOCK_TYPES:
        return value

    compacted = value.copy()
    text = compacted.get("text")
    if isinstance(text, str):
        compacted["text"] = _compact_display_text(
            text,
            max_bytes=max_bytes,
            artifact_dir=artifact_dir,
            workspace_dir=workspace_dir,
        )
    for key in ("content", "output"):
        if key in compacted:
            compacted[key] = _compact_textual_value(
                compacted[key],
                max_bytes=max_bytes,
                artifact_dir=artifact_dir,
                workspace_dir=workspace_dir,
            )
    return compacted


def _compact_display_text(
    text: str,
    *,
    max_bytes: int,
    artifact_dir: Path,
    workspace_dir: Path,
) -> str:
    existing = _existing_artifact(text, workspace_dir)
    if existing is not None:
        artifact_path, content = existing
        if len(content) <= max_bytes:
            return text
        reference = _artifact_reference(artifact_path, workspace_dir)
        if reference is None:
            return text
        try:
            notice = _truncation_notice(
                original_bytes=len(content),
                retained_bytes=max_bytes,
                artifact_reference=reference,
                max_bytes=max_bytes,
            ).encode("utf-8", errors="replace")
        except ValueError:
            return text
        return _compacted_display(content, notice=notice, max_bytes=max_bytes)

    if _CANONICAL_NOTICE_RE.search(text):
        return text
    return compact_text_output(
        text,
        max_bytes=max_bytes,
        artifact_dir=artifact_dir,
        workspace_dir=workspace_dir,
    ).text


def _existing_artifact(
    text: str,
    workspace_dir: Path,
) -> tuple[Path, bytes] | None:
    match = _CANONICAL_NOTICE_RE.search(text)
    if match is None:
        return None
    reference = match.group("reference")
    candidate = workspace_dir / reference
    try:
        artifact_path = candidate.resolve(strict=True)
        artifact_dir = (workspace_dir / "tool_result").resolve()
        if (
            artifact_path.parent != artifact_dir
            or not _ARTIFACT_FILENAME_RE.fullmatch(artifact_path.name)
            or reference != f"tool_result/{artifact_path.name}"
        ):
            return None
        if not artifact_path.is_file():
            return None
        return artifact_path, artifact_path.read_bytes()
    except (OSError, ValueError):
        return None


def _line_aware_excerpt(content: bytes, max_bytes: int) -> bytes:
    if max_bytes == 0:
        return b""

    head_limit = max_bytes // 2
    head = _utf8_prefix(content, head_limit)
    last_newline = head.rfind(b"\n")
    if last_newline >= 0:
        head = head[: last_newline + 1]

    tail_limit = max_bytes - len(head)
    tail = _utf8_suffix(content[len(head) :], tail_limit)
    padding = b" " * (max_bytes - len(head) - len(tail))
    return head + padding + tail


def _utf8_prefix(content: bytes, max_bytes: int) -> bytes:
    candidate = content[:max_bytes]
    while candidate:
        decoded = candidate.decode("utf-8", errors="replace")
        encoded = decoded.encode("utf-8", errors="replace")
        if encoded == candidate:
            return encoded
        candidate = candidate[:-1]
    return b""


def _utf8_suffix(content: bytes, max_bytes: int) -> bytes:
    candidate = content[-max_bytes:]
    while candidate:
        decoded = candidate.decode("utf-8", errors="replace")
        encoded = decoded.encode("utf-8", errors="replace")
        if encoded == candidate:
            return encoded
        candidate = candidate[1:]
    return b""


def _sanitize_excerpt(excerpt: bytes) -> bytes:
    return excerpt.replace(b"<<<TRUNCATED>>>", b"<<<TRUNCATED>>?")
