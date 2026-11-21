# -*- coding: utf-8 -*-
"""Bounded indexed checkpoint and evidence reads with explicit reader pins."""

from ...agents.memory.conversation_archive import (
    ConversationArchiveStore,
)
from .bundle import BundleStore
from .chat_mutations import load_metadata_json, utc_datetime
from .checkpoint_reader import CheckpointReads
from .errors import IntegrityError
from .identity import chat_key_bytes
from .message_bundle import (
    decode_message_directory,
    validate_runtime_occurrences,
)
import asyncio
import json
from .retention import RetentionStore


class EvidenceSelectors:
    """Reuse the existing pure evidence matching contract without a file store."""

    _parse_evidence_time_range = staticmethod(
        ConversationArchiveStore._parse_evidence_time_range,
    )
    _message_in_time_range = staticmethod(
        ConversationArchiveStore._message_in_time_range,
    )
    prepare = ConversationArchiveStore._prepare_evidence_query
    matches = ConversationArchiveStore._matches_evidence_query


def _decode(cls, payload):
    try:
        return cls.from_dict(payload)
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise IntegrityError(
            "indexed archive body schema is invalid",
        ) from error


def text(value):
    return (
        bytes(value).decode()
        if isinstance(value, (bytes, bytearray))
        else value
    )


