# -*- coding: utf-8 -*-
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from swe.observability.query import _authorized_sources


def test_admin_source_filter_caps_unique_authorized_sources_at_32():
    admin = SimpleNamespace(
        headers={"X-User-Role": "admin"},
        state=SimpleNamespace(source_id="source-current"),
    )
    sources = [f"source-{index}" for index in range(32)]

    assert _authorized_sources(admin, sources) == sources
    assert _authorized_sources(admin, [*sources, sources[0]]) == sources

    with pytest.raises(HTTPException) as error:
        _authorized_sources(admin, [*sources, "source-over-limit"])

    assert error.value.status_code == 400
    assert error.value.detail == "Too many Source filters"
