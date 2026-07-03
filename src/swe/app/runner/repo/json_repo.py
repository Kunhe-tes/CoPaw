# -*- coding: utf-8 -*-
"""JSON-based chat repository."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from swe.runtime_workers import run_runtime_state_work

from .base import BaseChatRepository
from ..models import ChatSpec, ChatsFile


@dataclass(frozen=True)
class _FileSignature:
    """Observable chats.json state used to validate in-process snapshots."""

    exists: bool
    mtime_ns: int | None = None
    size: int | None = None


class JsonChatRepository(BaseChatRepository):
    """chats.json repository (single-file storage).

    Stores chat_id (UUID) -> session_id mappings in a JSON file.
    Similar to JsonJobRepository pattern from crons.

    Notes:
    - Single-machine, no cross-process lock.
    - Atomic write: write tmp then replace.
    """

    def __init__(self, path: Path | str):
        """Initialize JSON chat repository.

        Args:
            path: Path to chats.json file
        """
        if isinstance(path, str):
            path = Path(path)
        self._path = path.expanduser()
        self._snapshot_signature: _FileSignature | None = None
        self._snapshot: ChatsFile | None = None
        self._chat_index: dict[str, ChatSpec] = {}

    @property
    def path(self) -> Path:
        """Get the repository file path."""
        return self._path

    def _file_signature(self) -> _FileSignature:
        if not self._path.exists():
            return _FileSignature(exists=False)
        stat_result = self._path.stat()
        return _FileSignature(
            exists=True,
            mtime_ns=stat_result.st_mtime_ns,
            size=stat_result.st_size,
        )

    def _load_sync(self) -> tuple[_FileSignature, ChatsFile]:
        if not self._path.exists():
            return self._file_signature(), ChatsFile(version=1, chats=[])

        data = json.loads(self._path.read_text(encoding="utf-8"))
        chats_file = ChatsFile.model_validate(data)
        return self._file_signature(), chats_file

    def _save_sync(self, chats_file: ChatsFile) -> _FileSignature:
        # Create parent directory if needed
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file first (atomic write)
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = chats_file.model_dump(mode="json")

        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        # Atomic replace (shutil.move handles cross-disk on Windows)
        shutil.move(str(tmp_path), str(self._path))
        return self._file_signature()

    def _set_snapshot(
        self,
        signature: _FileSignature,
        chats_file: ChatsFile,
    ) -> None:
        self._snapshot_signature = signature
        self._snapshot = chats_file
        self._chat_index = {chat.id: chat for chat in chats_file.chats}

    async def load(self) -> ChatsFile:
        """Load chat specs from JSON file.

        Returns:
            ChatsFile with all chat specs
        """
        signature, chats_file = await run_runtime_state_work(self._load_sync)
        self._set_snapshot(signature, chats_file)
        return chats_file

    async def save(self, chats_file: ChatsFile) -> None:
        """Save chat specs to JSON file atomically.

        Args:
            chats_file: ChatsFile to persist
        """
        signature = await run_runtime_state_work(self._save_sync, chats_file)
        self._set_snapshot(signature, chats_file)

    async def get_chat(self, chat_id: str) -> ChatSpec | None:
        """Get chat spec by chat_id (UUID), reusing a valid snapshot index."""
        signature = await run_runtime_state_work(self._file_signature)
        if (
            self._snapshot is not None
            and self._snapshot_signature == signature
        ):
            return self._chat_index.get(chat_id)

        await self.load()
        return self._chat_index.get(chat_id)
