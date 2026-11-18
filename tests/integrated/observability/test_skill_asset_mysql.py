# -*- coding: utf-8 -*-
"""Skill asset provenance contract on MySQL."""

from __future__ import annotations

from io import StringIO
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
from fastapi import FastAPI
import pytest

from swe.agents.skill_invocation_detector import SkillInvocationDetector
from swe.agents.skills_manager import _build_signature
from swe.database import DatabaseConnection
from swe.observability import Observability, Scope, bind_context
from swe.observability.config import EmitterConfig
from swe.observability.emitter import JsonlEmitter
from swe.observability.projector import InboxProjector
from swe.observability.query import router as observability_router
from swe.observability.store import ObservabilityStore
from tests.integrated.observability.test_mysql_pipeline import _test_db_config

pytestmark = pytest.mark.skipif(
    not os.getenv("SWE_AGENTOBS_TEST_DB_HOST"),
    reason="set SWE_AGENTOBS_TEST_DB_HOST to a disposable MySQL *_test database",
)


@pytest.mark.asyncio
async def test_skill_snapshot_asset_reaches_authorized_mysql_api(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv(
        "SWE_AGENTOBS_CURSOR_SECRET",
        "integration-cursor-secret-at-least-32",
    )
    skill_dir = tmp_path / "research"
    skill_dir.mkdir()
    skill_body = "SKILL_BODY_MUST_NOT_BE_RECORDED"
    (skill_dir / "SKILL.md").write_text(skill_body, encoding="utf-8")
    signature = _build_signature(skill_dir)

    sink = StringIO()
    emitter = JsonlEmitter(EmitterConfig(), stream=sink)
    monkeypatch.setattr(
        "swe.observability.instrumentation.default_emitter",
        lambda: emitter,
    )
    observer = Observability(emitter)
    context = observer.admit_run(
        scope=Scope("swe", "agentobs-integration", "user-a", "default"),
        enabled=True,
    )
    detector = SkillInvocationDetector(
        context_manager=SimpleNamespace(record_tool_call=Mock()),
        skill_signatures={"research": signature},
    )
    detector._ensure_skill_active = AsyncMock()
    with bind_context(context):
        activated = await detector._activate_and_record_skill(
            "research",
            1.0,
            "read_file",
            None,
        )
    assert activated == ("research", {"research": 1.0})
    assert emitter.close(timeout=1) == 0

    payload = sink.getvalue()
    assert skill_body not in payload
    records = [json.loads(line) for line in payload.splitlines()]
    skill_events = [
        item
        for item in records
        if item["event_name"] == "asset.used"
        and item.get("asset", {}).get("asset_type") == "skill"
    ]
    assert len(skill_events) == 1
    assert skill_events[0]["asset"] == {
        "asset_type": "skill",
        "asset_id": "research",
        "asset_source": "runtime_snapshot",
        "asset_digest": signature,
    }

    connection = DatabaseConnection(_test_db_config())
    await connection.connect()
    try:
        store = ObservabilityStore(connection)
        assert (await store.readiness())["ready"]
        async with connection.transaction() as session:
            for record in records:
                await session.insert(
                    "INSERT INTO swe_agentobs_inbox (payload_text) VALUES (%s)",
                    (json.dumps(record, separators=(",", ":")),),
                )
        projector = InboxProjector(store, poll_seconds=0.01)
        while await projector.project_batch():
            pass

        api = FastAPI()
        api.state.agent_observability_store = store

        @api.middleware("http")
        async def bind_source(request, call_next):
            request.state.source_id = request.headers.get("X-Source-Id")
            return await call_next(request)

        api.include_router(observability_router)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api),
            base_url="http://agentobs.test",
        ) as client:
            response = await client.get(
                f"/agent-observability/runs/{context.obs_run_id}/assets",
                headers={
                    "X-User-Role": "manager",
                    "X-Source-Id": "agentobs-integration",
                },
            )
            forbidden = await client.get(
                f"/agent-observability/runs/{context.obs_run_id}/assets",
                headers={
                    "X-User-Role": "manager",
                    "X-Source-Id": "another-source",
                },
            )

        assert response.status_code == 200
        assert forbidden.status_code == 404
        assets = response.json()["items"]
        skill_asset = next(
            item for item in assets if item["asset_type"] == "skill"
        )
        assert skill_asset == {
            "asset_ref": skill_asset["asset_ref"],
            "span_id": None,
            "asset_type": "skill",
            "asset_id": "research",
            "asset_digest": signature,
            "asset_source": "runtime_snapshot",
        }
        assert await store.list_spans(run_id=context.obs_run_id) == []
    finally:
        await connection.close()
