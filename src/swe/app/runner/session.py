# -*- coding: utf-8 -*-
"""Safe JSON session with filename sanitization for cross-platform
compatibility.

Windows filenames cannot contain: \\ / : * ? " < > |
This module wraps agentscope's SessionBase so that session_id and user_id
are sanitized before being used as filenames.
"""

import asyncio
import json
import logging
import os
import re
import threading
import tempfile

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Sequence, Union

from agentscope.session import SessionBase

from swe.runtime_workers import run_runtime_state_work

logger = logging.getLogger(__name__)
SESSION_SKILL_SNAPSHOT_STATE_KEY = "session_skill_snapshot"
_SESSION_WRITE_LOCKS: dict[
    tuple[asyncio.AbstractEventLoop, str],
    asyncio.Lock,
] = {}
_SESSION_WRITE_LOCKS_GUARD = threading.Lock()


# Characters forbidden in Windows filenames
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|]')
_ALLOWED_MESSAGE_ROLES = {"user", "assistant", "system"}


def sanitize_filename(name: str) -> str:
    """Replace characters that are illegal in Windows filenames with ``--``.

    >>> sanitize_filename('discord:dm:12345')
    'discord--dm--12345'
    >>> sanitize_filename('normal-name')
    'normal-name'
    """
    return _UNSAFE_FILENAME_RE.sub("--", name)


def _normalize_state_for_load(value):
    """在反序列化前把旧角色单向迁移到 AgentScope 可接受角色。"""
    if isinstance(value, list):
        return [_normalize_state_for_load(item) for item in value]

    if not isinstance(value, dict):
        return value

    normalized = {
        key: _normalize_state_for_load(item) for key, item in value.items()
    }
    role = normalized.get("role")
    if (
        isinstance(role, str)
        and role not in _ALLOWED_MESSAGE_ROLES
        and "name" in normalized
        and "content" in normalized
    ):
        normalized["role"] = "system"
    return normalized


def _get_session_write_lock(file_path: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    normalized_path = os.path.normcase(os.path.abspath(file_path))
    lock_key = (loop, normalized_path)
    with _SESSION_WRITE_LOCKS_GUARD:
        lock = _SESSION_WRITE_LOCKS.get(lock_key)
        if lock is None:
            lock = asyncio.Lock()
            _SESSION_WRITE_LOCKS[lock_key] = lock
        return lock


def _write_json_text(file_path: str, content: str) -> None:
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=os.path.dirname(file_path) or ".",
            prefix=f".{os.path.basename(file_path)}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temp_path = file.name
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, file_path)
    except Exception:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        raise


def _read_json_state_sync(
    session_save_path: str,
    *,
    allow_not_exist: bool,
    allow_empty: bool = False,
) -> tuple[bool, dict[str, Any]]:
    if not os.path.exists(session_save_path):
        if allow_not_exist:
            return False, {}
        raise ValueError(
            "Failed to load session state for file "
            f"{session_save_path} because it does not exist.",
        )

    with open(
        session_save_path,
        "r",
        encoding="utf-8",
        errors="surrogatepass",
    ) as file:
        content = file.read()

    if allow_empty and not content.strip():
        return True, {}

    states = json.loads(content)
    if not isinstance(states, dict):
        raise ValueError(
            f"Session file {session_save_path} does not contain "
            "a JSON object.",
        )
    return True, states


def _read_existing_state_for_save_sync(
    session_save_path: str,
) -> dict[str, Any]:
    """保存前读取已有状态，旧文件异常时沿用覆盖写入策略。"""
    if not os.path.exists(session_save_path):
        return {}

    with open(
        session_save_path,
        "r",
        encoding="utf-8",
        errors="surrogatepass",
    ) as file:
        content = file.read()

    if not content.strip():
        return {}

    try:
        loaded_state = json.loads(content)
    except json.JSONDecodeError:
        logger.warning(
            "Failed to parse existing session state at %s; "
            "overwriting with current state.",
            session_save_path,
        )
        return {}

    if isinstance(loaded_state, dict):
        return loaded_state
    return {}


def _write_json_state_sync(
    session_save_path: str,
    state: dict[str, Any],
) -> None:
    _write_json_text(
        session_save_path,
        json.dumps(state, ensure_ascii=False),
    )


