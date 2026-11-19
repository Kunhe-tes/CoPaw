# -*- coding: utf-8 -*-
"""Long lived task history must not turn the per-batch pin bound into a limit."""

import asyncio
import json
import threading
from types import SimpleNamespace

import pytest

from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.conversation_storage.projection_publication import _existing
from swe.app.conversation_storage.projection_references import (
    snapshot_projection,
    ref_key,
)
from swe.app.conversation_storage.retention import RetentionStore
from swe.app.conversation_storage.session_projection import (
    project_state,
    hydrate_state,
)
from tests.unit.app.conversation_storage.test_retention import (
    RetentionDatabase,
)


class HistoryDatabase(RetentionDatabase):
    def __init__(self, count):
        super().__init__()
        template = self.objects[1]
        self.objects.clear()
        self.objects.update(
            {
                i: {
                    **template,
                    "id": i,
                    "session_id": 1,
                    "relative_path": str(i).encode(),
                    "byte_length": 100,
                }
                for i in range(1, count + 1)
            },
        )
        self.session = None

    async def fetch_one(self, query, params=None):
        if "FROM swe_conversation_sessions" in query:
            return self.session
        return await super().fetch_one(query, params)


def history(count):
    db = HistoryDatabase(count)
    state = {
        "task_messages": [
            {"id": str(i), "role": "assistant", "content": str(i)}
            for i in db.objects
        ],
        "future": {"keep": True},
    }

    row = {
        "service_unit_key": b"schema-test-service",
        "tenant_key": b"t",
        "source_key": b"s",
        "agent_key": b"a",
        "session_id": 1,
        "base_state_revision": 0,
    }
    envelope = project_state(
        state,
        operation_key="current",
        resolve_message=lambda layer, body: {
            "publication_id": int(body["id"]),
            "block_name": "message",
            "position": 0,
        },
    ).envelope
    envelope["message_directory"] = [
        {"layer": "task", "body": item["ref"]}
        for item in envelope["lists"][0]["entries"]
    ]
    root_id = count + 1
    db.objects[root_id] = {
        **db.objects[1],
        "id": root_id,
        "operation_key": b"current",
        "relative_path": str(root_id).encode(),
    }
    db.session = {
        "recovery_publication_id": root_id,
        "recovery_offset": 0,
        "recovery_length": 10,
    }

    def read(path, *_args, **_kwargs):
        document = (
            envelope
            if int(path) == root_id
            else state["task_messages"][int(path) - 1]
        )
        return json.dumps(document).encode()

    def inspect(path, *, expected_length):
        return SimpleNamespace(
            relative_path=path,
            byte_length=expected_length,
            blocks={
                "message": SimpleNamespace(offset=0, length=10, kind="task"),
            },
        )

    service = SimpleNamespace(
        db=db,
        bundles=SimpleNamespace(read_extent=read, inspect=inspect),
    )
    request = SimpleNamespace(
        scope=WorkspaceScope(
            "t",
            "s",
            "a",
            service_unit_id="schema-test-service",
        ),
        session_id=1,
    )
    return db, service, row, request, state, envelope


@pytest.mark.parametrize("count", [4096, 4097])
@pytest.mark.parametrize("path", ["publication", "recovery"])
async def test_long_task_history_across_fresh_requests(count, path):
    db, service, row, request, state, envelope = history(count)
    for _ in range(2):
        if path == "publication":
            values = await _existing(service, row)
            assert sum(map(len, values.values())) == count
        else:
            refs = await snapshot_projection(
                service,
                request,
                envelope,
                None,
                current_id=count + 1,
            )
            try:
                assert (
                    hydrate_state(
                        envelope,
                        lambda ref, payloads=refs.payloads: payloads[
                            ref_key(ref)
                        ],
                    )
                    == state
                )
            finally:
                await refs.finish(RetentionStore(db, request.scope))
        assert all(pin["state"] == "released" for pin in db.pins)


