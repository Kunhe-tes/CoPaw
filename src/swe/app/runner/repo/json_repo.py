# -*- coding: utf-8 -*-
"""JSON-based chat repository."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from swe.runtime_workers import run_runtime_state_work

from .base import BaseChatRepository
from ..models import ChatSpec, ChatsFile

_LOAD_STABLE_READ_ATTEMPTS = 3


@dataclass(frozen=True)
class _FileSignature:
    """Observable chats.json state used to validate in-process snapshots."""

    exists: bool
    mtime_ns: int | None = None
    ctime_ns: int | None = None
    size: int | None = None
    inode: int | None = None
    digest: str | None = None


@dataclass(frozen=True)
class _SnapshotState:
    """Private immutable snapshot container prepared off the event loop."""

    signature: _FileSignature
    chats_file: ChatsFile
    chat_index: dict[str, ChatSpec]


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

    def _file_signature(self) -> _FileSignature | None:
        try:
            before_stat = self._path.stat()
        except FileNotFoundError:
            try:
                self._path.stat()
            except FileNotFoundError:
                return _FileSignature(exists=False)
            return None

        try:
            contents = self._path.read_bytes()
            after_stat = self._path.stat()
        except FileNotFoundError:
            return None

        before_identity = (
            before_stat.st_size,
            before_stat.st_mtime_ns,
            before_stat.st_ctime_ns,
            before_stat.st_ino,
        )
        after_identity = (
            after_stat.st_size,
            after_stat.st_mtime_ns,
            after_stat.st_ctime_ns,
            after_stat.st_ino,
        )
        if before_identity != after_identity:
            return None

        return _FileSignature(
            exists=True,
            mtime_ns=after_stat.st_mtime_ns,
            ctime_ns=after_stat.st_ctime_ns,
            size=after_stat.st_size,
            inode=after_stat.st_ino,
            digest=hashlib.sha256(contents).hexdigest(),
        )

    def _load_sync(self) -> tuple[_FileSignature | None, ChatsFile]:
        last_chats_file = ChatsFile(version=1, chats=[])

        for _ in range(_LOAD_STABLE_READ_ATTEMPTS):
            before_signature = self._file_signature()
            if before_signature is None:
                continue

            if not before_signature.exists:
                chats_file = ChatsFile(version=1, chats=[])
                after_signature = self._file_signature()
            else:
                try:
                    data = json.loads(self._path.read_text(encoding="utf-8"))
                except FileNotFoundError:
                    continue
                chats_file = ChatsFile.model_validate(data)
                after_signature = self._file_signature()

            last_chats_file = chats_file
            if (
                after_signature is not None
                and before_signature == after_signature
            ):
                return after_signature, chats_file

        return None, last_chats_file

    def _save_sync(self, chats_file: ChatsFile) -> _FileSignature | None:
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

    def _prepare_snapshot_sync(
        self,
        signature: _FileSignature,
        chats_file: ChatsFile,
    ) -> _SnapshotState:
        snapshot = chats_file.model_copy(deep=True)
        return _SnapshotState(
            signature=signature,
            chats_file=snapshot,
            chat_index={chat.id: chat for chat in snapshot.chats},
        )

    def _load_and_prepare_snapshot_sync(
        self,
    ) -> tuple[_SnapshotState | None, ChatsFile]:
        signature, chats_file = self._load_sync()
        caller_chats_file = chats_file.model_copy(deep=True)
        if signature is None:
            return None, caller_chats_file
        return (
            self._prepare_snapshot_sync(signature, chats_file),
            caller_chats_file,
        )

    def _save_and_prepare_snapshot_sync(
        self,
        chats_file: ChatsFile,
    ) -> _SnapshotState | None:
        chats_file_to_save = chats_file.model_copy(deep=True)
        signature = self._save_sync(chats_file_to_save)
        if signature is None:
            return None
        return self._prepare_snapshot_sync(signature, chats_file_to_save)

    @staticmethod
    def _copy_chat_sync(chat: ChatSpec | None) -> ChatSpec | None:
        if chat is None:
            return None
        return chat.model_copy(deep=True)

    @staticmethod
    def _find_chat_copy_sync(
        chats_file: ChatsFile,
        chat_id: str,
    ) -> ChatSpec | None:
        for chat in chats_file.chats:
            if chat.id == chat_id:
                return chat.model_copy(deep=True)
        return None

    def _set_snapshot(self, snapshot_state: _SnapshotState | None) -> None:
        if snapshot_state is None:
            self._snapshot_signature = None
            self._snapshot = None
            self._chat_index = {}
            return

        self._snapshot_signature = snapshot_state.signature
        self._snapshot = snapshot_state.chats_file
        self._chat_index = snapshot_state.chat_index

    async def load(self) -> ChatsFile:
        """Load chat specs from JSON file.

        Returns:
            ChatsFile with all chat specs
        """
        snapshot_state, chats_file = await run_runtime_state_work(
            self._load_and_prepare_snapshot_sync,
        )
        self._set_snapshot(snapshot_state)
        return chats_file

    async def save(self, chats_file: ChatsFile) -> None:
        """Save chat specs to JSON file atomically.

        Args:
            chats_file: ChatsFile to persist
        """
        snapshot_state = await run_runtime_state_work(
            self._save_and_prepare_snapshot_sync,
            chats_file,
        )
        self._set_snapshot(snapshot_state)

    async def get_chat(self, chat_id: str) -> ChatSpec | None:
        """Get chat spec by chat_id (UUID), reusing a valid snapshot index."""
        signature = await run_runtime_state_work(self._file_signature)
        if (
            self._snapshot is not None
            and self._snapshot_signature == signature
        ):
            return await run_runtime_state_work(
                self._copy_chat_sync,
                self._chat_index.get(chat_id),
            )

        chats_file = await self.load()
        if self._snapshot is not None:
            return await run_runtime_state_work(
                self._copy_chat_sync,
                self._chat_index.get(chat_id),
            )
        return await run_runtime_state_work(
            self._find_chat_copy_sync,
            chats_file,
            chat_id,
        )