class SafeJSONSession(SessionBase):
    """SessionBase subclass with filename sanitization and async file I/O.

    Uses :mod:`aiofiles` for reads and worker threads for writes so that
    disk I/O does not block the event loop.
    """

    def __init__(
        self,
        save_dir: str = "./",
    ) -> None:
        """Initialize the JSON session class.

        Args:
            save_dir (`str`, defaults to `"./"):
                The directory to save the session state.
        """
        self.save_dir = save_dir

    def _get_save_path(self, session_id: str, user_id: str) -> str:
        """Return a filesystem-safe save path.

        Overrides the parent implementation to ensure the generated
        filename is valid on Windows, macOS and Linux.
        """
        os.makedirs(self.save_dir, exist_ok=True)
        safe_sid = sanitize_filename(session_id)
        safe_uid = sanitize_filename(user_id) if user_id else ""
        if safe_uid:
            file_path = f"{safe_uid}_{safe_sid}.json"
        else:
            file_path = f"{safe_sid}.json"
        return os.path.join(self.save_dir, file_path)

    @asynccontextmanager
    async def session_write_lock(
        self,
        session_id: str,
        user_id: str = "",
        timeout_seconds: float | None = None,
    ) -> AsyncIterator[None]:
        """按会话文件串行化读改写，避免清理和运行结束互相覆盖。"""
        session_save_path = self._get_save_path(session_id, user_id=user_id)
        lock = _get_session_write_lock(session_save_path)
        if timeout_seconds is None:
            await lock.acquire()
        else:
            await asyncio.wait_for(lock.acquire(), timeout=timeout_seconds)
        try:
            yield
        finally:
            lock.release()

    async def _read_session_state_file(
        self,
        session_save_path: str,
        *,
        allow_not_exist: bool,
    ) -> tuple[bool, dict[str, Any]]:
        async with _get_session_write_lock(session_save_path):
            return await run_runtime_state_work(
                _read_json_state_sync,
                session_save_path,
                allow_not_exist=allow_not_exist,
            )

    async def _read_existing_state_for_save(
        self,
        session_save_path: str,
    ) -> dict[str, Any]:
        """保存前读取已有状态，旧文件异常时沿用覆盖写入策略。"""
        return await run_runtime_state_work(
            _read_existing_state_for_save_sync,
            session_save_path,
        )

    async def save_session_state(
        self,
        session_id: str,
        user_id: str = "",
        **state_modules_mapping,
    ) -> None:
        """Save state modules to a JSON file using async I/O."""
        session_save_path = self._get_save_path(session_id, user_id=user_id)
        async with _get_session_write_lock(session_save_path):
            existing_state = await self._read_existing_state_for_save(
                session_save_path,
            )
            state_dicts = {
                name: state_module.state_dict()
                for name, state_module in state_modules_mapping.items()
            }
            state_dicts = {**existing_state, **state_dicts}
            await run_runtime_state_work(
                _write_json_state_sync,
                session_save_path,
                state_dicts,
            )

        logger.info(
            "Saved session state to %s successfully.",
            session_save_path,
        )

    async def load_session_state(
        self,
        session_id: str,
        user_id: str = "",
        allow_not_exist: bool = True,
        **state_modules_mapping,
    ) -> None:
        """Load state modules from a JSON file using async I/O."""
        session_save_path = self._get_save_path(session_id, user_id=user_id)
        exists, states = await self._read_session_state_file(
            session_save_path,
            allow_not_exist=allow_not_exist,
        )
        if exists:
            for name, state_module in state_modules_mapping.items():
                if name in states:
                    normalized_state = _normalize_state_for_load(
                        states[name],
                    )
                    state_module.load_state_dict(normalized_state)
            logger.info(
                "Load session state from %s successfully.",
                session_save_path,
            )
        else:
            logger.info(
                "Session file %s does not exist. Skip loading session state.",
                session_save_path,
            )

    async def update_session_state(
        self,
        session_id: str,
        key: Union[str, Sequence[str]],
        value,
        user_id: str = "",
        create_if_not_exist: bool = True,
    ) -> None:
        path = key.split(".") if isinstance(key, str) else list(key)
        if not path:
            raise ValueError("key path is empty")

        def _mutate(states: dict[str, Any]) -> dict[str, Any]:
            cur = states
            for k in path[:-1]:
                if k not in cur or not isinstance(cur[k], dict):
                    cur[k] = {}
                cur = cur[k]

            cur[path[-1]] = value
            return states

        await self.mutate_session_state(
            session_id=session_id,
            mutator=_mutate,
            user_id=user_id,
            create_if_not_exist=create_if_not_exist,
        )

        logger.info(
            "Updated session state key '%s' in %s successfully.",
            key,
            self._get_save_path(session_id, user_id=user_id),
        )

    async def get_session_state_dict(
        self,
        session_id: str,
        user_id: str = "",
        allow_not_exist: bool = True,
    ) -> dict:
        """Return the session state dict from the JSON file.

        Args:
            session_id (`str`):
                The session id.
            user_id (`str`, default to `""`):
                The user ID for the storage.
            allow_not_exist (`bool`, defaults to `True`):
                Whether to allow the session to not exist. If `False`, raises
                an error if the session does not exist.

        Returns:
            `dict`:
                The session state dict loaded from the JSON file. Returns an
                empty dict if the file does not exist and
                `allow_not_exist=True`.
        """
        session_save_path = self._get_save_path(session_id, user_id=user_id)
        exists, states = await self._read_session_state_file(
            session_save_path,
            allow_not_exist=allow_not_exist,
        )
        if exists:
            logger.info(
                "Get session state dict from %s successfully.",
                session_save_path,
            )
            return states
        logger.info(
            "Session file %s does not exist. Return empty state dict.",
            session_save_path,
        )
        return {}

    async def get_session_skill_snapshot(
        self,
        session_id: str,
        user_id: str = "",
        allow_not_exist: bool = True,
    ) -> dict[str, dict]:
        """Return the persisted session skill snapshot."""
        state = await self.get_session_state_dict(
            session_id=session_id,
            user_id=user_id,
            allow_not_exist=allow_not_exist,
        )
        raw_snapshot = (
            state.get(SESSION_SKILL_SNAPSHOT_STATE_KEY)
            if isinstance(state, dict)
            else None
        )
        if not isinstance(raw_snapshot, dict):
            return {}

        snapshot: dict[str, dict] = {}
        for skill_name, entry in raw_snapshot.items():
            if isinstance(skill_name, str) and isinstance(entry, dict):
                snapshot[skill_name] = dict(entry)
        return snapshot

    async def save_session_skill_snapshot(
        self,
        session_id: str,
        snapshot: dict[str, dict],
        user_id: str = "",
    ) -> None:
        """Persist the top-level session skill snapshot."""
        await self.update_session_state(
            session_id=session_id,
            key=SESSION_SKILL_SNAPSHOT_STATE_KEY,
            value=snapshot,
            user_id=user_id,
        )

    async def save_merged_state(
        self,
        session_id: str,
        user_id: str = "",
        state: dict = None,
    ) -> None:
        """Save merged state dict to JSON file.

        Used by cron tasks to preserve existing session history while
        saving new state without overwriting.

        Args:
            session_id: The session id
            user_id: The user ID for the storage
            state: The merged state dict to save
        """
        if state is None:
            state = {}
        session_save_path = self._get_save_path(session_id, user_id=user_id)
        async with _get_session_write_lock(session_save_path):
            await run_runtime_state_work(
                _write_json_state_sync,
                session_save_path,
                state,
            )
        logger.info(
            "Saved merged session state to %s (keys=%d)",
            session_save_path,
            len(state),
        )

    async def mutate_session_state(
        self,
        session_id: str,
        mutator: Callable[[dict[str, Any]], dict[str, Any] | None],
        user_id: str = "",
        create_if_not_exist: bool = True,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Atomically read, merge and write session state under one lock."""
        session_save_path = self._get_save_path(session_id, user_id=user_id)
        lock = _get_session_write_lock(session_save_path)
        if timeout_seconds is None:
            await lock.acquire()
        else:
            await asyncio.wait_for(lock.acquire(), timeout=timeout_seconds)
        try:
            exists, states = await run_runtime_state_work(
                _read_json_state_sync,
                session_save_path,
                allow_not_exist=True,
                allow_empty=True,
            )
            if not exists and not create_if_not_exist:
                raise ValueError(
                    f"Session file {session_save_path} does not exist.",
                )

            updated_state = mutator(states)
            if updated_state is None:
                updated_state = states
            if not isinstance(updated_state, dict):
                raise ValueError("mutator must return a dict or None")

            await run_runtime_state_work(
                _write_json_state_sync,
                session_save_path,
                updated_state,
            )
        finally:
            lock.release()

        logger.info(
            "Mutated session state in %s successfully.",
            session_save_path,
        )
        return updated_state
