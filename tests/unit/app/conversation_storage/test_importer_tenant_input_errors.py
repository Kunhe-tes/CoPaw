# -*- coding: utf-8 -*-
"""Malformed tenant source fields must not terminate other accounts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swe.app.conversation_storage.migration.importer import (
    ConversationImporter,
    _timestamp,
)
from swe.app.conversation_storage.migration.tenant_errors import (
    TenantInputError,
)
from swe.cli import conversation_storage_tenants as cli

JOB = "00000000-0000-4000-8000-000000000001"


@pytest.mark.parametrize("revision", ["bad", -1, True, None])
async def test_bad_revision_fails_tenant_and_continues_registered_loop(
    tmp_path,
    monkeypatch,
    revision,
):
    tenants = [
        {"service_unit_id": "svc", "tenant_id": name, "state": "discovered"}
        for name in ("bob", "charlie")
    ]
    manifest = SimpleNamespace(
        migration_id=JOB,
        path=tmp_path / "manifest.json",
        data={
            "tenants": tenants,
            "workspaces": [],
            "shares": [],
            "services": [],
        },
    )
    states = SimpleNamespace(
        get=AsyncMock(return_value={"state": "discovered"}),
        fail=AsyncMock(),
    )

    async def get_many(keys):
        for key in keys:
            yield key, {"state": "discovered"}

    states.get_many = get_many
    monkeypatch.setattr(cli, "TenantState", lambda *_: states)
    monkeypatch.setattr(cli, "_register_tenants", AsyncMock())
    monkeypatch.setattr(cli, "_write_failures", lambda *_: "failures.json")
    completed = []

    async def import_tenant(_operation, view, *_args):
        state = {"revision": revision if view.key[1] == "bob" else 1}
        ConversationImporter._validate_runtime_sources(
            object(),
            {
                "workspaces": [
                    {"sessions": [{"legacy": {"state": state}}], "chats": []},
                ],
            },
        )
        completed.append(view.key[1])

    monkeypatch.setattr(cli, "_one_tenant", import_tenant)
    result = await cli._run_registered(
        "resume",
        manifest,
        None,
        SimpleNamespace(execute=AsyncMock(return_value=1)),
        SimpleNamespace(check=AsyncMock(), server_uuid="server"),
        tmp_path,
        {},
    )
    assert completed == ["charlie"]
    assert result["failed"] == 1
    assert result["completed"] == 1
    assert states.fail.call_args.args[:2] == ("svc", "bob")
    assert states.fail.call_args.args[3] == "tenant_input_invalid"


@pytest.mark.parametrize("value", ["bad timestamp", 123, {}, []])
def test_bad_message_timestamp_is_an_explicit_tenant_error(value):
    with pytest.raises(TenantInputError, match="timestamp"):
        _timestamp(value)


def test_late_revision_guard_is_an_explicit_tenant_error():
    session = {"position": "session", "legacy": {"state": {"revision": "bad"}}}
    with pytest.raises(TenantInputError, match="revision"):
        ConversationImporter._session_recovery_updates(
            object(),
            session,
            session["legacy"]["state"],
            {},
            1,
            0,
        )


@pytest.mark.parametrize(
    "value, expected",
    [(None, None), ("2026-11-15T00:00:00Z", "2026-11-15T00:00:00+00:00")],
)
def test_valid_message_timestamp_retains_normalization(value, expected):
    assert _timestamp(value) == expected


@pytest.mark.parametrize(
    "state",
    [
        {"agent": []},
        {"agent": {"memory": []}},
        {"unrelated_state": float("nan")},
    ],
)
def test_runtime_source_shape_and_json_fail_with_tenant_error(state):
    with pytest.raises(TenantInputError):
        ConversationImporter._validate_runtime_sources(
            object(),
            {
                "workspaces": [
                    {"sessions": [{"legacy": {"state": state}}], "chats": []},
                ],
            },
        )
