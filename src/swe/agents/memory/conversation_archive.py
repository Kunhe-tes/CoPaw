# -*- coding: utf-8 -*-
"""Chat-scoped, durable archives for compacted conversation messages."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from agentscope.message import Msg

from swe.app.runner.hidden_context_injection import (
    redact_hidden_context_for_display,
)

logger = logging.getLogger(__name__)

_MANIFEST_NAME = "manifest.json"
_MAX_PAGE_SIZE = 50


@dataclass(frozen=True)
class ConversationArchiveBoundary:
    """Metadata for one immutable archive batch."""

    id: str
    chat_id: str
    created_at: str
    archived_message_count: int
    first_message_id: str
    last_message_id: str
    first_timestamp: str | None
    last_timestamp: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON representation persisted in the manifest."""
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "created_at": self.created_at,
            "archived_message_count": self.archived_message_count,
            "first_message_id": self.first_message_id,
            "last_message_id": self.last_message_id,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ConversationArchiveBoundary":
        """Parse one manifest entry."""
        return cls(
            id=str(value["id"]),
            chat_id=str(value["chat_id"]),
            created_at=str(value["created_at"]),
            archived_message_count=int(value["archived_message_count"]),
            first_message_id=str(value["first_message_id"]),
            last_message_id=str(value["last_message_id"]),
            first_timestamp=cls._optional_string(value["first_timestamp"]),
            last_timestamp=cls._optional_string(value["last_timestamp"]),
        )

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None or isinstance(value, str):
            return value
        raise ValueError("timestamp must be a string or null")


@dataclass(frozen=True)
class ConversationArchivePage:
    """One chronological page of archived messages and their boundaries."""

    messages: list[Msg]
    boundaries: list[ConversationArchiveBoundary]
    has_more: bool
    next_cursor: str | None


