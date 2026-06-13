# -*- coding: utf-8 -*-

from swe.app.middleware import runtime_static_gzip


def test_runtime_static_gzip_default_compresslevel(monkeypatch) -> None:
    captured: dict[str, int] = {}

    class FakeGZipMiddleware:
        def __init__(self, app, minimum_size: int, compresslevel: int) -> None:
            captured["minimum_size"] = minimum_size
            captured["compresslevel"] = compresslevel

    monkeypatch.setattr(
        runtime_static_gzip,
        "GZipMiddleware",
        FakeGZipMiddleware,
    )

    runtime_static_gzip.RuntimeStaticGZipMiddleware(app=object())

    assert captured == {
        "minimum_size": 500,
        "compresslevel": 3,
    }
