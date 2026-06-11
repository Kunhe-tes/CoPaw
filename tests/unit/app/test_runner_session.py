# -*- coding: utf-8 -*-
import asyncio
import json
import threading
from pathlib import Path

import pytest

from swe.app.runner import session as session_module
from swe.app.runner.session import SafeJSONSession


def _write_json_text(path: str, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8")


def test_session_write_locks_are_scoped_to_event_loop_and_normalized_path(
    tmp_path: Path,
) -> None:
    async def get_locks() -> tuple[asyncio.Lock, asyncio.Lock]:
        direct_path = str(tmp_path / "session.json")
        equivalent_path = str(tmp_path / "nested" / ".." / "session.json")
        return (
            session_module._get_session_write_lock(direct_path),
            session_module._get_session_write_lock(equivalent_path),
        )

    first_loop_locks = asyncio.run(get_locks())
    second_loop_locks = asyncio.run(get_locks())

    assert first_loop_locks[0] is first_loop_locks[1]
    assert second_loop_locks[0] is second_loop_locks[1]
    assert first_loop_locks[0] is not second_loop_locks[0]


@pytest.mark.asyncio
async def test_session_write_runs_off_event_loop_thread(
    monkeypatch,
    tmp_path: Path,
) -> None:
    write_started = threading.Event()
    allow_write = threading.Event()
    write_thread_ids: list[int] = []
    event_loop_thread_id = threading.get_ident()

    def slow_write(path: str, content: str) -> None:
        write_thread_ids.append(threading.get_ident())
        write_started.set()
        assert allow_write.wait(timeout=2)
        _write_json_text(path, content)

    monkeypatch.setattr(
        session_module,
        "_write_json_text",
        slow_write,
        raising=False,
    )
    session = SafeJSONSession(save_dir=str(tmp_path))

    save_task = asyncio.create_task(
        session.save_merged_state("session-1", state={"message": "你好"}),
    )

    assert await asyncio.to_thread(write_started.wait, 1)
    assert not save_task.done()
    assert write_thread_ids == [write_thread_ids[0]]
    assert write_thread_ids[0] != event_loop_thread_id

    allow_write.set()
    await save_task
    assert json.loads((tmp_path / "session-1.json").read_text()) == {
        "message": "你好",
    }


@pytest.mark.asyncio
async def test_same_path_writes_serialize_across_session_objects(
    monkeypatch,
    tmp_path: Path,
) -> None:
    first_write_started = threading.Event()
    allow_first_write = threading.Event()
    calls: list[str] = []
    calls_guard = threading.Lock()

    def controlled_write(path: str, content: str) -> None:
        with calls_guard:
            calls.append(content)
            call_number = len(calls)
        if call_number == 1:
            first_write_started.set()
            assert allow_first_write.wait(timeout=2)
        _write_json_text(path, content)

    monkeypatch.setattr(
        session_module,
        "_write_json_text",
        controlled_write,
        raising=False,
    )
    first_session = SafeJSONSession(save_dir=str(tmp_path))
    second_session = SafeJSONSession(save_dir=str(tmp_path))

    first_task = asyncio.create_task(
        first_session.save_merged_state("shared", state={"writer": "first"}),
    )
    assert await asyncio.to_thread(first_write_started.wait, 1)
    second_task = asyncio.create_task(
        second_session.save_merged_state("shared", state={"writer": "second"}),
    )
    await asyncio.sleep(0.05)

    assert len(calls) == 1

    allow_first_write.set()
    await asyncio.gather(first_task, second_task)
    assert json.loads((tmp_path / "shared.json").read_text()) == {
        "writer": "second",
    }


@pytest.mark.asyncio
async def test_different_path_writes_can_overlap(
    monkeypatch,
    tmp_path: Path,
) -> None:
    both_writes_started = threading.Event()
    allow_writes = threading.Event()
    active_writes = 0
    maximum_active_writes = 0
    active_guard = threading.Lock()

    def controlled_write(path: str, content: str) -> None:
        nonlocal active_writes, maximum_active_writes
        with active_guard:
            active_writes += 1
            maximum_active_writes = max(maximum_active_writes, active_writes)
            if active_writes == 2:
                both_writes_started.set()
        assert allow_writes.wait(timeout=2)
        _write_json_text(path, content)
        with active_guard:
            active_writes -= 1

    monkeypatch.setattr(
        session_module,
        "_write_json_text",
        controlled_write,
        raising=False,
    )
    session = SafeJSONSession(save_dir=str(tmp_path))

    tasks = [
        asyncio.create_task(
            session.save_merged_state("first", state={"path": "first"}),
        ),
        asyncio.create_task(
            session.save_merged_state("second", state={"path": "second"}),
        ),
    ]

    assert await asyncio.to_thread(both_writes_started.wait, 1)
    allow_writes.set()
    await asyncio.gather(*tasks)
    assert maximum_active_writes == 2


@pytest.mark.asyncio
async def test_concurrent_key_updates_preserve_both_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    session_path = tmp_path / "shared.json"
    session_path.write_text("{}", encoding="utf-8")
    first_write_started = threading.Event()
    allow_first_write = threading.Event()
    call_count = 0
    call_guard = threading.Lock()

    def controlled_write(path: str, content: str) -> None:
        nonlocal call_count
        with call_guard:
            call_count += 1
            call_number = call_count
        if call_number == 1:
            first_write_started.set()
            assert allow_first_write.wait(timeout=2)
        _write_json_text(path, content)

    monkeypatch.setattr(
        session_module,
        "_write_json_text",
        controlled_write,
        raising=False,
    )
    session = SafeJSONSession(save_dir=str(tmp_path))

    first_task = asyncio.create_task(
        session.update_session_state("shared", "first", 1),
    )
    assert await asyncio.to_thread(first_write_started.wait, 1)
    second_task = asyncio.create_task(
        session.update_session_state("shared", "second", 2),
    )
    await asyncio.sleep(0.05)
    allow_first_write.set()

    await asyncio.gather(first_task, second_task)
    assert json.loads(session_path.read_text()) == {"first": 1, "second": 2}


@pytest.mark.asyncio
async def test_state_module_save_preserves_concurrent_key_update(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class StateModule:
        def state_dict(self) -> dict:
            return {"value": "saved"}

    session_path = tmp_path / "shared.json"
    session_path.write_text("{}", encoding="utf-8")
    first_write_started = threading.Event()
    allow_first_write = threading.Event()
    call_count = 0
    call_guard = threading.Lock()

    def controlled_write(path: str, content: str) -> None:
        nonlocal call_count
        with call_guard:
            call_count += 1
            call_number = call_count
        if call_number == 1:
            first_write_started.set()
            assert allow_first_write.wait(timeout=2)
        _write_json_text(path, content)

    monkeypatch.setattr(
        session_module,
        "_write_json_text",
        controlled_write,
    )
    session = SafeJSONSession(save_dir=str(tmp_path))

    state_save_task = asyncio.create_task(
        session.save_session_state("shared", agent=StateModule()),
    )
    assert await asyncio.to_thread(first_write_started.wait, 1)
    update_task = asyncio.create_task(
        session.update_session_state("shared", "message", "preserved"),
    )
    await asyncio.sleep(0.05)
    allow_first_write.set()

    await asyncio.gather(state_save_task, update_task)
    assert json.loads(session_path.read_text()) == {
        "agent": {"value": "saved"},
        "message": "preserved",
    }


@pytest.mark.asyncio
async def test_skill_snapshot_save_preserves_concurrent_state_update(
    monkeypatch,
    tmp_path: Path,
) -> None:
    session_path = tmp_path / "shared.json"
    session_path.write_text("{}", encoding="utf-8")
    first_write_started = threading.Event()
    allow_first_write = threading.Event()
    call_count = 0
    call_guard = threading.Lock()

    def controlled_write(path: str, content: str) -> None:
        nonlocal call_count
        with call_guard:
            call_count += 1
            call_number = call_count
        if call_number == 1:
            first_write_started.set()
            assert allow_first_write.wait(timeout=2)
        _write_json_text(path, content)

    monkeypatch.setattr(
        session_module,
        "_write_json_text",
        controlled_write,
        raising=False,
    )
    session = SafeJSONSession(save_dir=str(tmp_path))

    update_task = asyncio.create_task(
        session.update_session_state("shared", "message", "preserved"),
    )
    assert await asyncio.to_thread(first_write_started.wait, 1)
    snapshot_task = asyncio.create_task(
        session.save_session_skill_snapshot(
            "shared",
            snapshot={"xlsx": {"freshness_token": 1}},
        ),
    )
    await asyncio.sleep(0.05)
    allow_first_write.set()

    await asyncio.gather(update_task, snapshot_task)
    state = json.loads(session_path.read_text())
    assert state["message"] == "preserved"
    assert state["session_skill_snapshot"] == {
        "xlsx": {"freshness_token": 1},
    }
