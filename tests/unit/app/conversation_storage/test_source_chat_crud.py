# -*- coding: utf-8 -*-
"""Repository CRUD keeps equal external keys inside their trusted source."""

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock

from swe.app.conversation_storage.bundle import BundleStore
from swe.app.conversation_storage.chat_repository import MySQLChatRepository
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.app.runner.models import ChatSpec


class SourceDatabase:
    max_allowed_packet = 1024 * 1024
    _in_transaction = True

    def __init__(self):
        self.sessions, self.chats, self.queries = {}, {}, []

    @asynccontextmanager
    async def transaction(self):
        yield self

    @asynccontextmanager
    async def acquire(self):
        yield self

    async def insert(self, query, params):
        assert "INSERT INTO swe_conversation_sessions" in query
        self.queries.append((query, params))
        if params not in self.sessions:
            fields = (
                "service_unit_key",
                "tenant_key",
                "source_key",
                "agent_key",
                "user_key",
                "channel_key",
                "external_session_key",
            )
            self.sessions[params] = {
                **dict(zip(fields, params)),
                "id": len(self.sessions) + 1,
                "active_turn_id": None,
            }
        return self.sessions[params]["id"]

    async def fetch_one(self, query, params):
        self.queries.append((query, params))
        if "swe_conversation_sessions WHERE id=%s" in query:
            return next(
                (
                    s
                    for s in self.sessions.values()
                    if (s["id"], s["service_unit_key"]) == params
                ),
                None,
            )
        if "swe_conversation_sessions WHERE " in query:
            return self.sessions.get(params)
        rows = await self.fetch_all(query, params)
        return rows[0] if rows else None

    async def fetch_all(self, query, params):
        self.queries.append((query, params))
        rows = list(self.chats.values())
        if "source_key=%s" in query:
            assert all(
                name + "=%s" in query
                for name in ("service_unit_key", "tenant_key", "agent_key")
            )
            rows = [
                r
                for r in rows
                if tuple(
                    r[f]
                    for f in (
                        "service_unit_key",
                        "tenant_key",
                        "source_key",
                        "agent_key",
                    )
                )
                == params[:4]
            ]
            if "external_chat_key=%s" in query:
                rows = [r for r in rows if r["external_chat_key"] == params[4]]
            elif "external_chat_key IN (" in query:
                rows = [
                    r for r in rows if r["external_chat_key"] in params[4:]
                ]
            elif "external_session_key=%s" in query:
                rows = [
                    r
                    for r in rows
                    if (
                        r["user_key"],
                        r["channel_key"],
                        r["external_session_key"],
                    )
                    == params[4:]
                ]
            elif "id IN (" in query:
                rows = [r for r in rows if r["id"] in params[4:]]
        elif "id IN (" in query:
            rows = [
                r
                for r in rows
                if r["service_unit_key"] == params[0] and r["id"] in params[1:]
            ]
        else:
            raise AssertionError(query)
        if "deleted_at IS NULL" in query:
            rows = [r for r in rows if r["deleted_at"] is None]
        return rows

    async def execute(self, query, params):
        self.queries.append((query, params))
        if "SET title=%s" in query:
            title, identity, service, revision = params
            row = self.chats[identity]
            assert (row["service_unit_key"], row["metadata_revision"]) == (
                service,
                revision,
            )
            row["title"] = title
            row["metadata_revision"] += 1
            return 1
        assert "SET deleted_at=" in query
        rows = await self.fetch_all(query, params)
        for row in rows:
            row["deleted_at"] = datetime(2026, 11, 16)
        return len(rows)


async def test_same_tenant_source_crud_preserves_equal_chat_and_session_keys(
    monkeypatch,
    tmp_path,
):
    import swe.app.conversation_storage.chat_repository as module

    monkeypatch.setattr(
        module,
        "runtime_identity",
        AsyncMock(return_value=None),
    )
    db = SourceDatabase()
    repos = {}
    for source in ("A", "B"):
        repo = MySQLChatRepository(
            db,
            WorkspaceScope("alice", source, "agent", service_unit_id="svc"),
            BundleStore(tmp_path),
        )
        repo.retentions.assert_writes_allowed = AsyncMock()

        async def publish(spec, session, row, *, scope=repo.scope):
            if row is not None:
                assert WorkspaceScope.from_row(row) == scope
                row["title"] = spec.name
                return
            identity = len(db.chats) + 1
            db.chats[identity] = {
                **session,
                "id": identity,
                "session_id": session["id"],
                "external_chat_key": spec.id.encode(),
                "registry_order": identity,
                "title": spec.name,
                "metadata_text": "{}",
                "metadata_revision": 0,
                "expert_binding_revision": 0,
                "expert_id": None,
                "content_meta_publication_id": None,
                "content_meta_offset": None,
                "content_meta_length": None,
                "created_at": datetime(2026, 11, 16),
                "updated_at": datetime(2026, 11, 16),
                "status": "idle",
                "deleted_at": None,
            }

        repo._publish_metadata = publish
        repos[source] = repo
        for key in ("same-chat", "second-chat"):
            await repo.upsert_chat(
                ChatSpec(
                    id=key,
                    session_id="same-session",
                    user_id="user",
                    channel="console",
                    name=source,
                ),
            )
    assert len(db.sessions) == 2 and len(db.chats) == 4
    for source, repo in repos.items():
        assert (await repo.get_chat("same-chat")).name == source
        assert (
            await repo.get_chat_by_id("same-session", "user", "console")
        ).name == source
        assert {c.name for c in await repo.list_chats()} == {source}
    assert await repos["A"].update_title(
        "same-chat",
        "A changed",
        expected_revision=0,
    )
    assert (await repos["B"].get_chat("same-chat")).name == "B"
    assert await repos["A"].delete_chats(["same-chat"])
    assert await repos["A"].get_chat("same-chat") is None
    assert (await repos["B"].get_chat("same-chat")).name == "B"
    assert await repos["B"].delete_chats(["same-chat", "second-chat"])
    assert await repos["B"].list_chats() == []
    assert [c.id for c in await repos["A"].list_chats()] == ["second-chat"]
