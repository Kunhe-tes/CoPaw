# -*- coding: utf-8 -*-
"""Verify NAS message batches and bound parallel auxiliary reads."""

import asyncio
import threading
from types import SimpleNamespace

import pytest

from swe.app.conversation_storage.migration import verify
from swe.app.conversation_storage.migration.parallel import MigrationIO
from swe.app.conversation_storage.migration.verify_parallel import (
    verify_workspace_messages,
)


async def test_workspace_message_checks_overlap_with_bounded_nas_workers(
    monkeypatch,
):
    owner = asyncio.current_task()
    barrier = threading.Barrier(2)
    checked = []
    health_checks = []

    async def health_check():
        assert asyncio.current_task() is owner
        health_checks.append(True)

    database = object()

    async def session_check(
        evidence,
        _bundles,
        _manifest,
        _workspace,
        session,
        sid,
        *,
        io,
        io_workers,
    ):
        assert asyncio.current_task() is not owner
        assert evidence is database
        assert sid in (1, 2)
        await io.call(barrier.wait, timeout=5)
        checked.append(session["position"])

    monkeypatch.setattr(verify, "_verify_session_messages", session_check)
    manifest = SimpleNamespace(
        data={
            "assignments": {
                "session": {
                    "session-0": {"target_id": 1},
                    "session-1": {"target_id": 2},
                },
            },
        },
    )
    inventory = {
        "workspaces": [
            {
                "scope": ["SERVICE", "tenant", "source", str(index)],
                "sessions": [{"position": "session-" + str(index)}],
                "chats": [],
            }
            for index in range(2)
        ],
    }
    report = {"blockers": []}
    async with MigrationIO(2) as io:
        await verify_workspace_messages(
            database,
            {"SERVICE": object()},
            manifest,
            inventory,
            report,
            io=io,
            workers=2,
            health_check=health_check,
        )
    assert sorted(checked) == ["session-0", "session-1"]
    assert report["blockers"] == []
    assert health_checks


async def test_session_message_batch_offsets_are_numeric(tmp_path):
    from agentscope.message import Msg
    from swe.app.conversation_storage.bundle import BundleBlock, BundleStore
    from swe.app.conversation_storage.identity import WorkspaceScope
    from swe.app.conversation_storage.message_bundle import (
        encode_message_bodies,
        encode_message_directory,
    )

    bundles = BundleStore(tmp_path)
    scope = WorkspaceScope("tenant", "source", "agent", service_unit_id="svc")
    assignments, rows, messages = {}, {}, []
    for start in range(11):
        body = Msg("assistant", f"occurrence {start}", "assistant").to_dict()
        messages.append(body)
        entry = {
            "sequence": start + 1,
            "raw_id": body["id"],
            "layer": "memory",
            "source_occurrence": start,
            "visible": True,
            "body": {
                "publication_id": "self",
                "block_name": "message_bodies",
                "position": 0,
            },
        }
        index = bundles.publish(
            f"{start:064x}",
            [
                BundleBlock(
                    "message_directory",
                    "message_directory",
                    encode_message_directory([entry]),
                ),
                BundleBlock(
                    "message_bodies",
                    "message_bodies",
                    encode_message_bodies([body]),
                ),
            ],
            scope=scope,
        )
        rows[start + 1] = {
            **scope.fields,
            "session_id": 1,
            "relative_path": index.relative_path,
            "byte_length": index.byte_length,
        }
        assignments[f"session/messages:{start}"] = {"target_id": start + 1}

    class Database:
        async def fetch_one(self, _query, params):
            return rows[params[0]]

    manifest = SimpleNamespace(
        data={"assignments": {"publication": assignments}},
    )
    session = {
        "position": "session",
        "identity": [
            "svc",
            "tenant",
            "source",
            "agent",
            "user",
            "console",
            "s",
        ],
        "legacy": {"state": {"agent": {"memory": {"content": messages}}}},
    }
    await verify._verify_session_messages(
        Database(),
        bundles,
        manifest,
        {"chats": [], "scope": list(scope.values)},
        session,
        1,
    )


async def test_auxiliary_epoch_reads_overlap_and_failure_is_reported(
    monkeypatch,
):
    from swe.app.conversation_storage.migration.verify_parallel import (
        verify_auxiliary_bodies,
    )

    owner = asyncio.current_task()
    barrier = threading.Barrier(2)

    class Database:
        async def fetch_one(self, _query, params):
            assert asyncio.current_task() is owner
            return {"id": params[0]}

    async def epoch_check(evidence, _bundles, _manifest, chat, _scope, *, io):
        assert asyncio.current_task() is not owner
        assert await evidence.fetch_one("detached", (1,)) == {"id": 1}
        await io.call(barrier.wait, timeout=5)
        if chat["position"] == "chat-1":
            raise ValueError("bad epoch")

    monkeypatch.setattr(verify, "_verify_epochs", epoch_check)
    manifest = SimpleNamespace(
        data={
            "assignments": {
                "publication": {
                    "chat-0/epoch:0": {"target_id": 1},
                    "chat-1/epoch:0": {"target_id": 1},
                },
            },
        },
    )
    inventory = {
        "workspaces": [
            {
                "scope": ["SERVICE", "tenant", "source", "agent"],
                "chats": [
                    {
                        "position": "chat-" + str(index),
                        "archive": {"epochs": [{"epoch": 0}]},
                    }
                    for index in range(2)
                ],
            },
        ],
        "files": [],
        "shares": [],
    }
    report = {"checked": [], "blockers": []}
    async with MigrationIO(2) as io:
        await verify_auxiliary_bodies(
            Database(),
            {"SERVICE": object()},
            manifest,
            inventory,
            report,
            io=io,
            workers=2,
        )
    assert report["blockers"] == [
        {"position": "chat-1", "detail": "bad epoch"},
    ]


@pytest.mark.parametrize("dispatch", ("omit", "duplicate"))
async def test_auxiliary_verification_rejects_incomplete_dispatch(
    monkeypatch,
    dispatch,
):
    from swe.app.conversation_storage.migration import verify_parallel

    original = verify_parallel.MigrationCoordinator.run

    async def damaged_run(self, jobs, check):
        jobs = list(jobs)
        selected = jobs[:-1] if dispatch == "omit" else [jobs[0], jobs[0]]
        return await original(self, selected, check)

    class Database:
        async def fetch_one(self, _query, _params):
            return None

    monkeypatch.setattr(
        verify_parallel.MigrationCoordinator,
        "run",
        damaged_run,
    )
    inventory = {
        "workspaces": [],
        "files": [],
        "shares": [
            {
                "position": "share-" + str(index),
                "record": {"token": "token-" + str(index)},
                "service_unit_id": "SERVICE",
            }
            for index in range(2)
        ],
    }
    async with MigrationIO(2) as io:
        with pytest.raises(ValueError, match="coverage differs"):
            await verify_parallel.verify_auxiliary_bodies(
                Database(),
                {},
                SimpleNamespace(data={}),
                inventory,
                {"checked": [], "blockers": []},
                io=io,
                workers=2,
            )
