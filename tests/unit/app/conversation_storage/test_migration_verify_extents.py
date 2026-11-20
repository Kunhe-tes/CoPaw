# -*- coding: utf-8 -*-
import pytest

from swe.app.conversation_storage.bundle import (
    BundleBlock,
    BundleStore,
    new_operation_key,
)
from swe.app.conversation_storage.migration.parallel import MigrationIO
from swe.app.conversation_storage.migration.runtime_prefetch import (
    PrefetchedBundles,
)
from swe.app.conversation_storage.migration.verify import _read_extents


@pytest.mark.parametrize(
    "mode",
    ["direct", "threaded", "prefetched"],
)
async def test_verification_retains_per_extent_limit_with_metadata(
    tmp_path,
    monkeypatch,
    mode,
):
    body = b"x" * (9 * 1024 * 1024)
    store = BundleStore(tmp_path, unbounded=True)
    index = store.publish(
        new_operation_key(),
        [
            BundleBlock("metadata", "legacy_artifact_metadata", b"{}"),
            BundleBlock("body", "legacy_artifact", body),
        ],
    )
    bundles = store
    if mode == "prefetched":
        bundles = PrefetchedBundles(store)
        bundles.indexes[index.relative_path] = index
        bundles.blocks[index.relative_path] = [
            (index.blocks["metadata"].offset, b"{}"),
            (index.blocks["body"].offset, body),
        ]
    decodes = []
    original = store._decode_table

    def decode(*args):
        decodes.append(1)
        return original(*args)

    monkeypatch.setattr(store, "_decode_table", decode)

    async def read(io):
        return await _read_extents(
            bundles,
            index.relative_path,
            tuple(index.blocks.values()),
            io=io,
        )

    async with MigrationIO(1) as io:
        assert await read(io if mode == "threaded" else None) == (
            b"{}",
            body,
        )
    assert decodes == ([] if mode == "prefetched" else [1])


async def test_verification_rejects_more_than_two_extents(tmp_path):
    store = BundleStore(tmp_path)
    index = store.publish(
        new_operation_key(),
        [BundleBlock("body", "legacy_artifact", b"x")],
    )
    with pytest.raises(ValueError, match="at most two extents"):
        await _read_extents(
            store,
            index.relative_path,
            (index.blocks["body"],) * 3,
            io=None,
        )
