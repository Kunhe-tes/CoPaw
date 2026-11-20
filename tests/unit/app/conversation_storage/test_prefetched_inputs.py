# -*- coding: utf-8 -*-
"""Prefetched evidence errors preserve tenant versus shared IO boundaries."""

import errno
import threading
from types import SimpleNamespace

import pytest

from swe.cli import conversation_storage_tenants as cli
from swe.app.conversation_storage.migration.parallel import (
    MigrationIO,
    MigrationResources,
)
from swe.app.conversation_storage.migration.source_inputs import (
    SourceInputInvalid,
)


@pytest.mark.parametrize(
    "case",
    ["invalid", "file_missing", "root_missing", "eio", "success"],
)
async def test_recheck_prefetched_uses_borrowed_io_and_preserves_failure_scope(
    tmp_path,
    monkeypatch,
    case,
):
    from swe.app.conversation_storage.migration import tenant_inputs

    root = tmp_path / "source"
    root.mkdir()
    source = root / "tenant" / "chats.json"
    data = {
        "freshness_protocol": "chats-mtime-v1",
        "services": [
            {
                "source_root": str(root),
                "config_root": str(root),
                "snapshot_root": str(root),
            },
        ],
    }
    view = SimpleNamespace(data=data, key=("svc", "tenant"))
    owner_thread = threading.get_ident()
    invoked = []
    error = {
        "invalid": SourceInputInvalid("unsafe source"),
        "file_missing": FileNotFoundError(
            errno.ENOENT,
            "missing input",
            str(source),
        ),
        "root_missing": FileNotFoundError(
            errno.ENOENT,
            "missing root",
            str(root),
        ),
        "eio": OSError(errno.EIO, "shared IO failed", str(source)),
    }.get(case)
    if case == "root_missing":
        root.rmdir()

    def verify(actual_data, key):
        assert threading.get_ident() != owner_thread
        assert shared.memory.used == shared.allowance
        assert actual_data is data
        assert key == view.key
        invoked.append(True)
        if error is not None:
            raise error

    monkeypatch.setattr(tenant_inputs, "verify_chats_mtimes", verify)
    async with MigrationIO(2) as io:
        async with MigrationResources(
            workers=1,
            memory_bytes=100,
            io=io,
        ) as shared:
            resources = {"_shared_resources": shared, "_shared_io": io}
            if case in ("invalid", "file_missing"):
                with pytest.raises(cli.TenantFailure) as caught:
                    await cli._recheck_prefetched(view, resources)
                assert caught.value.__cause__ is error
            elif error is not None:
                with pytest.raises(type(error)) as caught:
                    await cli._recheck_prefetched(view, resources)
                assert caught.value is error
            else:
                await cli._recheck_prefetched(view, resources)
            assert invoked == [True]
            assert shared.memory.used == 0
            assert shared.memory.peak == 100
        assert (
            await io.call(lambda: "borrowed pool remains open")
            == "borrowed pool remains open"
        )
