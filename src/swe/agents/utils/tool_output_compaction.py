# -*- coding: utf-8 -*-
"""Recover oversized textual tool output without exceeding a byte budget."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


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

    artifact_path = artifact_dir / f"{uuid4().hex}.txt"
    notice = _truncation_notice(
        original_bytes=original_bytes,
        retained_bytes=max_bytes,
        artifact_path=artifact_path,
        max_bytes=max_bytes,
        workspace_dir=workspace_dir,
    )
    encoded_notice = notice.encode("utf-8", errors="replace")

    if not _persist_artifact(artifact_path, encoded_text):
        return CompactedText(text, None, original_bytes, original_bytes)

    excerpt_budget = max_bytes - len(encoded_notice)
    excerpt = _line_aware_excerpt(encoded_text, excerpt_budget)
    compacted = (_sanitize_excerpt(excerpt) + encoded_notice).decode(
        "utf-8",
        errors="replace",
    )
    return CompactedText(compacted, artifact_path, original_bytes, max_bytes)


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
    artifact_path: Path,
    max_bytes: int,
    workspace_dir: Path | None,
) -> str:
    reference = _artifact_reference(artifact_path, workspace_dir)
    detailed_notice = (
        "\n<<<TRUNCATED>>> "
        f"original_bytes={original_bytes}; retained_bytes={retained_bytes}; "
        f"read_file {reference}\n"
    )
    compact_notice = (
        "\n<<<TRUNCATED>>> "
        f"bytes={original_bytes}/{retained_bytes}; read_file {reference}\n"
    )
    for notice in (detailed_notice, compact_notice):
        if len(notice.encode("utf-8", errors="replace")) <= max_bytes:
            return notice
    raise ValueError("max_bytes is too small for a usable artifact reference")


def _artifact_reference(
    artifact_path: Path,
    workspace_dir: Path | None,
) -> str:
    if workspace_dir is not None:
        resolved_artifact = artifact_path.resolve()
        resolved_workspace = workspace_dir.resolve()
        try:
            return resolved_artifact.relative_to(resolved_workspace).as_posix()
        except ValueError:
            return resolved_artifact.as_posix()
    if not artifact_path.is_absolute():
        return artifact_path.as_posix()
    return artifact_path.as_posix()


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