class ConversationArchiveStore:
    """Persist and page compacted messages without cross-chat visibility."""

    def __init__(self, dialog_root: str | Path) -> None:
        self._dialog_root = Path(dialog_root)

    async def commit(
        self,
        chat_id: str,
        messages: Sequence[Msg],
    ) -> ConversationArchiveBoundary:
        """Write one immutable batch, then make it visible through manifest."""
        return await asyncio.to_thread(self._commit, chat_id, messages)

    def _commit(
        self,
        chat_id: str,
        messages: Sequence[Msg],
    ) -> ConversationArchiveBoundary:
        canonical_chat_id = self._validate_chat_id(chat_id)
        if not messages:
            raise ValueError("Cannot archive an empty message batch")

        archived_messages = list(messages)
        if not all(isinstance(message, Msg) for message in archived_messages):
            raise TypeError(
                "Conversation archive messages must be Msg instances",
            )

        chat_dir = self._chat_dir(canonical_chat_id)
        chat_dir.mkdir(parents=True, exist_ok=True)
        boundary = ConversationArchiveBoundary(
            id=str(uuid.uuid4()),
            chat_id=canonical_chat_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            archived_message_count=len(archived_messages),
            first_message_id=archived_messages[0].id,
            last_message_id=archived_messages[-1].id,
            first_timestamp=archived_messages[0].timestamp,
            last_timestamp=archived_messages[-1].timestamp,
        )
        batch_path = chat_dir / f"{boundary.id}.jsonl"
        self._write_batch(batch_path, archived_messages)

        manifest_path = chat_dir / _MANIFEST_NAME
        manifest = self._read_manifest(manifest_path)
        boundaries = manifest["boundaries"]
        boundaries.append(boundary.to_dict())
        self._replace_manifest(manifest_path, manifest)
        return boundary

    async def read_page(
        self,
        chat_id: str,
        before: str | None = None,
        limit: int = _MAX_PAGE_SIZE,
    ) -> ConversationArchivePage:
        """Read archived messages newest-first, returned in timeline order."""
        return await asyncio.to_thread(self._read_page, chat_id, before, limit)

    def _read_page(
        self,
        chat_id: str,
        before: str | None = None,
        limit: int = _MAX_PAGE_SIZE,
    ) -> ConversationArchivePage:
        canonical_chat_id = self._validate_chat_id(chat_id)
        page_size = self._normalize_page_size(limit)
        chat_dir = self._chat_dir(canonical_chat_id)
        manifest = self._read_manifest(chat_dir / _MANIFEST_NAME)
        boundaries = self._visible_boundaries(manifest, canonical_chat_id)
        cursor = self._decode_cursor(before) if before else None
        selected = self._select_page(chat_dir, boundaries, cursor, page_size)

        messages = [item[2] for item in reversed(selected)]
        page_boundaries = [
            item[0]
            for item in reversed(selected)
            if item[1] == item[0].archived_message_count - 1
        ]
        has_more = len(selected) == page_size and self._has_previous_message(
            chat_dir,
            boundaries,
            selected,
        )
        next_cursor = None
        if has_more and selected:
            oldest = selected[-1]
            next_cursor = self._encode_cursor(oldest[0].id, oldest[1])
        return ConversationArchivePage(
            messages=messages,
            boundaries=page_boundaries,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    async def delete_chat(self, chat_id: str) -> None:
        """Delete only the validated chat's archive directory."""
        await asyncio.to_thread(self._delete_chat, chat_id)

    def _delete_chat(self, chat_id: str) -> None:
        canonical_chat_id = self._validate_chat_id(chat_id)
        chat_dir = self._chat_dir(canonical_chat_id)
        if chat_dir.exists():
            shutil.rmtree(chat_dir)

    def _chat_dir(self, canonical_chat_id: str) -> Path:
        return self._dialog_root / canonical_chat_id

    @staticmethod
    def _validate_chat_id(chat_id: str) -> str:
        if not isinstance(chat_id, str):
            raise ValueError("chat_id must be a canonical UUID string")
        try:
            parsed = uuid.UUID(chat_id)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(
                "chat_id must be a canonical UUID string",
            ) from exc
        if str(parsed) != chat_id:
            raise ValueError("chat_id must be a canonical UUID string")
        return chat_id

    @staticmethod
    def _normalize_page_size(limit: int) -> int:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        return min(limit, _MAX_PAGE_SIZE)

    @staticmethod
    def _read_manifest(path: Path) -> dict[str, list[dict[str, Any]]]:
        if not path.exists():
            return {"boundaries": []}
        with path.open("r", encoding="utf-8") as file_handle:
            value = json.load(file_handle)
        boundaries = (
            value.get("boundaries") if isinstance(value, dict) else None
        )
        if not isinstance(boundaries, list):
            raise ValueError(
                "Conversation archive manifest has invalid boundaries",
            )
        return {"boundaries": boundaries}

    @staticmethod
    def _visible_boundaries(
        manifest: dict[str, list[dict[str, Any]]],
        chat_id: str,
    ) -> list[ConversationArchiveBoundary]:
        boundaries: list[ConversationArchiveBoundary] = []
        for value in manifest["boundaries"]:
            try:
                boundary = ConversationArchiveBoundary.from_dict(value)
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "Skipping malformed conversation archive boundary: %s",
                    exc,
                )
                continue
            if boundary.chat_id != chat_id:
                logger.warning(
                    "Skipping conversation archive boundary for another chat: %s",
                    boundary.id,
                )
                continue
            boundaries.append(boundary)
        return boundaries

    def _select_page(
        self,
        chat_dir: Path,
        boundaries: list[ConversationArchiveBoundary],
        cursor: tuple[str, int] | None,
        limit: int,
    ) -> list[tuple[ConversationArchiveBoundary, int, Msg]]:
        selected: list[tuple[ConversationArchiveBoundary, int, Msg]] = []
        before_reached = cursor is None
        for boundary in reversed(boundaries):
            records = self._read_batch(chat_dir / f"{boundary.id}.jsonl")
            upper_index = len(records) - 1
            if cursor is not None and boundary.id == cursor[0]:
                before_reached = True
                upper_index = min(upper_index, cursor[1] - 1)
            elif cursor is not None and not before_reached:
                continue

            for index in range(upper_index, -1, -1):
                message = records[index]
                if message is None:
                    continue
                selected.append((boundary, index, message))
                if len(selected) == limit:
                    return selected
        return selected

    def _has_previous_message(
        self,
        chat_dir: Path,
        boundaries: list[ConversationArchiveBoundary],
        selected: list[tuple[ConversationArchiveBoundary, int, Msg]],
    ) -> bool:
        if not selected:
            return False
        boundary_id, message_index, _message = selected[-1]
        return bool(
            self._select_page(
                chat_dir,
                boundaries,
                (boundary_id.id, message_index),
                1,
            ),
        )

    def _write_batch(self, path: Path, messages: Sequence[Msg]) -> None:
        payload = "".join(
            json.dumps(message.to_dict(), ensure_ascii=False) + "\n"
            for message in messages
        )
        self._atomic_write(path, payload)

    def _replace_manifest(
        self,
        path: Path,
        manifest: dict[str, list[dict[str, Any]]],
    ) -> None:
        self._atomic_write(
            path,
            json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
        )

    @staticmethod
    def _atomic_write(path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                delete=False,
            ) as file_handle:
                temporary_path = Path(file_handle.name)
                file_handle.write(payload)
                file_handle.flush()
                os.fsync(file_handle.fileno())
            os.replace(temporary_path, path)
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _read_batch(path: Path) -> list[Msg | None]:
        if not path.is_file():
            logger.warning("Conversation archive batch is missing: %s", path)
            return []
        records: list[Msg | None] = []
        with path.open("r", encoding="utf-8") as file_handle:
            for line_number, line in enumerate(file_handle, start=1):
                try:
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError("record is not a JSON object")
                    records.append(
                        redact_hidden_context_for_display(
                            Msg.from_dict(value),
                        ),
                    )
                except (
                    KeyError,
                    TypeError,
                    ValueError,
                    json.JSONDecodeError,
                ) as exc:
                    logger.warning(
                        "Skipping malformed conversation archive record %s:%d: %s",
                        path,
                        line_number,
                        exc,
                    )
                    records.append(None)
        return records

    @staticmethod
    def _encode_cursor(boundary_id: str, message_index: int) -> str:
        raw = json.dumps(
            {"boundary_id": boundary_id, "message_index": message_index},
            separators=(",", ":"),
        ).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[str, int]:
        if not isinstance(cursor, str):
            raise ValueError("Invalid conversation archive cursor")
        try:
            padding = "=" * (-len(cursor) % 4)
            value = json.loads(
                base64.urlsafe_b64decode(cursor + padding).decode("utf-8"),
            )
            boundary_id = value["boundary_id"]
            message_index = value["message_index"]
        except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
            raise ValueError("Invalid conversation archive cursor") from exc
        if (
            not isinstance(boundary_id, str)
            or not isinstance(message_index, int)
            or isinstance(message_index, bool)
            or message_index < 0
        ):
            raise ValueError("Invalid conversation archive cursor")
        return boundary_id, message_index


__all__ = [
    "ConversationArchiveBoundary",
    "ConversationArchivePage",
    "ConversationArchiveStore",
]
