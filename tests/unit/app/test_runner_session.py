# -*- coding: utf-8 -*-
import asyncio
import builtins
import json
import multiprocessing
import threading
import time
from pathlib import Path

import pytest

from swe.app.runner import session as session_module
from swe.app.runner.session import SafeJSONSession
from swe.app.runner.session_lock import SessionLockTimeout


def _write_json_text(path: str, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8")


def _mutate_session_state_in_process(
    save_dir: str,
    session_id: str,
    key: str,
    value: object,
    started_event,
    wait_for_event,
    delay_seconds: float,
) -> None:
    async def _run() -> None:
        session = SafeJSONSession(save_dir=save_dir)

        def _mutate(states: dict[str, object]) -> dict[str, object]:
            states[key] = value
            if started_event is not None:
                started_event.set()
            if delay_seconds:
                time.sleep(delay_seconds)
            return states

        if wait_for_event is not None and not wait_for_event.wait(timeout=5):
            raise TimeoutError("timed out waiting for session mutation")
        await session.mutate_session_state(session_id, _mutate)

    asyncio.run(_run())


class _GuardedReadableFile:
    def __init__(self, file, state: dict[str, bool], operations: list[str]):
        self._file = file
        self._state = state
        self._operations = operations

    def read(self, *args, **kwargs):
        assert self._state["in_worker"], "session read ran outside worker"
        self._operations.append("read")
        return self._file.read(*args, **kwargs)

    def __enter__(self):
        self._file.__enter__()
        return self

    def __exit__(self, *args):
        return self._file.__exit__(*args)

    def __iter__(self):
        return iter(self._file)

    def __getattr__(self, name: str):
        return getattr(self._file, name)


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
async def test_session_file_lock_timeout_maps_to_builtin_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class BusyFileLock:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            raise SessionLockTimeout("busy")

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            pass

    monkeypatch.setattr(session_module, "AsyncSessionFileLock", BusyFileLock)
    session = SafeJSONSession(save_dir=str(tmp_path))

    with pytest.raises(TimeoutError, match="busy"):
        async with session.session_write_lock(
            "shared",
            timeout_seconds=0.01,
        ):
            pass


@pytest.mark.asyncio
async def test_session_load_uses_runtime_state_worker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "session-1.json"
    path.write_text('{"message": "你好"}', encoding="utf-8")
    calls: list[str] = []
    operations: list[str] = []
    state = {"in_worker": False}
    original_open = builtins.open
    original_loads = json.loads

    async def fake_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        assert not state["in_worker"]
        state["in_worker"] = True
        try:
            return func(*args, **kwargs)
        finally:
            state["in_worker"] = False

    def guarded_open(*args, **kwargs):
        # pylint: disable=consider-using-with
        file = original_open(*args, **kwargs)
        if args and str(args[0]) == str(path):
            return _GuardedReadableFile(file, state, operations)
        return file

    def guarded_loads(*args, **kwargs):
        assert state["in_worker"], "json.loads ran outside worker"
        operations.append("parse")
        return original_loads(*args, **kwargs)

    monkeypatch.setattr(
        session_module,
        "run_runtime_state_work",
        fake_worker,
        raising=False,
    )
    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(session_module.json, "loads", guarded_loads)

    session = SafeJSONSession(save_dir=str(tmp_path))

    assert await session.get_session_state_dict("session-1") == {
        "message": "你好",
    }
    assert calls == ["_read_json_state_sync"]
    assert operations == ["read", "parse"]


@pytest.mark.asyncio
async def test_session_save_serializes_inside_runtime_state_worker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class StateModule:
        def state_dict(self) -> dict:
            return {"value": "saved"}

    (tmp_path / "session-2.json").write_text(
        '{"existing": true}',
        encoding="utf-8",
    )
    calls: list[str] = []
    operations: list[str] = []
    state = {"in_worker": False}
    original_loads = json.loads
    original_dumps = json.dumps

    async def fake_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        assert not state["in_worker"]
        state["in_worker"] = True
        try:
            return func(*args, **kwargs)
        finally:
            state["in_worker"] = False

    def guarded_loads(*args, **kwargs):
        assert state["in_worker"], "json.loads ran outside worker"
        operations.append("parse")
        return original_loads(*args, **kwargs)

    def guarded_dumps(*args, **kwargs):
        assert state["in_worker"], "json.dumps ran outside worker"
        operations.append("encode")
        return original_dumps(*args, **kwargs)

    def guarded_write(path: str, content: str) -> None:
        assert state["in_worker"], "_write_json_text ran outside worker"
        operations.append("write")
        _write_json_text(path, content)

    monkeypatch.setattr(
        session_module,
        "run_runtime_state_work",
        fake_worker,
        raising=False,
    )
    monkeypatch.setattr(session_module.json, "loads", guarded_loads)
    monkeypatch.setattr(session_module.json, "dumps", guarded_dumps)
    monkeypatch.setattr(session_module, "_write_json_text", guarded_write)

    session = SafeJSONSession(save_dir=str(tmp_path))

    await session.save_merged_state("session-1", state={"message": "你好"})
    await session.save_session_state("session-2", agent=StateModule())

    assert calls == [
        "_write_json_state_sync",
        "_read_existing_state_for_save_sync",
        "_write_json_state_sync",
    ]
    assert operations == ["encode", "write", "parse", "encode", "write"]
    assert original_loads((tmp_path / "session-1.json").read_text()) == {
        "message": "你好",
    }
    assert original_loads((tmp_path / "session-2.json").read_text()) == {
        "existing": True,
        "agent": {"value": "saved"},
    }


@pytest.mark.asyncio
async def test_mutate_session_state_uses_runtime_state_worker_for_json_io(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "session-1.json"
    path.write_text('{"existing": true}', encoding="utf-8")
    calls: list[str] = []
    operations: list[str] = []
    state = {"in_worker": False}
    original_open = builtins.open
    original_loads = json.loads
    original_dumps = json.dumps

    async def fake_worker(func, /, *args, **kwargs):
        calls.append(func.__name__)
        assert not state["in_worker"]
        state["in_worker"] = True
        try:
            return func(*args, **kwargs)
        finally:
            state["in_worker"] = False

    def guarded_open(*args, **kwargs):
        # pylint: disable=consider-using-with
        file = original_open(*args, **kwargs)
        if args and str(args[0]) == str(path):
            return _GuardedReadableFile(file, state, operations)
        return file

    def guarded_loads(*args, **kwargs):
        assert state["in_worker"], "json.loads ran outside worker"
        operations.append("parse")
        return original_loads(*args, **kwargs)

    def guarded_dumps(*args, **kwargs):
        assert state["in_worker"], "json.dumps ran outside worker"
        operations.append("encode")
        return original_dumps(*args, **kwargs)

    def guarded_write(write_path: str, content: str) -> None:
        assert state["in_worker"], "_write_json_text ran outside worker"
        operations.append("write")
        _write_json_text(write_path, content)

    def mutate(states: dict[str, object]) -> None:
        assert not state["in_worker"], "mutator should stay on event loop"
        states["mutated"] = True

    monkeypatch.setattr(
        session_module,
        "run_runtime_state_work",
        fake_worker,
        raising=False,
    )
    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(session_module.json, "loads", guarded_loads)
    monkeypatch.setattr(session_module.json, "dumps", guarded_dumps)
    monkeypatch.setattr(session_module, "_write_json_text", guarded_write)

    session = SafeJSONSession(save_dir=str(tmp_path))

    assert await session.mutate_session_state("session-1", mutate) == {
        "existing": True,
        "mutated": True,
    }
    assert calls == ["_read_json_state_sync", "_write_json_state_sync"]
    assert operations == ["read", "parse", "encode", "write"]


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
    assert json.loads(
        (tmp_path / "session-1.json").read_text(encoding="utf-8"),
    ) == {
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


def test_cross_process_key_updates_preserve_both_values(
    tmp_path: Path,
) -> None:
    session_path = tmp_path / "shared.json"
    session_path.write_text("{}", encoding="utf-8")
    context = multiprocessing.get_context("spawn")
    first_started = context.Event()

    first_process = context.Process(
        target=_mutate_session_state_in_process,
        args=(
            str(tmp_path),
            "shared",
            "first",
            1,
            first_started,
            None,
            0.4,
        ),
    )
    second_process = context.Process(
        target=_mutate_session_state_in_process,
        args=(
            str(tmp_path),
            "shared",
            "second",
            2,
            None,
            first_started,
            0,
        ),
    )

    first_process.start()
    second_process.start()
    first_process.join(timeout=10)
    second_process.join(timeout=10)

    if first_process.is_alive():
        first_process.terminate()
        first_process.join(timeout=2)
    if second_process.is_alive():
        second_process.terminate()
        second_process.join(timeout=2)

    assert first_process.exitcode == 0
    assert second_process.exitcode == 0
    assert json.loads(session_path.read_text()) == {
        "first": 1,
        "second": 2,
    }


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


@pytest.mark.asyncio
async def test_get_session_state_dict_avoids_truncated_json_during_write(
    monkeypatch,
    tmp_path: Path,
) -> None:
    session_path = tmp_path / "shared.json"
    session_path.write_text('{"version": "old"}', encoding="utf-8")
    write_truncated = threading.Event()
    allow_write = threading.Event()

    def truncating_write(path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8") as file:
            file.write("")
            file.flush()
            write_truncated.set()
            assert allow_write.wait(timeout=2)
            file.write(content)
            file.flush()

    monkeypatch.setattr(
        session_module,
        "_write_json_text",
        truncating_write,
        raising=False,
    )
    session = SafeJSONSession(save_dir=str(tmp_path))

    save_task = asyncio.create_task(
        session.save_merged_state("shared", state={"version": "new"}),
    )
    assert await asyncio.to_thread(write_truncated.wait, 1)

    read_task = asyncio.create_task(
        session.get_session_state_dict("shared"),
    )
    await asyncio.sleep(0.05)
    allow_write.set()

    await save_task
    state = await read_task

    assert state in ({"version": "old"}, {"version": "new"})


@pytest.mark.asyncio
async def test_load_session_state_avoids_truncated_json_during_write(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class StateModule:
        def __init__(self) -> None:
            self.loaded_state: dict | None = None

        def load_state_dict(self, state: dict) -> None:
            self.loaded_state = state

    session_path = tmp_path / "shared.json"
    session_path.write_text(
        '{"agent": {"version": "old"}}',
        encoding="utf-8",
    )
    write_truncated = threading.Event()
    allow_write = threading.Event()

    def truncating_write(path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8") as file:
            file.write("")
            file.flush()
            write_truncated.set()
            assert allow_write.wait(timeout=2)
            file.write(content)
            file.flush()

    monkeypatch.setattr(
        session_module,
        "_write_json_text",
        truncating_write,
        raising=False,
    )
    session = SafeJSONSession(save_dir=str(tmp_path))
    state_module = StateModule()

    save_task = asyncio.create_task(
        session.save_merged_state(
            "shared",
            state={"agent": {"version": "new"}},
        ),
    )
    assert await asyncio.to_thread(write_truncated.wait, 1)

    load_task = asyncio.create_task(
        session.load_session_state("shared", agent=state_module),
    )
    await asyncio.sleep(0.05)
    allow_write.set()

    await save_task
    await load_task

    assert state_module.loaded_state in (
        {"version": "old"},
        {"version": "new"},
    )
