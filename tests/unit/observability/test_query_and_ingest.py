# -*- coding: utf-8 -*-
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from swe.observability import Scope, ObservabilityContext
from swe.observability.db_config import get_observability_database_config
from swe.observability.projector import InboxProjector, _validate_payload
from swe.observability.query import (
    _authorized_sources,
    _decode_cursor,
    _encode_cursor,
    capabilities,
    health,
)


def test_observability_database_does_not_fallback_to_application_database(
    monkeypatch,
):
    monkeypatch.setenv("SWE_DB_HOST", "business-db")
    monkeypatch.setenv("SWE_DB_NAME", "business")
    monkeypatch.delenv("SWE_AGENTOBS_DB_HOST", raising=False)
    assert get_observability_database_config() is None

    monkeypatch.setenv("SWE_AGENTOBS_DB_HOST", "obs-db")
    monkeypatch.setenv("SWE_AGENTOBS_DB_PASSWORD", "plain-secret")
    config = get_observability_database_config()
    assert config.host == "obs-db"
    assert config.database == "swe_agentobs"
    assert config.password == "plain-secret"


def test_manager_cannot_expand_source_scope_and_admin_can_be_explicit():
    manager = SimpleNamespace(
        headers={"X-User-Role": "manager"},
        state=SimpleNamespace(source_id="source-a"),
    )
    assert _authorized_sources(manager, None) == ["source-a"]
    with pytest.raises(HTTPException) as error:
        _authorized_sources(manager, ["source-b"])
    assert error.value.status_code == 403

    admin = SimpleNamespace(
        headers={"X-User-Role": "admin"},
        state=SimpleNamespace(source_id="source-a"),
    )
    assert _authorized_sources(admin, ["source-b", "source-a"]) == [
        "source-b",
        "source-a",
    ]


def test_cursor_is_signed_and_bound_to_authorized_filters(monkeypatch):
    monkeypatch.setenv("SWE_AGENTOBS_CURSOR_SECRET", "x" * 40)
    scope = {"role": "manager", "sources": ["source-a"], "window": "24h"}
    from datetime import datetime, timezone

    token = _encode_cursor(datetime.now(timezone.utc), str(uuid4()), scope)
    assert _decode_cursor(token, scope)[1]
    with pytest.raises(HTTPException) as error:
        _decode_cursor(token, {**scope, "sources": ["source-b"]})
    assert error.value.status_code == 400
    with pytest.raises(HTTPException):
        _decode_cursor(token[:-2] + "aa", scope)


@pytest.mark.asyncio
async def test_capabilities_are_scoped_and_do_not_expose_database_secrets(
    monkeypatch,
):
    monkeypatch.delenv("SWE_AGENTOBS_ENABLED", raising=False)
    app = SimpleNamespace(
        state=SimpleNamespace(
            agent_observability_connection=None,
            agent_observability_projector=None,
            agent_observability_store=None,
        ),
    )
    request = SimpleNamespace(
        headers={"X-User-Role": "manager"},
        state=SimpleNamespace(source_id="source-a"),
        app=app,
    )
    result = await capabilities(request)
    assert result.capture_enabled is False
    assert result.storage_configured is False
    assert not hasattr(result, "password")

    request.headers = {"X-User-Role": "user"}
    with pytest.raises(HTTPException) as error:
        await capabilities(request)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_global_health_is_admin_only(monkeypatch):
    monkeypatch.delenv("SWE_AGENTOBS_ENABLED", raising=False)
    app = SimpleNamespace(
        state=SimpleNamespace(
            agent_observability_projector=None,
            agent_observability_store=None,
        ),
    )
    manager = SimpleNamespace(
        headers={"X-User-Role": "manager"},
        state=SimpleNamespace(source_id="source-a"),
        app=app,
    )
    with pytest.raises(HTTPException) as error:
        await health(manager)
    assert error.value.status_code == 403

    admin = SimpleNamespace(
        headers={"X-User-Role": "admin"},
        state=SimpleNamespace(),
        app=app,
    )
    result = await health(admin)
    assert result.storage_ready is False
    assert result.dropped_events is None


def test_ingest_validation_projects_body_and_rejects_bad_scope():
    context = ObservabilityContext.new_run(
        capture_enabled=True,
        scope=Scope("svc", "source", "tenant", "agent"),
        business_ref={"chat_id": "chat"},
    )
    event = {
        "schema_version": 1,
        "event_id": str(uuid4()),
        "event_name": "run.accepted",
        "occurred_at": context.run_started_at,
        "producer_id": "host:123:boot",
        "entity_kind": "run",
        "entity_id": context.obs_run_id,
        "phase_key": "accepted",
        "local_seq": 0,
        "obs_run_id": context.obs_run_id,
        "run_started_at": context.run_started_at,
        "capture_enabled": True,
        "scope": context.scope.to_dict(),
        "business_ref": {"chat_id": "chat", "message": "private question"},
        "started_at": context.run_started_at,
        "prompt": "private prompt",
    }
    validated = _validate_payload(json.dumps(event))
    assert "prompt" not in validated
    assert "message" not in validated["business_ref"]
    event["scope"] = {"source_id": "source"}
    with pytest.raises(ValueError, match="invalid_scope"):
        _validate_payload(json.dumps(event))
    event["scope"] = context.scope.to_dict()
    event["event_name"] = "run.ended"
    event["phase_key"] = "ended"
    event["ended_at"] = context.run_started_at
    event["terminal_fact_source"] = "business_settlement"
    with pytest.raises(ValueError, match="event_missing_required_field"):
        _validate_payload(json.dumps(event))
    event["status"] = "partial"
    with pytest.raises(ValueError, match="invalid_run_terminal_status"):
        _validate_payload(json.dumps(event))


