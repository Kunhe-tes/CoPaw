# -*- coding: utf-8 -*-
"""Scope checked direct recovery body references with bounded reader pins."""

from dataclasses import dataclass, field
import json

from .errors import IntegrityError
from .message_bundle import decode_message_bodies
from .retention import ReaderPins, RetentionStore
from .session_projection import hydrate_state, is_projection
from .projection_cache import active, cache_key, cached, remember
from .reference_queries import ReferenceQuery, fetch_reference_rows

TURN_FIELDS = (
    "service_unit_key",
    "session_id",
    "chat_id",
    "terminal_publication_id",
    "history_status",
    "question_msg_key",
)


def ref_key(ref):
    return json.dumps(ref, sort_keys=True, separators=(",", ":"))


def references(envelope):
    refs = [
        entry["ref"]
        for series in envelope["lists"]
        for entry in series["entries"]
    ]
    refs.extend(item["ref"] for item in envelope["turns"])
    for item in envelope.get("message_directory", ()):
        locator = item["body"]
        if locator["publication_id"] == "self":
            locator = {
                "operation_key": envelope["identity"]["operation_key"],
                "block_name": locator["block_name"],
                "position": locator["position"],
            }
        refs.append(locator)
    return list({ref_key(ref): ref for ref in refs}.values())


def _text(value):
    return (
        bytes(value).decode()
        if isinstance(value, (bytes, bytearray))
        else value
    )


@dataclass
class ProjectionReferences:
    payloads: dict = field(default_factory=dict)
    publications: dict = field(default_factory=dict)
    batch: object = None
    turns: dict = field(default_factory=dict)

    @property
    def publication_ids(self):
        return sorted(self.publications)

    async def finish(self, retentions):
        if self.batch is not None:
            await self.batch.finish()
            self.batch = None

    async def revalidate(self, db):
        turns = (
            await fetch_reference_rows(
                db,
                ReferenceQuery.TURN_REFERENCE,
                self.turns,
                next(iter(self.turns.values()))["service_unit_key"],
            )
            if self.turns
            else {}
        )
        for identity, expected in sorted(self.turns.items()):
            row = turns.get(identity)
            if row is None or any(
                row[key] != expected[key] for key in TURN_FIELDS
            ):
                raise IntegrityError("cold Turn projection authority changed")


async def _snapshot_rows(service, request, refs, snapshot):
    turns = await fetch_reference_rows(
        service.db,
        ReferenceQuery.TURN_REFERENCE,
        [ref["turn_id"] for ref in refs if "turn_id" in ref],
        request.scope.sql_values[0],
    )
    for ref in refs:
        if "turn_id" not in ref:
            continue
        turn = turns.get(ref["turn_id"])
        if (
            turn is None
            or turn["service_unit_key"] != request.scope.sql_values[0]
            or turn["session_id"] != request.session_id
            or turn["terminal_publication_id"] != ref["publication_id"]
        ):
            raise IntegrityError("cold Turn reference association differs")
        snapshot.turns[turn["id"]] = turn


def _cached_bodies(request, envelope):
    cached_values = cached(
        (
            *(request.scope.sql_values),
            request.session_id,
            envelope.get("identity", {}).get("base_state_revision"),
        ),
    )
    cached_bodies = {}
    if cached_values is not None:
        for (_, body), values in cached_values.items():
            for value in values:
                cached_bodies[ref_key(value)] = json.loads(body)
    return cached_bodies


