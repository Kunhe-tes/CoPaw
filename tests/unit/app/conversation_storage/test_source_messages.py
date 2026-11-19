# -*- coding: utf-8 -*-
from types import SimpleNamespace

import pytest

from swe.app.conversation_storage.identity import WorkspaceScope

from swe.app.conversation_storage.message_installs import MessageInstall


def test_online_messages_cannot_reuse_another_occurrence_extent():
    with pytest.raises(ValueError, match="archive"):
        MessageInstall("source:11", "memory", "user", source_message_id=11)


def test_source_occurrence_identity_cannot_be_forged():
    from swe.app.conversation_storage.source_messages import _validate_row
    from swe.app.conversation_storage.errors import IntegrityError

    row = {
        "service_unit_key": b"schema-test-service",
        "session_id": 1,
        "layer": "memory",
        "deleted_at": None,
        "current_visible": 1,
        "source_msg_key": b"q",
        "source_occurrence_no": 0,
        "role_key": b"user",
        "kind_key": b"message",
        "turn_id": 3,
        "origin_chat_id": None,
        "context_epoch": 0,
        "task_run_key": None,
    }
    message = MessageInstall(
        "source:11",
        "archive",
        "user",
        source_msg_key="q",
        archive_chat_id=2,
        turn_id=3,
        source_message_id=11,
    )
    row["message_timestamp"] = None
    _validate_row(
        row,
        message,
        SimpleNamespace(
            scope=WorkspaceScope(
                "t",
                "s",
                "a",
                service_unit_id="schema-test-service",
            ),
            session_id=1,
        ),
    )
    with pytest.raises(IntegrityError, match="visible"):
        _validate_row(
            {**row, "current_visible": 0},
            message,
            SimpleNamespace(
                scope=WorkspaceScope(
                    "t",
                    "s",
                    "a",
                    service_unit_id="schema-test-service",
                ),
                session_id=1,
            ),
        )
    with pytest.raises(IntegrityError, match="identity"):
        _validate_row(
            {**row, "source_msg_key": b"other"},
            message,
            SimpleNamespace(
                scope=WorkspaceScope(
                    "t",
                    "s",
                    "a",
                    service_unit_id="schema-test-service",
                ),
                session_id=1,
            ),
        )


async def test_session_revision_change_rejects_archive_commit():
    from unittest.mock import AsyncMock

    from swe.app.conversation_storage.errors import IntegrityError
    from swe.app.conversation_storage.source_messages import SourceMessages

    sources = SourceMessages(session_revision=1)
    db = SimpleNamespace(
        fetch_one=AsyncMock(return_value={"state_revision": 2}),
    )
    scope = WorkspaceScope(
        "t",
        "s",
        "a",
        service_unit_id="schema-test-service",
    )
    with pytest.raises(IntegrityError, match="changed"):
        await sources.revalidate(
            db,
            SimpleNamespace(scope=scope, session_id=1),
        )


async def test_source_publications_lock_older_then_current_in_integer_order():
    from swe.app.conversation_storage.source_messages import SourceMessages
    from unittest.mock import AsyncMock

    from tests.unit.app.conversation_storage.test_reference_queries import (
        ReferenceDatabase,
        SERVICE,
    )

    rows = {
        identity: {
            "service_unit_key": SERVICE,
            "id": identity,
            "state": "committed",
            "gc_state": "live",
            "scope_kind": "workspace",
            "tenant_key": b"t",
            "source_key": b"s",
            "agent_key": b"a",
            "session_id": 1,
            "chat_id": None,
            "turn_id": None,
            "kind": "state",
            "operation_key": str(identity).encode(),
            "relative_path": b"path",
            "byte_length": 100,
        }
        for identity in (1, 2)
    }
    db = ReferenceDatabase(publications=rows)
    db.fetch_one = AsyncMock(return_value={"id": 9})
    sources = SourceMessages(
        rows={11: {"publication_id": 2}, 12: {"publication_id": 1}},
    )
    service = SimpleNamespace(service_unit_key=SERVICE, db=db)
    current, locked = await sources.lock_publications(service, {"id": 9})
    assert current["id"] == 9
    assert locked == rows
    assert db.calls[0][1] == (SERVICE, 1, 2)
    assert db.fetch_one.await_args.args[1] == (9, SERVICE)
