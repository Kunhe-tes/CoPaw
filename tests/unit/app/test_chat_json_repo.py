# -*- coding: utf-8 -*-
"""Tests for JSON chat repository runtime-state worker boundaries."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from swe.app.runner.models import ChatSpec, ChatsFile
from swe.app.runner.repo import json_repo
from swe.app.runner.repo.json_repo import JsonChatRepository


def _write_chats(path: Path, chats: list[ChatSpec]) -> None:
    path.write_text(
        json.dumps(ChatsFile(version=1, chats=chats).model_dump(mode="json")),
        encoding="utf-8",
    )


def _saved_chats_payload(chats: list[ChatSpec]) -> str:
    return json.dumps(
        ChatsFile(version=1, chats=chats).model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


@pytest.mark.asyncio
async def test_chat_repo_load_uses_runtime_state_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "chats.json"
    _write_chats(
        path,
        [ChatSpec(session_id="s1", user_id="u1", channel="console")],
    )
    calls: list[str] = []
    operations: list[str] = []
    state = {"in_worker": False}

    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text
    original_loads = json.loads
    original_model_validate = ChatsFile.model_validate
    original_sha256 = json_repo.hashlib.sha256

    def guarded_read_bytes(self: Path):
        if self == path:
            assert state["in_worker"], "read_bytes ran outside runtime worker"
            operations.append("read")
        return original_read_bytes(self)

    def guarded_read_text(self: Path, *args, **kwargs):
        if self == path:
            raise AssertionError("load should not read text separately")
        return original_read_text(self, *args, **kwargs)

    def guarded_sha256(*args, **kwargs):
        assert state["in_worker"], "signature hash ran outside runtime worker"
        operations.append("hash")
        return original_sha256(*args, **kwargs)

    def guarded_loads(*args, **kwargs):
        assert state["in_worker"], "json.loads ran outside runtime worker"
        operations.append("parse")
        return original_loads(*args, **kwargs)

    def guarded_model_validate(cls, *args, **kwargs):
        assert state[
            "in_worker"
        ], "model validation ran outside runtime worker"
        operations.append("validate")
        return original_model_validate(*args, **kwargs)

    async def fake_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        assert not state["in_worker"]
        state["in_worker"] = True
        try:
            return func(*args, **kwargs)
        finally:
            state["in_worker"] = False

    monkeypatch.setattr(
        "swe.app.runner.repo.json_repo.run_runtime_state_work",
        fake_worker,
    )
    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(json_repo.hashlib, "sha256", guarded_sha256)
    monkeypatch.setattr(
        "swe.app.runner.repo.json_repo.json.loads",
        guarded_loads,
    )
    monkeypatch.setattr(
        ChatsFile,
        "model_validate",
        classmethod(guarded_model_validate),
    )

    repo = JsonChatRepository(path)
    loaded = await repo.load()

    assert [chat.session_id for chat in loaded.chats] == ["s1"]
    assert calls
    assert operations == ["read", "hash", "parse", "validate"]


@pytest.mark.asyncio
async def test_chat_repo_save_uses_runtime_state_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "chats.json"
    calls: list[str] = []
    operations: list[str] = []
    state = {"in_worker": False}

    original_model_dump = ChatsFile.model_dump
    original_dumps = json.dumps
    original_write_text = Path.write_text
    original_move = shutil.move

    def guarded_model_dump(self: ChatsFile, *args, **kwargs):
        assert state["in_worker"], "model dump ran outside runtime worker"
        operations.append("dump")
        return original_model_dump(self, *args, **kwargs)

    def guarded_dumps(*args, **kwargs):
        assert state["in_worker"], "json.dumps ran outside runtime worker"
        operations.append("encode")
        return original_dumps(*args, **kwargs)

    def guarded_write_text(self: Path, *args, **kwargs):
        if self == path.with_suffix(path.suffix + ".tmp"):
            assert state["in_worker"], "write_text ran outside runtime worker"
            operations.append("write")
        return original_write_text(self, *args, **kwargs)

    def guarded_move(*args, **kwargs):
        assert state["in_worker"], "shutil.move ran outside runtime worker"
        operations.append("move")
        return original_move(*args, **kwargs)

    async def fake_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        assert not state["in_worker"]
        state["in_worker"] = True
        try:
            return func(*args, **kwargs)
        finally:
            state["in_worker"] = False

    monkeypatch.setattr(
        "swe.app.runner.repo.json_repo.run_runtime_state_work",
        fake_worker,
    )
    monkeypatch.setattr(ChatsFile, "model_dump", guarded_model_dump)
    monkeypatch.setattr(
        "swe.app.runner.repo.json_repo.json.dumps",
        guarded_dumps,
    )
    monkeypatch.setattr(Path, "write_text", guarded_write_text)
    monkeypatch.setattr(
        "swe.app.runner.repo.json_repo.shutil.move",
        guarded_move,
    )

    repo = JsonChatRepository(path)
    await repo.save(
        ChatsFile(
            version=1,
            chats=[ChatSpec(session_id="s1", user_id="u1", channel="console")],
        ),
    )

    assert calls
    assert operations == ["dump", "encode", "write", "move"]
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["chats"][0]["session_id"] == "s1"


@pytest.mark.asyncio
async def test_chat_repo_get_chat_reuses_valid_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = JsonChatRepository(tmp_path / "chats.json")
    chat = ChatSpec(session_id="s1", user_id="u1", channel="console")
    await repo.save(ChatsFile(version=1, chats=[chat]))
    calls: list[str] = []
    state = {"in_worker": False}
    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(self: Path):
        if self == repo.path:
            assert state[
                "in_worker"
            ], "signature digest ran outside runtime worker"
        return original_read_bytes(self)

    async def fail_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        assert not state["in_worker"]
        state["in_worker"] = True
        if func.__name__ == "_load_and_prepare_snapshot_sync":
            raise AssertionError("snapshot should avoid full reload")
        try:
            return func(*args, **kwargs)
        finally:
            state["in_worker"] = False

    monkeypatch.setattr(
        "swe.app.runner.repo.json_repo.run_runtime_state_work",
        fail_worker,
    )
    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)

    loaded = await repo.get_chat(chat.id)

    assert loaded is not None
    assert loaded.session_id == "s1"
    assert calls == ["_file_signature", "_copy_chat_sync"]


@pytest.mark.asyncio
async def test_chat_repo_builds_snapshot_index_in_runtime_state_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "chats.json"
    _write_chats(
        path,
        [ChatSpec(session_id="s1", user_id="u1", channel="console")],
    )
    state = {"in_worker": False}
    original_getattribute = ChatSpec.__getattribute__

    async def fake_worker(func, /, *args, **kwargs):
        assert not state["in_worker"]
        state["in_worker"] = True
        try:
            return func(*args, **kwargs)
        finally:
            state["in_worker"] = False

    def guarded_getattribute(self: ChatSpec, name: str):
        if name == "id":
            assert state[
                "in_worker"
            ], "chat index built outside runtime worker"
        return original_getattribute(self, name)

    monkeypatch.setattr(
        "swe.app.runner.repo.json_repo.run_runtime_state_work",
        fake_worker,
    )
    monkeypatch.setattr(ChatSpec, "__getattribute__", guarded_getattribute)

    repo = JsonChatRepository(path)
    loaded = await repo.load()

    assert [chat.session_id for chat in loaded.chats] == ["s1"]


@pytest.mark.asyncio
async def test_chat_repo_retries_when_file_changes_during_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "chats.json"
    old_chat = ChatSpec(session_id="old", user_id="u1", channel="console")
    new_chat = ChatSpec(session_id="new", user_id="u1", channel="console")
    _write_chats(path, [old_chat])

    original_read_bytes = Path.read_bytes
    swapped = False

    def swapping_read_bytes(self: Path) -> bytes:
        nonlocal swapped
        contents = original_read_bytes(self)
        if self == path and not swapped:
            swapped = True
            _write_chats(path, [new_chat])
        return contents

    monkeypatch.setattr(Path, "read_bytes", swapping_read_bytes)

    repo = JsonChatRepository(path)
    await repo.load()

    assert await repo.get_chat(old_chat.id) is None
    loaded_new = await repo.get_chat(new_chat.id)
    assert loaded_new is not None
    assert loaded_new.session_id == "new"


@pytest.mark.asyncio
async def test_chat_repo_load_parses_the_same_bytes_used_for_signature(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "chats.json"
    old_chat = ChatSpec(session_id="old", user_id="u1", channel="console")
    new_chat = ChatSpec(session_id="new", user_id="u1", channel="console")
    _write_chats(path, [old_chat])
    new_payload = _saved_chats_payload([new_chat])
    read_text_calls = 0

    original_read_text = Path.read_text

    def mismatched_read_text(self: Path, *args, **kwargs):
        nonlocal read_text_calls
        if self == path:
            read_text_calls += 1
            return new_payload
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", mismatched_read_text)

    repo = JsonChatRepository(path)
    loaded = await repo.load()

    assert read_text_calls == 0
    assert [chat.id for chat in loaded.chats] == [old_chat.id]
    assert await repo.get_chat(new_chat.id) is None
    loaded_old = await repo.get_chat(old_chat.id)
    assert loaded_old is not None
    assert loaded_old.session_id == "old"


@pytest.mark.asyncio
async def test_chat_repo_get_chat_invalidates_published_snapshot_after_external_change(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.json"
    old_chat = ChatSpec(session_id="old", user_id="u1", channel="console")
    new_chat = ChatSpec(
        session_id="new-session-after-external-rewrite",
        user_id="u1",
        channel="console",
    )

    repo = JsonChatRepository(path)
    await repo.save(ChatsFile(version=1, chats=[old_chat]))
    _write_chats(path, [new_chat])

    assert await repo.get_chat(old_chat.id) is None
    loaded_new = await repo.get_chat(new_chat.id)

    assert loaded_new is not None
    assert loaded_new.id == new_chat.id
    assert loaded_new.session_id == "new-session-after-external-rewrite"


@pytest.mark.asyncio
async def test_chat_repo_get_chat_invalidates_snapshot_after_same_size_rewrite_with_restored_mtime(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.json"
    old_chat = ChatSpec(session_id="old", user_id="u1", channel="console")
    new_chat = old_chat.model_copy(
        update={
            "id": "00000000-0000-4000-8000-000000000000",
            "session_id": "new",
        },
    )

    repo = JsonChatRepository(path)
    await repo.save(ChatsFile(version=1, chats=[old_chat]))
    old_stat = path.stat()

    new_payload = _saved_chats_payload([new_chat])
    assert len(new_payload.encode("utf-8")) == old_stat.st_size
    path.write_text(new_payload, encoding="utf-8")
    os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))

    assert path.stat().st_size == old_stat.st_size
    assert path.stat().st_mtime_ns == old_stat.st_mtime_ns

    assert await repo.get_chat(old_chat.id) is None
    loaded_new = await repo.get_chat(new_chat.id)

    assert loaded_new is not None
    assert loaded_new.id == new_chat.id
    assert loaded_new.session_id == "new"


@pytest.mark.asyncio
async def test_chat_repo_get_chat_reload_when_signature_read_races_with_rewrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "chats.json"
    old_chat = ChatSpec(session_id="old", user_id="u1", channel="console")
    new_chat = old_chat.model_copy(
        update={
            "id": "00000000-0000-4000-8000-000000000000",
            "session_id": "new",
        },
    )

    repo = JsonChatRepository(path)
    await repo.save(ChatsFile(version=1, chats=[old_chat]))
    old_stat = path.stat()
    new_payload = _saved_chats_payload([new_chat])
    assert len(new_payload.encode("utf-8")) == old_stat.st_size

    original_read_bytes = Path.read_bytes
    swapped = False

    def swapping_read_bytes(self: Path) -> bytes:
        nonlocal swapped
        contents = original_read_bytes(self)
        if self == path and not swapped:
            swapped = True
            path.write_text(new_payload, encoding="utf-8")
            os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
        return contents

    monkeypatch.setattr(Path, "read_bytes", swapping_read_bytes)

    assert await repo.get_chat(old_chat.id) is None
    loaded_new = await repo.get_chat(new_chat.id)

    assert loaded_new is not None
    assert loaded_new.id == new_chat.id
    assert loaded_new.session_id == "new"


@pytest.mark.asyncio
async def test_chat_repo_load_result_mutation_does_not_pollute_cache(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.json"
    chat = ChatSpec(session_id="s1", user_id="u1", channel="console")
    _write_chats(path, [chat])

    repo = JsonChatRepository(path)
    loaded = await repo.load()
    loaded.chats[0].session_id = "mutated"

    cached = await repo.get_chat(chat.id)

    assert cached is not None
    assert cached.session_id == "s1"


@pytest.mark.asyncio
async def test_chat_repo_save_input_mutation_does_not_pollute_cache(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.json"
    chat = ChatSpec(session_id="s1", user_id="u1", channel="console")
    chats_file = ChatsFile(version=1, chats=[chat])

    repo = JsonChatRepository(path)
    await repo.save(chats_file)
    chats_file.chats[0].session_id = "mutated"

    cached = await repo.get_chat(chat.id)

    assert cached is not None
    assert cached.session_id == "s1"


@pytest.mark.asyncio
async def test_chat_repo_get_chat_returns_copy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.json"
    chat = ChatSpec(session_id="s1", user_id="u1", channel="console")
    _write_chats(path, [chat])

    repo = JsonChatRepository(path)
    first = await repo.get_chat(chat.id)
    assert first is not None
    first.session_id = "mutated"
    first.meta["client"] = "changed"

    second = await repo.get_chat(chat.id)

    assert second is not None
    assert second.session_id == "s1"
    assert second.meta == {}