class ArchiveReader(CheckpointReads):
    def __init__(self, database, scope, bundles):
        self.db, self.scope, self.bundles = database, scope, bundles
        self.retentions = RetentionStore(database, scope)

    async def chat(self, chat_id):
        row = await self.db.fetch_one(
            "SELECT * FROM swe_conversation_chats WHERE service_unit_key=%s AND tenant_key=%s AND source_key=%s AND agent_key=%s AND external_chat_key=%s AND deleted_at IS NULL",
            (*self.scope.sql_values, chat_key_bytes(chat_id)),
        )
        if row is None:
            raise KeyError(chat_id)
        return row

    async def payload(self, batch, publication, prefix):
        raw = await batch.read(
            self.bundles.read_extent,
            BundleStore.validate_publication_locator(publication),
            publication[prefix + "_offset"],
            publication[prefix + "_length"],
            expected_length=publication["byte_length"],
        )
        return load_metadata_json(raw)

    async def session_messages(self, session_id, *, high=None, layers=None):
        """Resolve the active Session recovery directory into ordered messages."""
        from types import SimpleNamespace
        from .projection_publication import _text
        from .projection_references import ref_key, snapshot_projection
        from .session_projection import is_projection

        async with self.db.transaction():
            session = await self.db.fetch_one(
                "SELECT * FROM swe_conversation_sessions WHERE id=%s "
                "AND service_unit_key=%s AND tenant_key=%s AND source_key=%s "
                "AND agent_key=%s",
                (session_id, *self.scope.sql_values),
            )
            if (
                session is None
                or session.get("recovery_publication_id") is None
            ):
                return []
            batch = await self.retentions.pin(
                [session["recovery_publication_id"]],
                kind="reader",
            )
        try:
            publication = batch.publications[0]
            if publication["session_id"] != session_id:
                raise IntegrityError("history recovery Session mismatch")
            index = await batch.read(
                self.bundles.inspect,
                _text(publication["relative_path"]),
                expected_length=publication["byte_length"],
            )
            root = await batch.read(
                self.bundles.read_extent,
                index.relative_path,
                session["recovery_offset"],
                session["recovery_length"],
                expected_length=index.byte_length,
            )
            envelope = load_metadata_json(root)
            if not is_projection(envelope):
                return []

            async def nas_io(_operation_key, function, *args, **kwargs):
                return await asyncio.to_thread(function, *args, **kwargs)

            service = SimpleNamespace(
                db=self.db,
                bundles=self.bundles,
                _nas_io=nas_io,
            )
            source = SimpleNamespace(
                operation_key=_text(publication["operation_key"]),
                scope=self.scope,
                session_id=session_id,
            )
            refs = await snapshot_projection(
                service,
                source,
                envelope,
                index,
                current_id=publication["id"],
                retentions=self.retentions,
            )
            try:
                directory = decode_message_directory(
                    json.dumps(
                        envelope.get("message_directory", []),
                        separators=(",", ":"),
                    ).encode(),
                )
                validate_runtime_occurrences(directory)
                result = []
                for item in directory:
                    entry = dict(item)
                    if layers and entry.get("layer") not in layers:
                        continue
                    if not entry.get("visible", True):
                        continue
                    order = entry.get("session_order", entry["sequence"])
                    if high is not None and order > high:
                        continue
                    locator = dict(entry["body"])
                    if locator["publication_id"] == "self":
                        ref = {
                            "operation_key": source.operation_key,
                            "block_name": locator["block_name"],
                            "position": locator["position"],
                        }
                    else:
                        ref = locator
                    body = refs.payloads.get(ref_key(ref))
                    if body is None:
                        raise IntegrityError(
                            "history directory body is missing",
                        )
                    raw_id = entry["raw_id"]
                    occurrence = {
                        **entry,
                        "id": order,
                        "service_unit_key": self.scope.sql_values[0],
                        "session_id": session_id,
                        "publication_id": ref.get(
                            "publication_id",
                            publication["id"],
                        ),
                        "relative_path": publication["relative_path"],
                        "byte_offset": 0,
                        "byte_length": 0,
                        "source_msg_key": (
                            entry.get("source_msg_key", raw_id).encode()
                            if isinstance(
                                entry.get("source_msg_key", raw_id),
                                str,
                            )
                            else entry.get("source_msg_key", raw_id)
                        ),
                        "source_occurrence_no": entry["source_occurrence_no"],
                        "role_key": (
                            entry.get("role")
                            or body.get("role")
                            or "assistant"
                        ).encode(),
                        "layer": entry.get(
                            "layer",
                            entry.get("category", "memory"),
                        ),
                        "kind_key": (entry.get("kind") or "message").encode(),
                        "task_run_key": (
                            entry["task"].encode()
                            if isinstance(entry.get("task"), str)
                            else entry.get("task")
                        ),
                        "task_index": entry.get("task_index"),
                        "task_section": entry.get("task_section"),
                        "origin_chat_id": entry.get("origin_chat_id"),
                        "archive_chat_id": entry.get("archive_chat_id"),
                        "archive_order": entry.get("archive_order"),
                        "turn_id": entry.get("turn_id"),
                        "context_epoch": entry.get("context_epoch", 0),
                        "session_order": order,
                        "current_visible": entry.get("current_visible", True),
                        "in_context": entry.get("in_context", False),
                        "deleted_at": None,
                        "message_timestamp": (
                            utc_datetime(entry["timestamp"])
                            if entry.get("timestamp") is not None
                            else None
                        ),
                        "message": body,
                    }
                    result.append(occurrence)
                return sorted(result, key=lambda value: value["session_order"])
            finally:
                await refs.finish(self.retentions)
        finally:
            await self.retentions.finish_reader(batch)

    async def evidence(
        self,
        chat_id,
        *,
        epoch,
        refs,
        query=None,
        kinds=None,
        time_range=None,
        limit=10,
    ):
        from agentscope.message import Msg

        if limit <= 0:
            return []
        selector = EvidenceSelectors()
        normalized = selector.prepare(
            refs,
            query,
            kinds,
            time_range,
        )
        if not normalized.requested and not normalized.semantic_query:
            return []
        chat = await self.chat(chat_id)
        if chat["epoch"] != epoch:
            return []
        recovered = []
        boundaries = await self.db.fetch_all(
            "SELECT * FROM swe_conversation_publications WHERE chat_id=%s "
            "AND epoch=%s AND state='committed' AND archive_last_order IS NOT NULL "
            "ORDER BY archive_first_order",
            (chat["id"], epoch),
        )
        from .archive_bundle_reader import read_archive_bundle

        for boundary in boundaries:
            selected = await read_archive_bundle(
                self.db,
                self.scope,
                self.bundles,
                boundary,
                retentions=self.retentions,
            )
            try:
                for entry in selected.entries:
                    msg = _decode(Msg, entry["message"])
                    if selector.matches(
                        msg,
                        requested=normalized.requested,
                        semantic_query=normalized.semantic_query,
                        kind_filter=normalized.kind_filter,
                        time_bounds=normalized.time_bounds,
                    ):
                        recovered.append(msg)
                        if len(recovered) >= min(limit, 10):
                            break
            finally:
                await selected.pins.finish()
            if len(recovered) >= min(limit, 10):
                break
        current = await self.chat(chat_id)
        if (
            current["epoch"] != epoch
            or current["session_id"] != chat["session_id"]
        ):
            return []
        return recovered