def test_ingest_validation_rejects_sql_width_overflow_and_bad_attempt_ids():
    context = ObservabilityContext.new_run(
        capture_enabled=True,
        scope=Scope("svc", "source", "tenant", "agent"),
    )
    event = {
        "schema_version": 1,
        "event_id": str(uuid4()),
        "event_name": "span.started",
        "occurred_at": context.run_started_at,
        "producer_id": "p" * 129,
        "entity_kind": "span",
        "entity_id": str(uuid4()),
        "phase_key": "started",
        "local_seq": 0,
        "obs_run_id": context.obs_run_id,
        "obs_attempt_id": str(uuid4()),
        "obs_span_id": str(uuid4()),
        "run_started_at": context.run_started_at,
        "capture_enabled": True,
        "scope": context.scope.to_dict(),
        "span_type": "Tool",
        "operation": "execute",
        "kind": "INTERNAL",
        "name": "registered.tool",
        "started_at": context.run_started_at,
    }
    event["entity_id"] = event["obs_span_id"]
    event["name"] = "registered.tool"
    event["producer_id"] = "host:123:boot"
    event["error_type"] = None
    assert _validate_payload(json.dumps(event))["error_type"] is None
    event.pop("error_type")
    event["producer_id"] = "p" * 129
    with pytest.raises(ValueError, match="field_too_long"):
        _validate_payload(json.dumps(event))
    event["obs_attempt_id"] = "bad-id"
    event["producer_id"] = "host:123:boot"
    with pytest.raises(ValueError, match="invalid_identity"):
        _validate_payload(json.dumps(event))
    event["obs_attempt_id"] = str(uuid4())
    event["has_error"] = "false"
    with pytest.raises(ValueError, match="invalid_error_flag"):
        _validate_payload(json.dumps(event))
    event["has_error"] = 1
    with pytest.raises(ValueError, match="invalid_error_flag"):
        _validate_payload(json.dumps(event))
    event["has_error"] = False
    event["terminal_fact_source"] = "x" * 33
    with pytest.raises(ValueError, match="field_too_long"):
        _validate_payload(json.dumps(event))


@pytest.mark.asyncio
async def test_projector_sets_read_committed_on_its_transaction_connection():
    operations = []

    class Session:
        async def execute(self, query, params=None):
            operations.append(("execute", self, query))

        async def fetch_all(self, query, params=None):
            operations.append(("fetch", self, query))
            return []

    session = Session()

    @asynccontextmanager
    async def acquire():
        yield session

    @asynccontextmanager
    async def transaction():
        yield session

    connection = SimpleNamespace(acquire=acquire, transaction=transaction)
    projector = InboxProjector(SimpleNamespace(connection=connection))
    assert await projector.project_batch() == 0
    assert operations[0][0:2] == ("execute", session)
    assert operations[1][0:2] == ("fetch", session)
    assert "SKIP LOCKED" in operations[1][2]
    assert "READ COMMITTED" in operations[0][2]


@pytest.mark.asyncio
async def test_optional_database_configuration_errors_do_not_abort_app_startup(
    monkeypatch,
):
    from swe.app import _app
    from swe.observability import db_config

    def invalid_config():
        raise ValueError("invalid optional port")

    monkeypatch.setattr(
        db_config,
        "get_observability_database_config",
        invalid_config,
    )
    app = SimpleNamespace(state=SimpleNamespace())
    await _app._initialize_agent_observability_storage(app)
    assert app.state.agent_observability_connection is None
    assert app.state.agent_observability_store is None


@pytest.mark.asyncio
async def test_readiness_rejects_existing_tables_with_missing_schema_parts():
    from swe.observability.store import (
        REQUIRED_COLUMNS,
        REQUIRED_INDEXES,
        ObservabilityStore,
    )

    class Session:
        async def fetch_all(self, query, _params):
            if "information_schema.COLUMNS" in query:
                return [
                    {"TABLE_NAME": table, "COLUMN_NAME": column}
                    for table, columns in REQUIRED_COLUMNS.items()
                    for column in columns
                    if not (
                        table == "swe_agentobs_runs" and column == "status"
                    )
                ]
            return [
                {
                    "TABLE_NAME": table,
                    "INDEX_NAME": name,
                    "NON_UNIQUE": int(not unique),
                    "SEQ_IN_INDEX": position,
                    "COLUMN_NAME": (
                        "wrong_column"
                        if name == "uq_agentobs_event_slot"
                        else column
                    ),
                }
                for table, definitions in REQUIRED_INDEXES.items()
                for name, (unique, columns) in definitions.items()
                for position, column in enumerate(columns, start=1)
            ]

    session = Session()

    @asynccontextmanager
    async def acquire():
        yield session

    connection = SimpleNamespace(
        acquire=acquire,
        config=SimpleNamespace(database="obs"),
    )
    readiness = await ObservabilityStore(connection).readiness()
    assert not readiness["ready"]
    assert readiness["missing_columns"]["swe_agentobs_runs"] == ["status"]
    assert readiness["invalid_indexes"]["swe_agentobs_events"] == [
        "uq_agentobs_event_slot",
    ]