async def snapshot_projection(
    service,
    request,
    envelope,
    index,
    *,
    current_id,
    retentions=None,
):
    snapshot = ProjectionReferences()
    if envelope is None:
        return snapshot
    refs = references(envelope)
    cached_bodies = _cached_bodies(request, envelope)
    retentions = retentions or RetentionStore(service.db, request.scope)
    snapshot.batch = ReaderPins(retentions)
    try:
        async with service.db.transaction():
            await _snapshot_rows(service, request, refs, snapshot)
            ids = sorted(
                {
                    ref["publication_id"]
                    for ref in refs
                    if "publication_id" in ref
                },
            )
            if any(identity >= current_id for identity in ids):
                raise IntegrityError(
                    "recovery dependencies must point to older publications",
                )
            if ids:
                await snapshot.batch.pin(ids)
                snapshot.publications = {
                    row["id"]: row for row in snapshot.batch.publications
                }
        decoded = {}
        indexes = {current_id: index}
        for ref in refs:
            if ref_key(ref) in cached_bodies:
                snapshot.payloads[ref_key(ref)] = cached_bodies[ref_key(ref)]
                continue
            target = ref.get("publication_id", current_id)
            if target != current_id:
                publication = snapshot.publications[target]
                if publication["session_id"] != request.session_id:
                    raise IntegrityError(
                        "recovery projection dependency Session differs",
                    )
                if target not in indexes:
                    indexes[target] = await snapshot.batch.read(
                        service.bundles.inspect,
                        _text(publication["relative_path"]),
                        expected_length=publication["byte_length"],
                    )
            target_index = indexes[target]
            name = ref["block_name"]
            extent = target_index.blocks.get(name)
            if extent is None or ("turn_id" in ref and extent.kind != "turn"):
                raise IntegrityError("recovery reference block is invalid")
            if (target, name) not in decoded:
                args = (
                    service.bundles.read_extent,
                    target_index.relative_path,
                    extent.offset,
                    extent.length,
                )
                if target == current_id:
                    raw = await service._nas_io(
                        request.operation_key,
                        *args,
                        expected_length=target_index.byte_length,
                    )
                else:
                    raw = await snapshot.batch.read(
                        *args,
                        expected_length=target_index.byte_length,
                    )
                decoded[target, name] = (
                    decode_message_bodies(raw)
                    if extent.kind == "message_bodies"
                    else json.loads(raw)
                )
            snapshot.payloads[ref_key(ref)] = _resolve_payload(
                decoded[target, name],
                ref,
                snapshot.turns,
            )
        hydrate_state(envelope, lambda ref: snapshot.payloads[ref_key(ref)])
        return snapshot
    except BaseException:
        await snapshot.finish(retentions)
        raise


def _resolve_payload(payload, ref, turns):
    position = ref.get("position", 0)
    if isinstance(payload, (tuple, list)):
        if type(position) is not int or not 0 <= position < len(payload):
            raise IntegrityError("recovery message position is invalid")
        payload = payload[position]
    elif position != 0:
        raise IntegrityError("recovery message position is invalid")
    if "turn_id" in ref:
        turn = turns[ref["turn_id"]]
        if (
            ref["block_name"] != "turn:" + _text(turn["question_msg_key"])
            or payload.get("status") != turn["history_status"]
        ):
            raise IntegrityError("cold Turn independent body identity differs")
    return payload


async def hydrate_projection(adapter, envelope, session, publication, batch):
    if not is_projection(envelope):
        return envelope
    from types import SimpleNamespace

    source = SimpleNamespace(
        operation_key=_text(publication["operation_key"]),
        scope=adapter.scope,
        session_id=session["id"],
    )
    index = await batch.read(
        adapter.bundles.inspect,
        _text(publication["relative_path"]),
        expected_length=publication["byte_length"],
    )
    snapshot = await snapshot_projection(
        adapter.publications,
        source,
        envelope,
        index,
        current_id=publication["id"],
        retentions=adapter.retentions,
    )
    try:
        return hydrate_state(
            envelope,
            lambda ref: snapshot.payloads[ref_key(ref)],
        )
    finally:
        await snapshot.finish(adapter.retentions)


async def refresh_projection_cache(service, row, envelope, snapshot):
    if envelope is None or not active():
        return
    from collections import defaultdict
    from .projection_publication import canonical

    values = defaultdict(list)
    for series in envelope["lists"]:
        layer = (
            "memory"
            if len(series["path"]) > 1
            else "task" if series["path"][0] == "task_messages" else "error"
        )
        for entry in series["entries"]:
            ref = entry["ref"]
            payload = snapshot.payloads[ref_key(ref)]
            resolved = {
                "publication_id": ref.get("publication_id", row["id"]),
                "block_name": ref["block_name"],
                "position": ref.get("position", 0),
            }
            values[(layer, canonical(payload))].append(resolved)
    remember(cache_key(row, row["base_state_revision"] + 1), values)
