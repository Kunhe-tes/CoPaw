# -*- coding: utf-8 -*-
"""Retain exact preoptimization plans when resuming immutable bundles."""

from ..bundle import BundleBlock, BundleStore
from ..errors import IntegrityError


def retained_plan(bundles, row, expected, legacy):
    """Read only NAS evidence and accept exactly one canonical plan candidate."""
    index = bundles.inspect(
        BundleStore.validate_publication_locator(row),
        expected_length=row["byte_length"],
    )
    if index.metadata.get("operation_key") != row["operation_key"].decode():
        raise IntegrityError("offline original plan publication mismatch")
    extent = index.blocks.get("import_plan")
    if extent is None or extent.kind != "import_plan":
        raise IntegrityError("offline import plan block is missing")
    raw = bundles.read_extent(
        index.relative_path,
        extent.offset,
        extent.length,
        expected_length=index.byte_length,
    )
    if raw not in (expected.content, legacy.content):
        raise IntegrityError(
            "original import plan differs from current source mapping",
        )
    return BundleBlock("import_plan", "import_plan", raw)
