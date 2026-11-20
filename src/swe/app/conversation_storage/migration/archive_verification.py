# -*- coding: utf-8 -*-
"""Bounded, batched archive publication and NAS reads."""

import asyncio

from ..bundle import BundleStore
from ..message_bundle import (
    decode_archive_manifest,
    decode_message_bodies,
    decode_message_directory,
)

PUBLICATION_FIELDS = (
    "id,scope_kind,service_unit_key,tenant_key,source_key,agent_key,"
    "operation_key,session_id,chat_id,epoch,relative_path,byte_length,"
    "state,gc_state,durable_at"
)
PUBLICATION_BATCH_SIZE = 128


async def fetch_publications(
    database,
    identifiers,
    *,
    committed_live=False,
):
    """Fetch unique Publication rows in bounded SQL batches."""
    unique = tuple(dict.fromkeys(identifiers))
    rows = {}
    for start in range(0, len(unique), PUBLICATION_BATCH_SIZE):
        batch = unique[start : start + PUBLICATION_BATCH_SIZE]
        query = (
            "SELECT "
            + PUBLICATION_FIELDS
            + " FROM swe_conversation_publications WHERE id IN ("
            + ",".join(["%s"] * len(batch))
            + ")"
        )
        if committed_live:
            query += " AND state='committed' AND gc_state='live'"
        for row in await database.fetch_all(query, batch):
            if row["id"] in rows:
                raise ValueError("duplicate publication identity")
            rows[row["id"]] = row
    return rows


async def run_bounded_io(io, calls, workers):
    """Run synchronous bundle reads with bounded in-flight work."""
    if not calls:
        return []
    if workers <= 0:
        raise ValueError("archive verification workers must be positive")
    results = []
    for start in range(0, len(calls), workers):
        batch = calls[start : start + workers]
        if io is None:
            results.extend(call() for call in batch)
        else:
            results.extend(
                await asyncio.gather(*(io.call(call) for call in batch)),
            )
    return results


def read_archive_manifest(bundles, publication):
    """Read one boundary manifest with a single bundle open."""
    path = BundleStore.validate_publication_locator(publication)
    with bundles.open_reader(
        path,
        expected_length=publication["byte_length"],
    ) as reader:
        extent = reader.index.blocks.get("archive_manifest")
        if extent is None or extent.kind != "archive_manifest":
            raise ValueError("archive boundary manifest is missing")
        (payload,) = reader.read_extents((extent,))
    return decode_archive_manifest(payload)


def read_archive_chunk(
    bundles,
    publication,
    directory_block,
    *,
    include_bodies,
    allowance,
    expected_operation_key=None,
):
    """Read directory and optional bodies in one verified bundle open."""
    path = BundleStore.validate_publication_locator(publication)
    with bundles.open_reader(
        path,
        expected_length=publication["byte_length"],
        expected_operation_key=expected_operation_key,
    ) as reader:
        directory_extent = reader.index.blocks.get(directory_block)
        if (
            directory_extent is None
            or directory_extent.kind != "message_directory"
        ):
            raise ValueError("archive chunk directory is missing")
        extents = [directory_extent]
        if include_bodies:
            body_extent = reader.index.blocks.get("message_bodies")
            if body_extent is None or body_extent.kind != "message_bodies":
                raise ValueError("archive chunk bodies are missing")
            extents.append(body_extent)
        payloads = reader.read_extents(extents, max_bytes=allowance)
    directory = decode_message_directory(payloads[0])
    bodies = decode_message_bodies(payloads[1]) if include_bodies else None
    return directory, bodies


def archive_read_workers(io_workers, memory_bytes):
    """Limit concurrent decoded chunks to at most 64 MiB per worker."""
    return max(1, min(io_workers, memory_bytes // (64 * 1024 * 1024)))
