# -*- coding: utf-8 -*-
"""Validate immutable archive payloads before publication SQL locks."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone

from agentscope.message import Msg

from ...agents.memory.chat_checkpoint import (
    CheckpointEvent,
    CheckpointRecord,
    validate_checkpoint_record,
)
from .chat_mutations import load_metadata_json
from .errors import ConflictError, IntegrityError
from .identity import identity_bytes
from .bundle import BundleBlock
from .message_bundle import encode_archive_manifest, encode_message_directory


@dataclass(frozen=True)
class ArchivePayloads:
    checkpoint: CheckpointRecord | None = None
    manifest: dict | None = None

    def validate_chat(self, chat):
        if self.manifest is not None and (
            identity_bytes(self.manifest["chat_id"], 256)
            != chat["external_chat_key"]
            or self.manifest["first_sequence"] != chat["history_high"] + 1
        ):
            raise IntegrityError(
                "archive manifest differs from the locked Chat",
            )
        if (
            self.checkpoint is not None
            and identity_bytes(self.checkpoint.chat_id, 256)
            != chat["external_chat_key"]
        ):
            raise IntegrityError("checkpoint body Chat identity mismatch")


def validate_archive_plan(plan):
    if plan.install_digest is not None:
        return
    archived = [item for item in plan.messages if item.layer == "archive"]
    if archived and plan.archive is None:
        raise ValueError("archive occurrences require a committed boundary")
    if plan.archive is not None and len(archived) != plan.archive.source_count:
        raise ValueError(
            "archive boundary source count differs from occurrences",
        )
    if plan.archive is not None and (
        archived[0].source_msg_key != plan.archive.first_source_msg_key
        or archived[-1].source_msg_key != plan.archive.last_source_msg_key
    ):
        raise ValueError(
            "archive boundary source identities differ from occurrences",
        )


def validate_request_plan(request, plan):
    validate_archive_plan(plan)
    if request.kind == "compact" and plan.recovery_block is None:
        raise ValueError("compact requires a complete recovery root")


async def prepare_archive_blocks(service, request, plan, blocks):
    if plan.archive is None:
        return blocks
    from .source_messages import snapshot_sources

    chat = await service.db.fetch_one(
        "SELECT external_chat_key,history_high FROM swe_conversation_chats "
        "WHERE id=%s AND service_unit_key=%s AND history_revision=%s",
        (
            request.chat_id,
            request.scope.sql_values[0],
            request.base_history_revision,
        ),
    )
    if chat is None:
        raise ConflictError("archive Chat revision changed")
    sources = await snapshot_sources(service, request, plan)
    try:
        archived = [item for item in plan.messages if item.layer == "archive"]
        first = chat["history_high"] + 1
        entries = []
        for sequence, item in enumerate(archived, first):
            source = sources.rows.get(item.source_message_id)
            locator = (
                {
                    "publication_id": source["publication_id"],
                    "block_name": source["body"]["block_name"],
                    "position": source["body"]["position"],
                }
                if source is not None
                else {
                    "publication_id": "self",
                    "block_name": item.block_name,
                    "position": 0,
                }
            )
            entries.append(
                {
                    "sequence": sequence,
                    "archive_order": sequence,
                    "raw_id": item.source_msg_key or "",
                    "layer": "archive",
                    "visible": True,
                    "turn_id": item.turn_id,
                    "archive_chat_id": request.chat_id,
                    "origin_chat_id": item.origin_chat_id,
                    "role": item.role,
                    "kind": item.kind,
                    "task": item.task_run_key,
                    "source_occurrence_no": item.source_occurrence_no,
                    "context_epoch": item.context_epoch,
                    "timestamp": item.message_timestamp,
                    "body": locator,
                },
            )
        archive_blocks = []
        chunks = []
        for start in range(0, len(entries), 1000):
            part = entries[start : start + 1000]
            name = f"archive-directory:{start}"
            archive_blocks.append(
                BundleBlock(
                    name,
                    "message_directory",
                    encode_message_directory(part),
                ),
            )
            chunks.append(
                {
                    "publication_id": "self",
                    "directory_block": name,
                    "first_sequence": part[0]["sequence"],
                    "last_sequence": part[-1]["sequence"],
                },
            )
        archive_blocks.append(
            BundleBlock(
                plan.archive.block_name,
                "archive_manifest",
                encode_archive_manifest(
                    {
                        "chat_id": chat["external_chat_key"].decode(),
                        "epoch": request.epoch,
                        "first_sequence": first,
                        "last_sequence": first + len(entries) - 1,
                        "chunks": chunks,
                    },
                ),
            ),
        )
        return [
            *(
                block
                for block in blocks
                if block.name != plan.archive.block_name
            ),
            *archive_blocks,
        ]
    finally:
        await sources.finish(service, request.scope)


def _stamp(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("archive timestamp must be a string")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _checkpoint(value, request, plan):
    record = CheckpointRecord.from_dict(value)
    if not validate_checkpoint_record(record).is_valid or (
        record.epoch != request.epoch
        or record.revision != plan.revision
        or record.source_revision != plan.base_revision
        or record.applied_event_sequence != plan.event_watermark
    ):
        raise ValueError("checkpoint body differs from installation metadata")
    return record


def _events(value, request, plan):
    if not isinstance(value, list) or len(value) != plan.last - plan.first + 1:
        raise ValueError("event body count differs from declared range")
    events = tuple(CheckpointEvent.from_dict(item) for item in value)
    if len({item.id for item in events}) != len(events) or any(
        not item.id or item.sequence != plan.first + index
        for index, item in enumerate(events)
    ):
        raise ValueError("event identities or sequence range are invalid")
    record = replace(
        CheckpointRecord.new(chat_id="validation", epoch=request.epoch),
        applied_event_sequence=plan.first - 1,
    )
    if not validate_checkpoint_record(record, events).is_valid:
        raise ValueError("event body epoch or facts are invalid")


def _archive(entries, plan, sources):
    from ..runner.utils import agentscope_msg_to_message

    archived = [item for item in plan.messages if item.layer == "archive"]
    if len(entries) != len(archived):
        raise ValueError("archive directory count differs from occurrences")
    originals = [entry["message"] for entry in entries]
    count = 0
    for item, entry, raw in zip(archived, entries, originals):
        if not isinstance(raw, dict) or (
            raw.get("id"),
            raw.get("role"),
            _stamp(raw.get("timestamp")),
        ) != (item.source_msg_key, item.role, _stamp(item.message_timestamp)):
            raise ValueError(
                "archive occurrence body identity differs from metadata",
            )
        if (
            entry["raw_id"],
            entry["turn_id"],
            entry["origin_chat_id"],
            entry["archive_chat_id"],
        ) != (
            item.source_msg_key,
            item.turn_id,
            item.origin_chat_id,
            item.archive_chat_id,
        ):
            raise ValueError("archive directory associations differ")
        if item.source_message_id is not None and (
            sources.payloads[item.block_name] != raw
        ):
            raise ValueError("archive referenced body differs from Session")
        count += len(agentscope_msg_to_message(Msg.from_dict(raw)))
    boundary = plan.archive
    if (
        count != boundary.display_count
        or _stamp(originals[0].get("timestamp"))
        != _stamp(boundary.first_timestamp)
        or _stamp(originals[-1].get("timestamp"))
        != _stamp(boundary.last_timestamp)
    ):
        raise ValueError("archive boundary display count or timestamps differ")


async def validate_archive_payloads(
    service,
    request,
    plan,
    index,
    publication=None,
    *,
    sources=None,
):
    specs = {}
    for item, kind in (
        (plan.checkpoint, "checkpoint"),
        (plan.events, "events"),
    ):
        if item is not None:
            specs[item.block_name] = kind
    payloads = {}
    try:
        for name, kind in specs.items():
            extent = index.blocks.get(name)
            if extent is None or extent.kind != kind:
                raise ValueError(kind + " block is missing or invalid")
            raw = await service._nas_io(
                request.operation_key,
                service.bundles.read_extent,
                index.relative_path,
                extent.offset,
                extent.length,
                expected_length=index.byte_length,
            )
            payloads[name] = load_metadata_json(raw)
        checkpoint = None
        if plan.checkpoint is not None:
            checkpoint = _checkpoint(
                payloads[plan.checkpoint.block_name],
                request,
                plan.checkpoint,
            )
        if plan.events is not None:
            _events(payloads[plan.events.block_name], request, plan.events)
        manifest = None
        if plan.archive is not None:
            from .archive_bundle_reader import read_archive_bundle

            archive = await read_archive_bundle(
                service.db,
                request.scope,
                service.bundles,
                publication,
                prepared_index=index,
            )
            sources.archive_pins = archive.pins
            _archive(archive.entries, plan, sources)
            manifest = archive.manifest
            sources.dependency_publications.update(
                (row["id"], row) for row in archive.pins.publications
            )
        return ArchivePayloads(checkpoint, manifest)
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise IntegrityError(
            "archive/checkpoint/event body validation failed: " + str(error),
        ) from error
