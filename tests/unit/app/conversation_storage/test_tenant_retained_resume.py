# -*- coding: utf-8 -*-
"""Committed failed tenants resume only with accepted unchanged input proof."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from swe.cli import conversation_storage_tenants as cli
from swe.app.conversation_storage.migration import tenant_retry, tenant_inputs
from swe.app.conversation_storage.migration.tenant_errors import SourceChanged
from swe.app.conversation_storage import in_place_admission

JOB = "00000000-0000-4000-8000-000000000001"


@pytest.mark.parametrize(
    "proof,allowed",
    [
        ("matching", True),
        ("missing", False),
        ("changed", False),
    ],
)
async def test_auto_review_retained_requires_matching_digest(
    tmp_path,
    monkeypatch,
    proof,
    allowed,
):
    tenant = {"service_unit_id": "svc", "tenant_id": "bob", "state": "failed"}
    if proof != "missing":
        tenant["input_digest"] = "frozen"
    manifest = SimpleNamespace(
        migration_id=JOB,
        path=tmp_path / "manifest.json",
        data={"tenants": [tenant]},
    )
    states = SimpleNamespace(get=AsyncMock(return_value={"state": "failed"}))
    monkeypatch.setattr(cli, "TenantState", lambda *_: states)
    monkeypatch.setattr(cli, "_register_tenants", AsyncMock())
    review = AsyncMock(return_value={"retained_keys": [["svc", "bob"]]})
    monkeypatch.setattr(tenant_retry, "review_retry", review)
    boundary = Mock()
    monkeypatch.setattr(
        in_place_admission,
        "tenant_write_boundaries",
        boundary,
    )
    verify = Mock(
        side_effect=SourceChanged("changed") if proof == "changed" else None,
    )
    monkeypatch.setattr(tenant_inputs, "verify_input_digest", verify)
    result = await cli._auto_review(
        None,
        manifest,
        SimpleNamespace(check=AsyncMock()),
        {
            "workers": 1,
            "io_workers": 1,
            "memory_bytes": 128 * 1024 * 1024,
        },
    )
    assert result == ({("svc", "bob")} if allowed else set())
    assert review.call_args.kwargs["eligible"] == {("svc", "bob")}
    assert tenant["state"] == "failed"
    assert verify.call_count == (0 if proof == "missing" else 1)


@pytest.mark.parametrize("allowed", [False, True])
async def test_registered_failed_gate_only_opens_for_retained_attempt(
    tmp_path,
    monkeypatch,
    allowed,
):
    tenant = {"service_unit_id": "svc", "tenant_id": "bob", "state": "failed"}
    manifest = SimpleNamespace(
        migration_id=JOB,
        path=tmp_path / "manifest.json",
        data={
            "tenants": [tenant],
            "workspaces": [],
            "shares": [],
            "services": [],
        },
    )
    states = SimpleNamespace(
        get=AsyncMock(return_value={"state": "failed"}),
        fail=AsyncMock(),
    )
    monkeypatch.setattr(cli, "TenantState", lambda *_: states)
    monkeypatch.setattr(cli, "_register_tenants", AsyncMock())
    monkeypatch.setattr(cli, "_write_failures", Mock(return_value="report"))
    one = AsyncMock()
    monkeypatch.setattr(cli, "_one_tenant", one)
    db = SimpleNamespace(execute=AsyncMock(return_value=1))
    resources = {"_retained_attempts": {("svc", "bob")} if allowed else set()}
    result = await cli._run_registered(
        "resume",
        manifest,
        None,
        db,
        SimpleNamespace(check=AsyncMock(), server_uuid="server"),
        tmp_path,
        resources,
    )
    assert one.await_count == int(allowed)
    assert states.fail.await_count == int(not allowed)
    assert result["failed"] == int(not allowed)
    assert tenant["state"] == "failed"
