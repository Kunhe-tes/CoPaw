# -*- coding: utf-8 -*-
"""Bounded reads for multi-publication archive message bundles."""

from dataclasses import dataclass
import asyncio
import json

from .bundle import BundleStore
from .chat_mutations import load_metadata_json
from .errors import IntegrityError
from .message_bundle import (
    decode_archive_manifest,
    decode_message_bodies,
    decode_message_directory,
    select_archive_chunks,
)
from .identity import chat_key_bytes
from .retention import ReaderPins, RetentionStore


@dataclass(frozen=True)
class ArchiveBundleResult:
    """Selected directory occurrences and the pins protecting their bodies."""

    entries: tuple[dict, ...]
    indexes: dict[int, object]
    pins: ReaderPins
    manifest: dict


def _text(value):
    return (
        bytes(value).decode("utf-8")
        if isinstance(value, (bytes, bytearray))
        else value
    )


def _publication_id(row):
    identity = row.get("id") if hasattr(row, "get") else None
    if type(identity) is not int or identity <= 0:
        raise IntegrityError("archive publication identity is invalid")
    return identity


def _manifest_extent(index):
    extent = index.blocks.get("archive_manifest")
    if extent is None or extent.kind != "archive_manifest":
        raise IntegrityError("archive manifest block is missing")
    return extent


