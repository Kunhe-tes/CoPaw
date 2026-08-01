# -*- coding: utf-8 -*-
"""Chat-scoped, durable archives for compacted conversation messages."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
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

import fcntl

from agentscope.message import Msg

from swe.app.runner.hidden_context_injection import (
    redact_hidden_context_for_display,
)

logger = logging.getLogger(__name__)

_MANIFEST_NAME = "manifest.json"
_MAX_PAGE_SIZE = 50
_CURSOR_SIGNATURE_SIZE = hashlib.sha256().digest_size
_CURSOR_SECRET = os.urandom(_CURSOR_SIGNATURE_SIZE)


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
        if not isinstance(value, dict):
            raise ValueError("boundary must be a JSON object")
        return cls(
            id=cls._canonical_uuid(value["id"], "id"),
            chat_id=cls._canonical_uuid(value["chat_id"], "chat_id"),
            created_at=cls._timestamp(value["created_at"], "created_at"),
            archived_message_count=cls._positive_int(
                value["archived_message_count"],
                "archived_message_count",
            ),
            first_message_id=cls._non_empty_string(
                value["first_message_id"],
                "first_message_id",
            ),
            last_message_id=cls._non_empty_string(
                value["last_message_id"],
                "last_message_id",
            ),
            first_timestamp=cls._optional_string(value["first_timestamp"]),
            last_timestamp=cls._optional_string(value["last_timestamp"]),
        )

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None or isinstance(value, str):
            return value
        raise ValueError("timestamp must be a string or null")

    @staticmethod
    def _canonical_uuid(value: Any, field: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a canonical UUID string")
        try:
            parsed = uuid.UUID(value)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(
                f"{field} must be a canonical UUID string",
            ) from exc
        if str(parsed) != value:
            raise ValueError(f"{field} must be a canonical UUID string")
        return value

    @staticmethod
    def _non_empty_string(value: Any, field: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field} must be a non-empty string")
        return value

    @staticmethod
    def _positive_int(value: Any, field: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"{field} must be a positive integer")
        return value

    @staticmethod
    def _timestamp(value: Any, field: str) -> str:
        value = ConversationArchiveBoundary._non_empty_string(value, field)
        try:
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO timestamp") from exc
        return value


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

        chat_dir = self.path_for(canonical_chat_id)
        chat_dir.mkdir(parents=True, exist_ok=True)
        with self._chat_lock(chat_dir):
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
            manifest["boundaries"].append(boundary.to_dict())
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
        chat_dir = self.path_for(canonical_chat_id)
        manifest = self._read_manifest(chat_dir / _MANIFEST_NAME)
        boundaries = self._visible_boundaries(manifest, canonical_chat_id)
        cursor = (
            self._decode_cursor(
                before,
                canonical_chat_id,
                boundaries,
                chat_dir,
            )
            if before
            else None
        )
        selected = self._select_page(chat_dir, boundaries, cursor, page_size)

        messages = [item[2] for item in reversed(selected)]
        page_boundaries = [
            item[0]
            for item in reversed(selected)
            if item[2].id == item[0].last_message_id
        ]
        has_more = len(selected) == page_size and self._has_previous_message(
            chat_dir,
            boundaries,
            selected,
        )
        next_cursor = None
        if has_more and selected:
            oldest = selected[-1]
            next_cursor = self._encode_cursor(
                canonical_chat_id,
                oldest[0].id,
                oldest[1],
            )
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
        chat_dir = self.path_for(canonical_chat_id)
        if chat_dir.exists():
            shutil.rmtree(chat_dir)

    def _chat_dir(self, canonical_chat_id: str) -> Path:
        return self._dialog_root / canonical_chat_id

    def path_for(self, chat_id: str) -> Path:
        """Return the validated archive directory for one chat record."""
        return self._chat_dir(self._validate_chat_id(chat_id))

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
            if not self._batch_matches_boundary(boundary, records):
                logger.warning(
                    "Skipping inconsistent conversation archive batch: %s",
                    boundary.id,
                )
                continue
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

    @staticmethod
    def _batch_matches_boundary(
        boundary: ConversationArchiveBoundary,
        records: list[Msg | None],
    ) -> bool:
        if len(records) < boundary.archived_message_count:
            return False
        if not records or records[0] is None or records[-1] is None:
            return False
        first_message = records[0]
        last_message = records[-1]
        return bool(
            first_message.id == boundary.first_message_id
            and last_message.id == boundary.last_message_id
            and first_message.timestamp == boundary.first_timestamp
            and last_message.timestamp == boundary.last_timestamp,
        )

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
            ConversationArchiveStore._fsync_directory(path.parent)
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    @contextlib.contextmanager
    def _chat_lock(chat_dir: Path):
        lock_path = chat_dir / ".manifest.lock"
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

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
    def _encode_cursor(
        chat_id: str,
        boundary_id: str,
        message_index: int,
    ) -> str:
        raw = json.dumps(
            {
                "chat_id": chat_id,
                "boundary_id": boundary_id,
                "message_index": message_index,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        signature = hmac.new(
            _CURSOR_SECRET,
            raw,
            hashlib.sha256,
        ).digest()
        return (
            base64.urlsafe_b64encode(raw + signature)
            .decode("ascii")
            .rstrip("=")
        )

    @staticmethod
    def _decode_cursor(
        cursor: str,
        chat_id: str,
        boundaries: list[ConversationArchiveBoundary],
        chat_dir: Path,
    ) -> tuple[str, int]:
        if not isinstance(cursor, str):
            raise ValueError("Invalid conversation archive cursor")
        try:
            padding = "=" * (-len(cursor) % 4)
            signed_value = base64.urlsafe_b64decode(cursor + padding)
            raw, signature = (
                signed_value[:-_CURSOR_SIGNATURE_SIZE],
                signed_value[-_CURSOR_SIGNATURE_SIZE:],
            )
            expected_signature = hmac.new(
                _CURSOR_SECRET,
                raw,
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(signature, expected_signature):
                raise ValueError("invalid signature")
            value = json.loads(raw.decode("utf-8"))
            cursor_chat_id = value["chat_id"]
            boundary_id = value["boundary_id"]
            message_index = value["message_index"]
        except (
            KeyError,
            TypeError,
            ValueError,
            UnicodeDecodeError,
            base64.binascii.Error,
        ) as exc:
            raise ValueError("Invalid conversation archive cursor") from exc
        if (
            cursor_chat_id != chat_id
            or not isinstance(message_index, int)
            or isinstance(message_index, bool)
            or message_index < 0
        ):
            raise ValueError("Invalid conversation archive cursor")
        try:
            boundary_id = ConversationArchiveBoundary._canonical_uuid(
                boundary_id,
                "boundary_id",
            )
        except ValueError as exc:
            raise ValueError("Invalid conversation archive cursor") from exc
        boundary = next(
            (item for item in boundaries if item.id == boundary_id),
            None,
        )
        if boundary is None:
            raise ValueError("Invalid conversation archive cursor")
        records = ConversationArchiveStore._read_batch(
            chat_dir / f"{boundary.id}.jsonl",
        )
        if message_index >= len(records) or records[message_index] is None:
            raise ValueError("Invalid conversation archive cursor")
        return boundary_id, message_index


__all__ = [
    "ConversationArchiveBoundary",
    "ConversationArchivePage",
    "ConversationArchiveStore",
]