@pytest.mark.parametrize("path", ["publication", "recovery"])
@pytest.mark.parametrize("failure", ["pin", "read", "cancel"])
async def test_long_history_failure_releases_every_batch(
    monkeypatch,
    path,
    failure,
):
    db, service, row, request, _, envelope = history(4097)
    original_pin = RetentionStore.pin
    calls = 0

    async def pin(store, ids, *, kind, **kwargs):
        nonlocal calls
        calls += 1
        if failure == "pin" and calls == 2:
            raise RuntimeError("second pin failed")
        return await original_pin(store, ids, kind=kind, **kwargs)

    monkeypatch.setattr(RetentionStore, "pin", pin)
    original = service.bundles.read_extent

    def read(path, *args, **kwargs):
        if int(path) == 4097:
            if failure == "cancel":
                raise asyncio.CancelledError
            if failure == "read":
                raise RuntimeError("last read failed")
        return original(path, *args, **kwargs)

    service.bundles.read_extent = read
    with pytest.raises(
        asyncio.CancelledError if failure == "cancel" else RuntimeError,
    ):
        if path == "publication":
            await _existing(service, row)
        else:
            await snapshot_projection(
                service,
                request,
                envelope,
                None,
                current_id=4098,
            )
    assert not [pin for pin in db.pins if pin["state"] == "active"]


@pytest.mark.parametrize("count", [4095, 4096, 4097])
async def test_projection_commit_installs_all_dependencies(count):
    from swe.app.conversation_storage.source_messages import SourceMessages

    db, service, _, request, _, _ = history(count + 1)
    sources = SourceMessages(
        dependency_publications={
            i: db.objects[i] for i in range(1, count + 1)
        },
    )
    await sources.install_dependencies(service, request, db.objects[count + 1])
    assert [pin["publication_id"] for pin in db.pins] == list(
        range(1, count + 1),
    )
    assert all(
        pin["kind"] == "dependency" and pin["state"] == "active"
        for pin in db.pins
    )


@pytest.mark.parametrize("path", ["publication", "recovery"])
async def test_external_cancel_drains_io_before_releasing_all_batches(path):
    db, service, row, request, _, envelope = history(4097)
    entered, release = threading.Event(), threading.Event()
    original = service.bundles.read_extent

    def blocked(path, *args, **kwargs):
        if int(path) <= 4097:
            entered.set()
            assert release.wait(10)
        return original(path, *args, **kwargs)

    service.bundles.read_extent = blocked
    task = asyncio.create_task(
        (
            _existing(service, row)
            if path == "publication"
            else snapshot_projection(
                service,
                request,
                envelope,
                None,
                current_id=4098,
            )
        ),
    )
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert len([pin for pin in db.pins if pin["state"] == "active"]) == (
            4098 if path == "publication" else 4097
        )
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert all(pin["state"] == "released" for pin in db.pins)


@pytest.mark.parametrize("error", [RuntimeError, asyncio.CancelledError])
async def test_commit_source_cleanup_failure_still_releases_projection_batches(
    tmp_path,
    monkeypatch,
    error,
):
    from unittest.mock import AsyncMock
    from swe.app.conversation_storage import publications
    from swe.app.conversation_storage.bundle import BundleBlock, BundleStore
    from swe.app.conversation_storage.projection_references import (
        ProjectionReferences,
    )
    from swe.app.conversation_storage.retention import ReaderPins
    from tests.unit.app.conversation_storage.test_publications import (
        PublicationDatabase,
        request as publication_request,
    )

    history_db, _, _, request, _, _ = history(4097)
    pins = ReaderPins(RetentionStore(history_db, request.scope))
    await pins.pin(list(history_db.objects))
    refs = ProjectionReferences(batch=pins)
    monkeypatch.setattr(
        publications,
        "snapshot_projection",
        AsyncMock(return_value=refs),
    )

    async def failed_source_cleanup(*_args):
        raise error("source cleanup failed")

    monkeypatch.setattr(
        publications.SourceMessages,
        "finish",
        failed_source_cleanup,
    )
    db = PublicationDatabase()
    db.session["recovery_publication_id"] = None
    store = publications.PublicationStore(
        db,
        BundleStore(tmp_path),
        service_unit_id="schema-test-service",
    )
    operation = publication_request()
    await store.reserve(
        operation,
        publications.CommitPlan(recovery_block="root"),
    )
    await store.write_bundle(
        operation.operation_key,
        [BundleBlock("root", "recovery", b'{"future":true}')],
    )
    with pytest.raises(error):
        await store.commit(operation.operation_key)
    assert all(pin["state"] == "released" for pin in history_db.pins)
