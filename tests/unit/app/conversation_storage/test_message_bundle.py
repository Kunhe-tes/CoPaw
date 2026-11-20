# -*- coding: utf-8 -*-
import pytest

from swe.app.conversation_storage.errors import IntegrityError
from swe.app.conversation_storage.message_bundle import (
    decode_archive_manifest,
    decode_message_bodies,
    decode_message_directory,
    encode_message_bodies,
    encode_message_directory,
    encode_archive_manifest,
    select_archive_chunks,
    split_message_batches,
)


def _entry(sequence, raw_id, position):
    return {
        "sequence": sequence,
        "raw_id": raw_id,
        "layer": "memory",
        "visible": True,
        "body": {
            "publication_id": "self",
            "block_name": "message_bodies",
            "position": position,
        },
    }


def test_message_body_encoding_is_deterministic_and_positioned():
    bodies = (
        {"id": "duplicate", "content": "first"},
        {"id": "duplicate", "content": "second"},
    )

    encoded = encode_message_bodies(bodies)

    assert encoded == encode_message_bodies(bodies)
    assert decode_message_bodies(encoded) == bodies
    assert (
        decode_message_directory(
            encode_message_directory(
                (_entry(0, "duplicate", 0), _entry(1, "duplicate", 1)),
            ),
        )[1]["body"]["position"]
        == 1
    )


def test_directory_requires_strict_sequence_order_but_keeps_duplicate_raw_ids():
    entries = (_entry(2, "same", 0), _entry(3, "same", 1))

    assert tuple(
        entry["raw_id"]
        for entry in decode_message_directory(
            encode_message_directory(entries),
        )
    ) == ("same", "same")
    with pytest.raises(ValueError, match="strictly ordered"):
        encode_message_directory((_entry(3, "same", 0), _entry(2, "same", 1)))


def test_directory_rejects_duplicate_json_keys():
    with pytest.raises(IntegrityError, match="JSON is invalid"):
        decode_message_directory(
            b'[{"sequence":0,"sequence":1,"raw_id":"x","visible":true,'
            b'"body":{"publication_id":"self","block_name":"b",'
            b'"position":0}}]',
        )


def test_split_batches_obeys_encoded_bytes_and_record_count():
    messages = tuple(
        {"id": str(index), "content": "x" * 20} for index in range(5)
    )

    batches = split_message_batches(messages, max_bytes=100, max_records=2)

    assert tuple(len(batch) for batch in batches) == (2, 2, 1)
    assert all(len(encode_message_bodies(batch)) <= 100 for batch in batches)


def test_archive_manifest_selects_only_chunks_intersecting_requested_range():
    manifest = {
        "format": "swe.archive-manifest.v1",
        "chat_id": "chat-1",
        "epoch": 4,
        "first_sequence": 20,
        "last_sequence": 24,
        "chunks": [
            {
                "publication_id": 10,
                "first_sequence": 20,
                "last_sequence": 21,
                "directory_block": "message_directory",
            },
            {
                "publication_id": 11,
                "first_sequence": 22,
                "last_sequence": 24,
                "directory_block": "message_directory",
            },
        ],
    }

    decoded = decode_archive_manifest(encode_archive_manifest(manifest))

    assert tuple(
        chunk["publication_id"]
        for chunk in select_archive_chunks(decoded, 23, 24)
    ) == (11,)
    manifest["chunks"][1]["first_sequence"] = 23
    with pytest.raises(ValueError, match="range is invalid"):
        encode_archive_manifest(manifest)


def test_archive_manifest_allows_local_chunk_and_reports_publication_dependencies():
    from swe.app.conversation_storage.archive_bundle_reader import (
        archive_manifest_dependencies,
        validate_archive_manifest,
    )

    manifest = {
        "format": "swe.archive-manifest.v1",
        "chat_id": "chat-1",
        "epoch": 0,
        "first_sequence": 7,
        "last_sequence": 8,
        "chunks": [
            {
                "publication_id": 12,
                "first_sequence": 7,
                "last_sequence": 7,
                "directory_block": "message_directory",
            },
            {
                "publication_id": "self",
                "first_sequence": 8,
                "last_sequence": 8,
                "directory_block": "message_directory",
            },
        ],
    }

    normalized, chunks = validate_archive_manifest(manifest)

    assert len(chunks) == 2
    assert archive_manifest_dependencies(
        normalized,
        boundary_publication_id=20,
    ) == (12,)
