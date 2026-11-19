# -*- coding: utf-8 -*-
"""Cross-store business population API contract on disposable MySQL."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI, Request
import pytest

from swe.app.conversation_storage.history import HistoryStore
from swe.app.conversation_storage.identity import WorkspaceScope
from swe.config.config import AgentProfileConfig
from swe.observability.query import router as observability_router
from swe.observability.store import ObservabilityStore
from tests.integrated.conversation_storage.conftest import apply_sql_script
from tests.integrated.conversation_storage.test_schema import (
    insert_chat,
    insert_publication,
    insert_row,
    insert_session,
)

_OBSERVABILITY_DDL = (
    Path(__file__).parents[3]
    / ".scratch"
    / "agent-observability"
    / "schema-draft.sql"
)


async def _insert_admitted_turn(
    database,
    *,
    source_key: bytes,
    session_key: bytes,
    chat_key: bytes,
    question_key: bytes,
    admitted_at: datetime,
) -> None:
    session_id = await insert_session(
        database,
        service_unit_key=b"schema-test-service",
        tenant_key=b"tenant",
        source_key=source_key,
        agent_key=b"agent",
        external_session_key=session_key,
    )
    chat_id = await insert_chat(
        database,
        session_id,
        chat_key,
        service_unit_key=b"schema-test-service",
        tenant_key=b"tenant",
        source_key=source_key,
        agent_key=b"agent",
    )
    admission_id = await insert_publication(
        database,
        operation=b"population-" + question_key,
        service_unit_key=b"schema-test-service",
        tenant_key=b"tenant",
        source_key=source_key,
        agent_key=b"agent",
        session_id=session_id,
        chat_id=chat_id,
        state="committed",
    )
    await insert_row(
        database,
        "swe_conversation_turns",
        {
            "service_unit_key": b"schema-test-service",
            "chat_id": chat_id,
            "session_id": session_id,
            "question_msg_key": question_key,
            "turn_order": 1,
            "context_epoch": 0,
            "generation": 1,
            "state": "completed",
            "history_status": "completed",
            "admission_publication_id": admission_id,
            "admitted_at": admitted_at,
            "terminal_at": admitted_at,
        },
    )


async def _seed_population_subagents(run_store_dir):
    from swe.app.subagents import (
        DelegationSpec,
        PerRunSubAgentRunStore,
        PermissionPolicy,
        SubAgentDefinition,
    )

    store = PerRunSubAgentRunStore(run_store_dir)
    definition = SubAgentDefinition(
        name="population-researcher",
        description="Population integration test",
        instruction="Inspect a test population.",
    )
    records = []
    for chat_id in ("chat-real", "", "hidden-chat"):
        record = await store.create(
            DelegationSpec(
                parent_chat_id=chat_id,
                parent_thread_id="session-real",
                name=definition.name,
                objective="Inspect population coverage.",
            ),
            definition,
            PermissionPolicy.readonly(),
        )
        records.append(record)
    await store.mark_running(records[1].run_id, worker_pid=123)


@pytest.mark.asyncio
async def test_business_population_reads_admitted_turn_from_mysql(
    conversation_test_database,
    tmp_path,
    monkeypatch,
):
    database = conversation_test_database
    await apply_sql_script(database, _OBSERVABILITY_DDL)

    scope = WorkspaceScope(
        "tenant",
        "source",
        "agent",
        service_unit_id="schema-test-service",
    )
    bundles_dir = tmp_path / "bundles"
    from swe.app.conversation_storage.bundle import BundleStore

    history = HistoryStore(
        database,
        scope,
        BundleStore(bundles_dir),
        cursor_secret=b"business-population-mysql-test",
    )
    admitted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await _insert_admitted_turn(
        database,
        source_key=b"source",
        session_key=b"session-real",
        chat_key=b"chat-real",
        question_key=b"question-real",
        admitted_at=admitted_at,
    )
    await _seed_population_subagents(tmp_path / "subagents")
    await _insert_admitted_turn(
        database,
        source_key=b"foreign-source",
        session_key=b"foreign-session",
        chat_key=b"foreign-chat",
        question_key=b"foreign-question",
        admitted_at=admitted_at,
    )

    workspace = SimpleNamespace(
        agent_id="agent",
        tenant_id="tenant",
        workspace_dir=tmp_path,
        config=AgentProfileConfig(
            id="agent",
            name="Business Population Integration Agent",
            workspace_dir=str(tmp_path),
        ),
        subagent_run_store_dir=tmp_path / "subagents",
        conversation_storage=SimpleNamespace(history=history),
    )
    monkeypatch.setattr(
        "swe.app.runner.api.get_workspace",
        AsyncMock(return_value=workspace),
    )
    api = FastAPI()
    api.state.agent_observability_store = ObservabilityStore(database)

    @api.middleware("http")
    async def bind_test_source(request: Request, call_next):
        request.state.source_id = request.headers.get("X-Source-Id")
        return await call_next(request)

    api.include_router(observability_router)
    start = admitted_at.replace(tzinfo=timezone.utc) - timedelta(minutes=1)
    end = admitted_at.replace(tzinfo=timezone.utc) + timedelta(minutes=1)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api),
        base_url="http://agentobs.test",
    ) as client:
        response = await client.get(
            "/agent-observability/business-population",
            params={"start": start.isoformat(), "end": end.isoformat()},
            headers={"X-User-Role": "manager", "X-Source-Id": "source"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["business"]["turn_count"] == 1
    assert body["business"]["by_turn_status"]["completed"] == 1
    assert body["business"]["not_collected_count"] == 1
    assert body["runs"]["settled_count"] == 0
    assert body["subagents"]["count"] == 2
    assert body["subagents"]["by_status"] == {"pending": 1, "running": 1}
    assert body["subagents"]["unresolved_count"] == 1
    assert body["population_source"]["business"] == (
        "current_workspace_admitted_turns"
    )
    assert await history.business_visible_chat_sessions() == [
        {"chat_id": b"chat-real", "session_id": b"session-real"},
    ]
