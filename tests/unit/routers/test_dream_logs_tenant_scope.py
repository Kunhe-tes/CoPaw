# -*- coding: utf-8 -*-
"""Dream logs router scope helper tests."""

from types import SimpleNamespace

from swe.app.routers.dream_logs import _get_tenant_id
from swe.config.context import encode_scope_id


def test_get_tenant_id_prefers_request_scope_id() -> None:
    request = SimpleNamespace(
        state=SimpleNamespace(
            tenant_id="tenant-a",
            source_id="source-a",
            scope_id=encode_scope_id("tenant-a", "source-a"),
        ),
        headers={"X-Tenant-Id": "tenant-a"},
    )

    assert _get_tenant_id(request) == encode_scope_id(
        "tenant-a",
        "source-a",
    )
