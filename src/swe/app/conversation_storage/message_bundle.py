# -*- coding: utf-8 -*-
"""Deterministic message directory and body bundle encoding."""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
import json

from .errors import IntegrityError

DEFAULT_MESSAGE_BLOCK_BYTES = 8 * 1024 * 1024
DEFAULT_MESSAGE_BLOCK_RECORDS = 1000
ARCHIVE_MANIFEST_FORMAT = "swe.archive-manifest.v1"

_DIRECTORY_FIELDS = frozenset(
    {
        "sequence",
        "raw_id",
        "category",
        "visible",
        "body",
        "turn_id",
        "chat_id",
        "role",
        "kind",
        "task",
        "task_index",
        "task_section",
        "source_occurrence",
        "timestamp",
        "epoch",
        "layer",
        "archive_order",
        "session_order",
        "current_visible",
        "in_context",
        "origin_chat_id",
        "source_msg_key",
        "source_occurrence_no",
        "context_epoch",
        "archive_chat_id",
    },
)
_BODY_LOCATOR_FIELDS = frozenset(
    {"publication_id", "block_name", "position"},
)


def _reject_constant(value):
    raise ValueError(f"nonfinite JSON number {value}")


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object field")
        result[key] = value
    return result


def _json_bytes(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _load_json(payload):
    try:
        return json.loads(
            payload,
            object_pairs_hook=_unique_fields,
            parse_constant=_reject_constant,
        )
    except (
        UnicodeDecodeError,
        ValueError,
        TypeError,
        RecursionError,
    ) as error:
        raise IntegrityError("message bundle JSON is invalid") from error


def _validate_body(value):
    if not isinstance(value, dict):
        raise ValueError("message body must be an object")
    _json_bytes(value)


def _validate_locator(locator):
    if (
        not isinstance(locator, Mapping)
        or set(locator) != _BODY_LOCATOR_FIELDS
    ):
        raise ValueError("message body locator is invalid")
    publication_id = locator["publication_id"]
    block_name = locator["block_name"]
    position = locator["position"]
    if publication_id != "self" and (
        type(publication_id) is not int or publication_id <= 0
    ):
        raise ValueError("message publication identity is invalid")
    if not isinstance(block_name, str) or not block_name:
        raise ValueError("message block name is invalid")
    if type(position) is not int or position < 0:
        raise ValueError("message body position is invalid")


def _normalize_directory_entry(entry):
    if not isinstance(entry, Mapping):
        raise ValueError("message directory entry must be an object")
    if set(entry) - _DIRECTORY_FIELDS:
        raise ValueError("message directory entry has unknown fields")
    required = {"sequence", "raw_id", "visible", "body"}
    if not required.issubset(entry):
        raise ValueError("message directory entry is incomplete")
    sequence = entry["sequence"]
    raw_id = entry["raw_id"]
    category = entry.get("category", entry.get("layer"))
    if type(sequence) is not int or sequence < 0:
        raise ValueError("message sequence is invalid")
    if not isinstance(raw_id, str):
        raise ValueError("raw message identity must be a string")
    if not isinstance(category, str) or not category:
        raise ValueError("message category is invalid")
    if type(entry["visible"]) is not bool:
        raise ValueError("message visibility must be boolean")
    _validate_locator(entry["body"])
    normalized = dict(entry)
    normalized.setdefault("category", category)
    normalized.setdefault("layer", category)
    for key in (
        "turn_id",
        "chat_id",
        "source_occurrence",
        "source_occurrence_no",
        "epoch",
        "context_epoch",
        "archive_order",
        "session_order",
        "origin_chat_id",
        "archive_chat_id",
    ):
        if key in normalized and normalized[key] is not None:
            if type(normalized[key]) is not int or normalized[key] < 0:
                raise ValueError(f"message {key} is invalid")
    for key in (
        "role",
        "kind",
        "task",
        "task_section",
        "timestamp",
        "layer",
        "source_msg_key",
    ):
        if (
            key in normalized
            and normalized[key] is not None
            and not isinstance(
                normalized[key],
                str,
            )
        ):
            raise ValueError(f"message {key} must be a string")
    for key in ("current_visible", "in_context"):
        if key in normalized and type(normalized[key]) is not bool:
            raise ValueError(f"message {key} must be boolean")
    return normalized


def encode_message_body(message: dict) -> bytes:
    """Encode one message with the canonical body-block representation."""
    if not isinstance(message, dict):
        raise ValueError("message body must be an object")
    return _json_bytes(message)


def _body_payload(encoded: Sequence[bytes]) -> bytes:
    return b"[" + b",".join(encoded) + b"]"


def _encoded_batch(messages, encoded):
    return EncodedMessageBatch(
        tuple(messages),
        tuple(encoded),
        _body_payload(encoded),
    )


def encode_message_bodies(messages: Sequence[dict]) -> bytes:
    """Encode one ordered body block. Array positions are the body locators."""
    if isinstance(messages, (str, bytes)) or not isinstance(
        messages,
        Sequence,
    ):
        raise ValueError("message bodies must be an ordered sequence")
    return _body_payload(
        tuple(encode_message_body(body) for body in messages),
    )


def decode_message_bodies(payload: bytes) -> tuple[dict, ...]:
    value = _load_json(payload)
    if not isinstance(value, list):
        raise IntegrityError("message body block must contain an array")
    for body in value:
        try:
            _validate_body(body)
        except (TypeError, ValueError, OverflowError) as error:
            raise IntegrityError(
                "message body block entry is invalid",
            ) from error
    return tuple(value)


def encode_message_directory(entries: Sequence[dict]) -> bytes:
    """Encode validated message occurrence metadata in sequence order."""
    if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        raise ValueError("message directory must be an ordered sequence")
    normalized = [_normalize_directory_entry(entry) for entry in entries]
    sequences = [entry["sequence"] for entry in normalized]
    if sequences != sorted(sequences) or len(set(sequences)) != len(sequences):
        raise ValueError(
            "message directory sequences must be strictly ordered",
        )
    return _json_bytes(normalized)


def decode_message_directory(payload: bytes) -> tuple[dict, ...]:
    value = _load_json(payload)
    if not isinstance(value, list):
        raise IntegrityError("message directory block must contain an array")
    try:
        normalized = tuple(
            _normalize_directory_entry(entry) for entry in value
        )
        sequences = [entry["sequence"] for entry in normalized]
        if sequences != sorted(sequences) or len(set(sequences)) != len(
            sequences,
        ):
            raise ValueError(
                "message directory sequences are not strictly ordered",
            )
        return normalized
    except (TypeError, ValueError, OverflowError) as error:
        raise IntegrityError("message directory entry is invalid") from error


@dataclass(frozen=True)
class EncodedMessageBatch:
    """One body block with its canonical per-message encodings."""

    messages: tuple[dict, ...]
    encoded_bodies: tuple[bytes, ...]
    payload: bytes

    def __len__(self):
        return len(self.messages)


def iter_message_batches(
    messages: Sequence[dict],
    *,
    max_bytes: int = DEFAULT_MESSAGE_BLOCK_BYTES,
    max_records: int = DEFAULT_MESSAGE_BLOCK_RECORDS,
) -> Iterator[EncodedMessageBatch]:
    """Split ordered bodies and encode each message exactly once."""
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("message block byte limit is invalid")
    if type(max_records) is not int or max_records <= 0:
        raise ValueError("message block record limit is invalid")
    if isinstance(messages, (str, bytes)) or not isinstance(
        messages,
        Sequence,
    ):
        raise ValueError("message bodies must be an ordered sequence")

    current = []
    encoded = []
    current_size = 2
    for message in messages:
        if current and len(current) >= max_records:
            yield _encoded_batch(current, encoded)
            current, encoded, current_size = [], [], 2
        encoded_body = encode_message_body(message)
        encoded_size = len(encoded_body)
        addition = encoded_size + (1 if current else 0)
        if current and current_size + addition > max_bytes:
            yield _encoded_batch(current, encoded)
            current, encoded, current_size = [], [], 2
            addition = encoded_size
        if not current:
            current_size = encoded_size + 2
            current = [message]
            encoded = [encoded_body]
        else:
            current.append(message)
            encoded.append(encoded_body)
            current_size += addition
    if current:
        yield _encoded_batch(current, encoded)


def prepare_message_batches(
    messages: Sequence[dict],
    *,
    max_bytes: int = DEFAULT_MESSAGE_BLOCK_BYTES,
    max_records: int = DEFAULT_MESSAGE_BLOCK_RECORDS,
) -> tuple[EncodedMessageBatch, ...]:
    """Materialize prepared batches for callers that need the full sequence."""
    return tuple(
        iter_message_batches(
            messages,
            max_bytes=max_bytes,
            max_records=max_records,
        ),
    )


def split_message_batches(
    messages: Sequence[dict],
    *,
    max_bytes: int = DEFAULT_MESSAGE_BLOCK_BYTES,
    max_records: int = DEFAULT_MESSAGE_BLOCK_RECORDS,
) -> tuple[tuple[dict, ...], ...]:
    """Split ordered bodies by their encoded block size and record count."""
    return tuple(
        batch.messages
        for batch in prepare_message_batches(
            messages,
            max_bytes=max_bytes,
            max_records=max_records,
        )
    )


def _normalize_archive_manifest(manifest):
    if not isinstance(manifest, Mapping):
        raise ValueError("archive manifest must be an object")
    required = {
        "format",
        "chat_id",
        "epoch",
        "first_sequence",
        "last_sequence",
        "chunks",
    }
    if (
        set(manifest) != required
        or manifest["format"] != ARCHIVE_MANIFEST_FORMAT
    ):
        raise ValueError("archive manifest format is invalid")
    if not isinstance(manifest["chat_id"], str) or not manifest["chat_id"]:
        raise ValueError("archive manifest Chat identity is invalid")
    if type(manifest["epoch"]) is not int or manifest["epoch"] < 0:
        raise ValueError("archive manifest epoch is invalid")
    first = manifest["first_sequence"]
    last = manifest["last_sequence"]
    if (
        type(first) is not int
        or type(last) is not int
        or first < 0
        or last < first
    ):
        raise ValueError("archive manifest sequence range is invalid")
    chunks = manifest["chunks"]
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("archive manifest chunks are required")
    normalized_chunks = []
    expected = first
    seen_directories = set()
    for chunk in chunks:
        if not isinstance(chunk, Mapping) or set(chunk) != {
            "publication_id",
            "first_sequence",
            "last_sequence",
            "directory_block",
        }:
            raise ValueError("archive manifest chunk is invalid")
        publication_id = chunk["publication_id"]
        chunk_first = chunk["first_sequence"]
        chunk_last = chunk["last_sequence"]
        block = chunk["directory_block"]
        if publication_id != "self" and (
            type(publication_id) is not int or publication_id <= 0
        ):
            raise ValueError(
                "archive manifest publication identity is invalid",
            )
        if (
            type(chunk_first) is not int
            or type(chunk_last) is not int
            or chunk_first != expected
            or chunk_last < chunk_first
        ):
            raise ValueError("archive manifest chunk range is invalid")
        if not isinstance(block, str) or not block:
            raise ValueError("archive manifest directory block is invalid")
        directory = (publication_id, block)
        if directory in seen_directories:
            raise ValueError("archive manifest directory repeats")
        seen_directories.add(directory)
        normalized_chunks.append(dict(chunk))
        expected = chunk_last + 1
    if expected != last + 1:
        raise ValueError("archive manifest chunks do not cover its range")
    return {
        "format": ARCHIVE_MANIFEST_FORMAT,
        "chat_id": manifest["chat_id"],
        "epoch": manifest["epoch"],
        "first_sequence": first,
        "last_sequence": last,
        "chunks": normalized_chunks,
    }


def encode_archive_manifest(manifest: Mapping) -> bytes:
    return _json_bytes(_normalize_archive_manifest(manifest))


def decode_archive_manifest(payload: bytes) -> dict:
    try:
        return _normalize_archive_manifest(_load_json(payload))
    except (TypeError, ValueError, OverflowError) as error:
        raise IntegrityError("archive manifest is invalid") from error


def select_archive_chunks(
    manifest: Mapping,
    first_sequence: int,
    last_sequence: int,
):
    """Return only chunk locators intersecting an inclusive sequence range."""
    normalized = _normalize_archive_manifest(manifest)
    if (
        type(first_sequence) is not int
        or type(last_sequence) is not int
        or first_sequence < 0
        or last_sequence < first_sequence
    ):
        raise ValueError("archive chunk selection range is invalid")
    return tuple(
        chunk
        for chunk in normalized["chunks"]
        if chunk["last_sequence"] >= first_sequence
        and chunk["first_sequence"] <= last_sequence
    )