def validate_archive_manifest(
    manifest,
    *,
    first_sequence=None,
    last_sequence=None,
):
    """Validate a decoded boundary manifest and return its selected chunks."""
    normalized = decode_archive_manifest(
        json.dumps(
            manifest,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8"),
    )
    first = (
        normalized["first_sequence"]
        if first_sequence is None
        else first_sequence
    )
    last = (
        normalized["last_sequence"] if last_sequence is None else last_sequence
    )
    chunks = select_archive_chunks(normalized, first, last)
    return normalized, chunks


def archive_manifest_dependencies(manifest, *, boundary_publication_id=None):
    """Return committed publication IDs the boundary must retain."""
    normalized, _ = validate_archive_manifest(manifest)
    dependencies = set()
    for chunk in normalized["chunks"]:
        identity = chunk["publication_id"]
        if identity == "self":
            if boundary_publication_id is None:
                raise IntegrityError(
                    "self archive chunk requires a boundary publication ID",
                )
            identity = boundary_publication_id
        if identity != boundary_publication_id:
            dependencies.add(identity)
    return tuple(sorted(dependencies))


async def read_archive_bundle(
    database,
    scope,
    bundles,
    publication,
    *,
    first_sequence=None,
    last_sequence=None,
    retentions=None,
    prepared_index=None,
):
    """Read selected archive occurrences while keeping every source pinned.

    ``publication`` is the boundary publication row. Chunk publications are
    discovered from its manifest and body publications from their directories.
    The caller must call ``await result.pins.finish()`` after consuming entries.
    """
    boundary_id = _publication_id(publication)
    retention_store = retentions or RetentionStore(database, scope)
    pins = ReaderPins(retention_store)
    if prepared_index is None:
        await pins.pin([boundary_id])
    try:
        result, indexes, manifest = await _read_archive_entries(
            database,
            bundles,
            publication,
            boundary_id,
            pins,
            first_sequence=first_sequence,
            last_sequence=last_sequence,
            prepared_index=prepared_index,
        )
        return ArchiveBundleResult(tuple(result), indexes, pins, manifest)
    except BaseException:
        await pins.finish()
        raise


async def _read_archive_entries(
    database,
    bundles,
    publication,
    boundary_id,
    pins,
    *,
    first_sequence,
    last_sequence,
    prepared_index,
):
    read_local = _reader(pins)
    publication = _pinned_boundary(publication, boundary_id, pins)
    boundary_path = BundleStore.validate_publication_locator(publication)
    boundary_index = await _boundary_index(
        bundles,
        publication,
        boundary_path,
        read_local,
        prepared_index,
    )
    manifest, chunks = await _manifest_and_chunks(
        database,
        bundles,
        publication,
        boundary_path,
        boundary_index,
        read_local,
        prepared_index,
        first_sequence,
        last_sequence,
    )
    first = (
        manifest["first_sequence"]
        if first_sequence is None
        else first_sequence
    )
    last = (
        manifest["last_sequence"] if last_sequence is None else last_sequence
    )
    rows, indexes, directories = await _read_directories(
        bundles,
        publication,
        boundary_id,
        boundary_index,
        manifest,
        chunks,
        pins,
        read_local,
        first,
        last,
    )
    result = await _read_bodies(
        bundles,
        publication,
        boundary_id,
        rows,
        indexes,
        directories,
        pins,
        read_local,
    )
    return result, indexes, manifest


def _reader(pins):
    async def read_local(function, *args, **kwargs):
        if pins.batches:
            return await pins.read(function, *args, **kwargs)
        return await asyncio.to_thread(function, *args, **kwargs)

    return read_local


def _pinned_boundary(publication, boundary_id, pins):
    pinned = {row["id"]: row for row in pins.publications}
    current = pinned.get(boundary_id)
    if current is None:
        return publication
    return {**publication, **current}


async def _boundary_index(
    bundles,
    publication,
    path,
    read_local,
    prepared_index,
):
    if prepared_index is None:
        return await read_local(
            bundles.inspect,
            path,
            expected_length=publication["byte_length"],
        )
    if (
        prepared_index.relative_path != path
        or prepared_index.byte_length != publication["byte_length"]
    ):
        raise IntegrityError("prepared archive bundle identity mismatch")
    return prepared_index


async def _manifest_and_chunks(
    database,
    bundles,
    publication,
    path,
    index,
    read_local,
    prepared_index,
    first_sequence,
    last_sequence,
):
    extent = _manifest_extent(index)
    payload = await read_local(
        bundles.read_extent,
        path,
        extent.offset,
        extent.length,
        expected_length=index.byte_length,
    )
    manifest, chunks = validate_archive_manifest(
        decode_archive_manifest(payload),
        first_sequence=first_sequence,
        last_sequence=last_sequence,
    )
    chat = await database.fetch_one(
        "SELECT external_chat_key FROM swe_conversation_chats WHERE id=%s",
        (publication["chat_id"],),
    )
    if chat is None or chat_key_bytes(manifest["chat_id"]) != bytes(
        chat["external_chat_key"],
    ):
        raise IntegrityError("archive manifest Chat identity mismatch")
    if (
        publication.get("epoch") is not None
        and publication["epoch"] != manifest["epoch"]
    ):
        raise IntegrityError("archive manifest epoch differs from publication")
    archive_offset = publication.get("archive_offset")
    archive_length = publication.get("archive_length")
    if prepared_index is None and (
        archive_offset is None
        or archive_length is None
        or int(archive_offset) != extent.offset
        or int(archive_length) != extent.length
    ):
        raise IntegrityError(
            "archive manifest locator differs from publication",
        )
    return manifest, chunks


async def _read_directories(
    bundles,
    boundary,
    boundary_id,
    boundary_index,
    manifest,
    chunks,
    pins,
    read_local,
    first,
    last,
):
    await pins.pin(
        [
            chunk["publication_id"]
            for chunk in chunks
            if chunk["publication_id"] != "self"
        ],
    )
    rows = {row["id"]: row for row in pins.publications}
    rows[boundary_id] = boundary
    indexes = {boundary_id: boundary_index}
    directories = []
    sources = {}
    for chunk in chunks:
        identity = (
            boundary_id
            if chunk["publication_id"] == "self"
            else chunk["publication_id"]
        )
        row = rows.get(identity)
        if row is None:
            raise IntegrityError("archive chunk publication is not pinned")
        _validate_chunk_publication(row, boundary, manifest)
        path = BundleStore.validate_publication_locator(row)
        index = (
            boundary_index
            if identity == boundary_id
            else await read_local(
                bundles.inspect,
                path,
                expected_length=row["byte_length"],
            )
        )
        indexes[identity] = index
        extent = index.blocks.get(chunk["directory_block"])
        if extent is None or extent.kind != "message_directory":
            raise IntegrityError("archive message directory block is missing")
        payload = await read_local(
            bundles.read_extent,
            path,
            extent.offset,
            extent.length,
            expected_length=index.byte_length,
        )
        entries = decode_message_directory(payload)
        _validate_directory_range(entries, chunk)
        for entry in entries:
            if first <= entry["sequence"] <= last:
                directories.append(entry)
                sources[id(entry)] = identity
    return (
        rows,
        indexes,
        [(entry, sources[id(entry)]) for entry in directories],
    )


def _validate_directory_range(entries, chunk):
    if not entries or (
        entries[0]["sequence"] != chunk["first_sequence"]
        or entries[-1]["sequence"] != chunk["last_sequence"]
        or any(
            entry["sequence"] != chunk["first_sequence"] + offset
            for offset, entry in enumerate(entries)
        )
    ):
        raise IntegrityError(
            "archive directory disagrees with manifest sequence range",
        )


async def _read_bodies(
    bundles,
    boundary,
    boundary_id,
    rows,
    indexes,
    directories,
    pins,
    read_local,
):
    body_ids = {
        entry["body"]["publication_id"]
        for entry, _ in directories
        if entry["body"]["publication_id"] != "self"
    }
    missing = sorted(body_ids - set(rows))
    if missing:
        await pins.pin(missing)
        rows.update({row["id"]: row for row in pins.publications})
    cache = {}
    result = []
    for entry, directory_id in directories:
        locator = entry["body"]
        identity = (
            directory_id
            if locator["publication_id"] == "self"
            else locator["publication_id"]
        )
        row = rows.get(identity)
        if row is None:
            raise IntegrityError(
                "archive message body publication is not pinned",
            )
        _validate_body_publication(row, boundary)
        path = BundleStore.validate_publication_locator(row)
        index = indexes.get(identity)
        if index is None:
            index = await read_local(
                bundles.inspect,
                path,
                expected_length=row["byte_length"],
            )
            indexes[identity] = index
        key = identity, locator["block_name"]
        bodies = cache.get(key)
        if bodies is None:
            extent = index.blocks.get(locator["block_name"])
            if extent is None or extent.kind not in (
                "message_bodies",
                "message",
                "memory",
                "anchor",
                "task",
                "error",
                "archive",
            ):
                raise IntegrityError("archive message body block is missing")
            payload = await read_local(
                bundles.read_extent,
                path,
                extent.offset,
                extent.length,
                expected_length=index.byte_length,
            )
            bodies = (
                decode_message_bodies(payload)
                if extent.kind == "message_bodies"
                else (load_metadata_json(payload),)
            )
            cache[key] = bodies
        position = locator["position"]
        if position >= len(bodies):
            raise IntegrityError(
                "archive message body position is outside block",
            )
        result.append({**entry, "message": bodies[position]})
    return result


def _validate_chunk_publication(row, boundary, manifest):
    if row.get("chat_id") != boundary.get("chat_id"):
        raise IntegrityError("archive chunk Chat association mismatch")
    if row.get("session_id") != boundary.get("session_id"):
        raise IntegrityError("archive chunk Session association mismatch")


def _validate_body_publication(row, boundary):
    if row.get("session_id") != boundary.get("session_id"):
        raise IntegrityError("archive message body Session mismatch")
